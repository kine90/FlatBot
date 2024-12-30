import os
import re
import io
import base64
import logging
from time import sleep
from dotenv import load_dotenv

from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support.ui import Select
from io import BytesIO
from modules.captcha.twocaptcha_solver import TwoCaptchaSolver

logger = logging.getLogger(__name__)

class CaptchaTester:
    """
    Handles detection and solving of various Captcha types:
    - GeeTest
    - reCAPTCHA
    - AWS WAF puzzle

    Usage:
        from captcha_tester import CaptchaTester

        tester = CaptchaTester()
        solved = tester.solve_captcha_on_page(driver)
        if solved:
            print("Captcha solved!")
        else:
            print("Failed to solve captcha.")
    """

    def __init__(self):
        # Load API key from .env
        load_dotenv()
        api_key = os.getenv("2CAPTCHA_API_KEY")
        if not api_key:
            logger.warning("2CAPTCHA_API_KEY not found in .env.")
        self.captcha_solver = TwoCaptchaSolver(api_key)

    def detect_captcha(self, driver) -> str:
        """
        Checks the page source for known Captcha indicators.
        Returns a string identifier of the captcha type ('geetest', 
        'recaptcha', 'awswaf') or None if none found.
        """
        page_source = driver.page_source.lower()

        if "initgeetest" in page_source:
            return "geetest"
        if "g-recaptcha" in page_source:
            return "recaptcha"
        if "awswaf" in page_source:
            return "awswaf"
        return None

    def get_captcha_data(self, captcha_type, driver) -> dict:
        """
        Extracts captcha-specific data from the page (e.g., sitekey, challenge, etc.).
        Returns a dictionary with the needed fields.
        """
        if captcha_type == "geetest":
            data_match = re.search(
                r"geetest_validate: obj\.geetest_validate,\n.*?data: \"(.*)\"",
                driver.page_source
            )
            gt_data = data_match.group(1) if data_match else ""

            init_match = re.findall(
                r"initGeetest\({(.*?)}", 
                driver.page_source, 
                re.DOTALL
            )
            if init_match:
                geetest_str = init_match[0]
                geetest = re.search(r'gt: "([^"]+)"', geetest_str).group(1)
                challenge = re.search(r'challenge: "([^"]+)"', geetest_str).group(1)
                return {
                    "geetest": geetest,
                    "challenge": challenge,
                    "data": gt_data
                }
            else:
                logger.error("Could not parse geetest data from page.")
                return {}

        elif captcha_type == "recaptcha":
            recaptcha_elem = driver.find_element(By.CLASS_NAME, "g-recaptcha")
            sitekey = recaptcha_elem.get_attribute("data-sitekey")
            return {"sitekey": sitekey}

        elif captcha_type == "awswaf":
            # For AWS WAF, we typically handle everything inline. 
            # Returning an empty dict is okay.
            return {}

        return {}

    def solve_captcha(self, captcha_type, data, driver, page_url):
        """
        Calls the appropriate solver function based on captcha_type.
        For AWS WAF, handles screenshot & clicks directly.
        """
        try:
            if captcha_type == "geetest":
                return self.captcha_solver.solve_geetest(
                    data["geetest"], 
                    data["challenge"], 
                    page_url
                )

            elif captcha_type == "recaptcha":
                return self.captcha_solver.solve_recaptcha(
                    data["sitekey"], 
                    page_url
                )

            elif captcha_type == "awswaf":
                return self.solve_awswaf_captcha(driver)

        except Exception as e:
            logger.error(f"Error solving {captcha_type} CAPTCHA: {e}", exc_info=True)
            return False

        return False

    def solve_awswaf_captcha(self, driver):
        """
        Resolve Amazon WAF Captcha:
        1) Scroll to puzzle
        2) Take screenshot
        3) Send to solver
        4) Perform clicks with Selenium
        """
        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            sleep(1)

            # Access shadow root
            shadow_element = driver.execute_script(
                "return document.querySelector('awswaf-captcha').shadowRoot"
            )
            my_img = shadow_element.find_element(By.ID, "root")
            size = my_img.size

            # Possibly interacting with the <select> to reveal the puzzle
            select_l = my_img.find_element(By.TAG_NAME, "select")
            Select(select_l).select_by_visible_text("English")

            sleep(3)
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            sleep(1)

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
                return False

            try:
                driver.find_element(By.TAG_NAME, "awswaf-captcha")
                logger.error("Captcha unsolvable or still present")
                return False
            except:
                logger.info("Captcha solved")
                return True

        except Exception as e:
            logger.error(f"Error solving AWS WAF CAPTCHA: {e}", exc_info=True)
            return False

    def inject_solution(self, captcha_type, driver, solution, extra_data=None):
        """
        Inject the captcha solver's response back into the page (if needed).
        - For GeeTest, might call some JS function 'solvedCaptcha(...)'.
        - For reCAPTCHA, might set `g-recaptcha-response`.
        - For AWS WAF, we do the clicks directly in solve_captcha().
        """
        if captcha_type == "geetest" and solution:
            # solution might have .challenge, .sec_code, .validate
            script = (
                f'solvedCaptcha({{'
                f'geetest_challenge: "{solution.challenge}",'
                f'geetest_seccode: "{solution.sec_code}",'
                f'geetest_validate: "{solution.validate}",'
                f'data: "{extra_data}"}});'
            )
            driver.execute_script(script)
            sleep(2)

        elif captcha_type == "recaptcha" and solution:
            # Put the token in the <textarea> for reCAPTCHA
            driver.execute_script(
                'document.getElementById("g-recaptcha-response").innerHTML = "{}";'.format(
                    solution.get("code", "")
                )
            )

    def validate_solution(self, captcha_type, driver):
        try:
            driver.find_element(By.TAG_NAME, "awswaf-captcha")
            return False
        except:
            logger.info("Captcha solved")
            return True

    def solve_captcha_on_page(self, driver) -> bool:
        """
        Detects and solves the captcha on the current page.
        Returns True if solved (or if no captcha), False otherwise.
        """
        try:
            captcha_type = self.detect_captcha(driver)
            if not captcha_type:
                logger.info("No CAPTCHA detected.")
                return True  # No captcha => success

            logger.info(f"Detected CAPTCHA type: {captcha_type}")
            captcha_data = self.get_captcha_data(captcha_type, driver)
            solution = self.solve_captcha(
                captcha_type,
                captcha_data,
                driver,
                driver.current_url
            )

            if captcha_type == "geetest":
                extra_data = captcha_data.get("data")
                self.inject_solution(captcha_type, driver, solution, extra_data)
            else:
                self.inject_solution(captcha_type, driver, solution)
        except Exception as e:
            logger.error(f"Error while solving CAPTCHA: {e}", exc_info=True)
            return False
        if self.validate_solution(captcha_type, driver):
            logger.info("CAPTCHA solved successfully.")
            return True
        else:
            return False

