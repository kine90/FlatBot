import os
import re
import io
import base64
import logging
from datetime import datetime
from time import sleep
from dotenv import load_dotenv

from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from io import BytesIO

from modules.StealthBrowser import StealthBrowser  # Your custom stealth browser
from modules.captcha.twocaptcha_solver import TwoCaptchaSolver  # Your solver

logger = logging.getLogger(__name__)
log_level = logging.INFO

def init_log():
    """
    Initialize logging to both console and a file in the 'logs' directory.
    """
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
    os.makedirs(log_dir, exist_ok=True)

    current_time = datetime.now()
    log_file = f"Flatbot_{current_time.day}_{current_time.month}_{current_time.year}.log"
    log_file_path = os.path.join(log_dir, log_file)

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_file_path),
            logging.StreamHandler()
        ]
    )

class CaptchaTester:
    """
    Handles detection and solving of various Captcha types:
    - GeeTest
    - reCAPTCHA
    - AWS WAF puzzle
    """

    def __init__(self, captcha_solver):
        self.captcha_solver = captcha_solver

    def detect_captcha(self, driver):
        """
        Checks the page source for known Captcha indicators.
        Returns a string identifier of the captcha type or None.
        """
        page_source = driver.page_source.lower()

        if "initgeetest" in page_source:
            return "geetest"
        if "g-recaptcha" in page_source:
            return "recaptcha"
        if "awswaf" in page_source:
            return "awswaf"
        return None

    def get_captcha_data(self, captcha_type, driver):
        """
        Extracts captcha-specific data from the page (e.g., sitekey, challenge, etc.).
        Returns a dictionary with the needed fields.
        """
        if captcha_type == "geetest":
            # Example: parse the geetest, challenge, and data from the page
            data = re.findall(
                r"geetest_validate: obj\.geetest_validate,\n.*?data: \"(.*)\"",
                driver.page_source
            )[0]
            result = re.findall(r"initGeetest\({(.*?)}", driver.page_source, re.DOTALL)
            geetest = re.findall(r"gt: \"(.*?)\"", result[0])[0]
            challenge = re.findall(r"challenge: \"(.*?)\"", result[0])[0]
            return {
                "geetest": geetest,
                "challenge": challenge,
                "data": data
            }

        elif captcha_type == "recaptcha":
            # Use modern By-locator
            recaptcha_elem = driver.find_element(By.CLASS_NAME, "g-recaptcha")
            sitekey = recaptcha_elem.get_attribute("data-sitekey")
            return {"sitekey": sitekey}

        elif captcha_type == "awswaf":
            # For AWS WAF, we'll grab data later in the solving phase 
            # if needed. Return an empty dict for now.
            return {}

        return {}

    def solve_captcha(self, captcha_type, data, driver, page_url):
        """
        Calls the appropriate solver function based on captcha_type.
        For AWS WAF, we handle the screenshot & clicks directly here.
        """
        if captcha_type == "geetest":
            # Solve using your geetest solver
            return self.captcha_solver.solve_geetest(
                data["geetest"], 
                data["challenge"], 
                page_url
            )

        elif captcha_type == "recaptcha":
            # Solve using your recaptcha solver
            return self.captcha_solver.solve_recaptcha(
                data["sitekey"], 
                page_url
            )

        elif captcha_type == "awswaf":
            """
            Resolve Amazon WAF Captcha:
            1) Scroll to puzzle
            2) Take screenshot
            3) Send to solver
            4) Perform clicks with Selenium
            """
            try:
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                sleep(3)

                # Access shadow root
                shadow_element = driver.execute_script(
                    "return document.querySelector('awswaf-captcha').shadowRoot"
                )
                my_img = shadow_element.find_element(By.ID, "root")
                size = my_img.size

                # Possibly interacting with the <select> to reveal the puzzle
                select_l = my_img.find_element(By.TAG_NAME, "select")
                select_l.click()
                sleep(1)
                select_l.send_keys(Keys.DOWN)  # or any needed key to adjust
                sleep(3)

                # Take screenshot
                shadow_element = driver.execute_script(
                    "return document.querySelector('awswaf-captcha').shadowRoot"
                )
                my_img = shadow_element.find_element(By.ID, "root")
                screenshot = my_img.screenshot_as_png

                # Encode screenshot
                screenshot_bytes = BytesIO(screenshot)
                base64_screenshot = base64.b64encode(screenshot_bytes.getvalue()).decode('utf-8')

                # Solve via your Amazon solver (which returns coords)
                result = self.captcha_solver.solve_amazon(base64_screenshot)

                # We'll do the clicks right here
                logger.info(result['code'])
                # Example format from solver: 'ok: x=123,y=45; x=200,y=99'
                coords_str = result['code'].split(':')[1].split(';')
                coords_list = [
                    [int(val.split('=')[1]) for val in coord.split(',')]
                    for coord in coords_str
                ]
                # Append final coords for some "submit" region (example)
                button_coord = [size['width'] - 30, size['height'] - 30]
                coords_list.append(button_coord)

                actions = ActionChains(driver)
                for (x_coord, y_coord) in coords_list:
                    # Offsetting from top-left of the puzzle
                    actions.move_to_element_with_offset(my_img, x_coord - 160, y_coord - 211).click()
                    actions.perform()
                    sleep(0.5)
                    actions.reset_actions()

                sleep(1)
                try:
                    confirm_button = my_img.find_element(By.ID, "amzn-btn-verify-internal")
                    actions.move_to_element_with_offset(confirm_button, 40, 15).click()
                    actions.perform()
                    sleep(4)
                except:
                    pass

                try:
                    driver.find_element(By.TAG_NAME, "awswaf-captcha")
                    logger.error("Captcha unsolvable or still present")
                except:
                    logger.info("Captcha solved")

            except Exception:
                driver.refresh()
            # Return None or an object indicating success/failure
            return None

        return None

    def inject_solution(self, captcha_type, driver, solution, extra_data=None):
        """
        Inject the captcha solver's response back into the page (if needed).
        - For GeeTest, might call some JS function 'solvedCaptcha(...)'.
        - For reCAPTCHA, might set `g-recaptcha-response`.
        - For AWS WAF, you might modify cookies or skip if already done by clicks.
        """
        if captcha_type == "geetest" and solution:
            # Example of injecting the GeeTest solution
            # `solution` might have .challenge, .sec_code, .validate
            script = (
                f'solvedCaptcha({{geetest_challenge: "{solution.challenge}",'
                f'geetest_seccode: "{solution.sec_code}",'
                f'geetest_validate: "{solution.validate}",'
                f'data: "{extra_data}"}});'
            )
            driver.execute_script(script)
            sleep(2)

        elif captcha_type == "recaptcha" and solution:
            # Put the token in the <textarea> for recaptcha
            driver.execute_script(
                'document.getElementById("g-recaptcha-response").innerHTML = "{}";'.format(
                    solution.get("code", "")
                )
            )

        # For AWS WAF, we perform clicks right away in solve_captcha, 
        # so no further injection needed here.

    def validate_solution(self, captcha_type, driver):
        """
        Optional post-injection check. Implementation is up to you:
        - e.g., does the page reload? does the captcha element disappear?
        """
        pass


class CaptchaTest:
    """
    Test harness to:
    1) Initialize the StealthBrowser
    2) Navigate to the target URL
    3) Detect & solve Captchas
    4) Clean up
    """

    def __init__(self, url, api_key):
        self.url = url
        self.api_key = api_key
        self.browser = None
        self.captcha_solver = TwoCaptchaSolver(api_key)
        self.captcha_tester = CaptchaTester(self.captcha_solver)

    def setup_browser(self):
        """
        Initialize the StealthBrowser instance.
        """
        try:
            self.browser = StealthBrowser()
            logger.info("StealthBrowser initialized.")
        except WebDriverException as e:
            logger.error("Failed to initialize StealthBrowser: %s", e)
            raise

    def run_test(self):
        """
        Run the CAPTCHA solving test flow.
        """
        try:
            self.browser.get(self.url)
            logger.info("Navigated to URL: %s", self.url)

            # 1) Detect the captcha type
            captcha_type = self.captcha_tester.detect_captcha(self.browser)
            if not captcha_type:
                logger.info("No CAPTCHA detected on the page.")
                return

            logger.info("Detected CAPTCHA type: %s", captcha_type)

            # 2) Extract relevant data
            captcha_data = self.captcha_tester.get_captcha_data(captcha_type, self.browser)

            # 3) Solve the captcha (some types require direct driver manipulation)
            solution = self.captcha_tester.solve_captcha(
                captcha_type, 
                captcha_data, 
                self.browser, 
                self.browser.current_url
            )

            # 4) Inject the solution (if necessary for that captcha type)
            if captcha_type == "geetest":
                # We have an extra piece of data for geetest 
                extra_data = captcha_data.get("data")
                self.captcha_tester.inject_solution(
                    captcha_type, self.browser, solution, extra_data
                )
            else:
                self.captcha_tester.inject_solution(captcha_type, self.browser, solution)

            logger.info("CAPTCHA solution injected.")

            # 5) Validate the solution
            self.captcha_tester.validate_solution(captcha_type, self.browser)
            logger.info("CAPTCHA solution validated (if applicable).")

        except Exception as e:
            logger.error("Error during CAPTCHA test: %s", e)
        finally:
            self.cleanup()

    def cleanup(self):
        """
        Quit the browser and do any necessary cleanup.
        """
        if self.browser:
            self.browser.quit()
            logger.info("Browser closed.")


if __name__ == "__main__":
    init_log()
    load_dotenv()

    TEST_URL = "https://www.immobilienscout24.de/expose/156170682"  # Replace with your target URL
    API_KEY = os.getenv("2CAPTCHA_API_KEY")  # Your 2Captcha API key from .env

    captcha_test = CaptchaTest(TEST_URL, API_KEY)
    captcha_test.setup_browser()
    captcha_test.run_test()
