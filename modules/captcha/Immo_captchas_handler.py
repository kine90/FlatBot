import os
import re
from io import BytesIO
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
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from modules.captcha.twocaptcha_solver import TwoCaptchaSolver, GeetestResponse, RecaptchaResponse, CaptchaUnsolvableError, CaptchaBalanceEmpty
from modules.StealthBrowser import StealthBrowser

logger = logging.getLogger(__name__)

class ImmoCaptchaHandler:
    """
    Handles detection and solving of various Captcha types:
    - GeeTest
    - reCAPTCHA
    - AWS WAF puzzle

    """

    def __init__(self):
        # Load API key from .env
        load_dotenv()
        api_key = os.getenv("2CAPTCHA_API_KEY")
        if not api_key:
            logger.warning("2CAPTCHA_API_KEY not found in .env.")
        self.captcha_solver = TwoCaptchaSolver(api_key)

        return None

    def handle_captchas(self, driver: StealthBrowser):
        logger.debug("Trying to handle captcha")
        attempts = 0
        max_attempts = 3
        while attempts < max_attempts:
            attempts += 1
            try:
                captcha_type = self.detect_captcha(driver)
                if not captcha_type:
                    logging.info("No captcha detected, returning.")
                    return True  # No captcha => success

                elif captcha_type == "geetest":
                    self._resolve_geetest()
                elif captcha_type == "recaptcha":
                    self._resolve_recaptcha(driver)
                elif captcha_type == "awswaf":
                    self._resolve_awswaf(driver)

                StealthBrowser.random_wait(3,6)

            except Exception as e:
                logger.error(f"Error while solving CAPTCHA: {e}", exc_info=True)
                #self.stealth_chrome.refresh()

        logger.error("All attempts to solve CAPTCHA failed.")
        return False

    def detect_captcha(self, driver: StealthBrowser) -> str:
        """
        Checks the page source for known Captcha indicators.
        Returns a string identifier of the captcha type ('geetest', 
        'recaptcha', 'awswaf') or None if none found.
        """
        page_source = driver.page_source.lower()
        type = None
        if "initgeetest" in page_source:
            type = "geetest"
        if "g-recaptcha" in page_source:
            type = "recaptcha"
        if "awswaf" in page_source:
            try:
                # Access shadow root
                shadow_element = driver.execute_script(
                    "return document.querySelector('awswaf-captcha').shadowRoot"
                )
                type = "awswaf"
            except:
                logging.info("No shadowroot element for awswaf captcha detection")
        logging.info(f"Detected {type} type captcha.")
        return type

    def _resolve_geetest(self, driver: StealthBrowser):
        """Resolve GeeTest Captcha"""
        logging.info("Resolving Geetest")
        data = re.findall(
            "geetest_validate: obj.geetest_validate,\n.*?data: \"(.*)\"",
            driver.page_source
        )[0]
        result = re.findall(
            r"initGeetest\({(.*?)}", driver.page_source, re.DOTALL)
        geetest = re.findall("gt: \"(.*?)\"", result[0])[0]
        challenge = re.findall("challenge: \"(.*?)\"", result[0])[0]
        try:
            captcha_response = self.captcha_solver.get_geetest_solution(
                geetest,
                challenge,
                driver.current_url
            )
            script = (f'solvedCaptcha({{geetest_challenge: "{captcha_response.challenge}",'
                      f'geetest_seccode: "{captcha_response.sec_code}",'
                      f'geetest_validate: "{captcha_response.validate}",'
                      f'data: "{data}"}});')
            driver.execute_script(script)
            sleep(2)
        except CaptchaUnsolvableError:
            driver.refresh()
            raise

    def _resolve_awswaf(self, driver: StealthBrowser):
        logging.info("Resolving AwsWaf")
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
            result = self.captcha_solver.get_awswaf_solution(base64_screenshot)

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
                sleep(0.3)
                actions.reset_actions()

            sleep(1)
            try:
                confirm_button = my_img.find_element(By.ID, "amzn-btn-verify-internal")
                actions.move_to_element_with_offset(confirm_button, 40, 15).click()
                actions.perform()
                sleep(4)
            except:
                return

        except Exception as e:
            logger.error(f"Error solving AWS WAF CAPTCHA: {e}", exc_info=True)
            return
        
    def _resolve_recaptcha(self, driver: StealthBrowser, checkbox: bool = False, afterlogin_string: str = ""):
        logging.info("Resolving ReCaptcha")
        """Resolve Captcha"""
        iframe_present = self._wait_for_iframe(driver)
        if checkbox is False and afterlogin_string == "" and iframe_present:

            google_site_key = driver \
                .find_element_by_class_name("g-recaptcha") \
                .get_attribute("data-sitekey")
            try:
                captcha_result = self.captcha_solver.get_recaptcha_solution(
                    google_site_key,
                    driver.current_url
                ).result
                driver.execute_script(
                    f'document.getElementById("g-recaptcha-response").innerHTML="{captcha_result}";'
                )
                #  Below function call can be different depending on the websites
                #  implementation. It is responsible for sending the promise that we
                #  get from recaptcha_answer. For now, if it breaks, it is required to
                #  reverse engineer it by hand. Not sure if there is a way to automate it.
                driver.execute_script(f'solvedCaptcha("{captcha_result}")')
                self._wait_until_iframe_disappears(driver)
            except CaptchaUnsolvableError:
                driver.refresh()
                raise
        else:
            if checkbox:
                self._clickcaptcha(driver, checkbox)
            else:
                self._wait_for_captcha_resolution(
                    driver, checkbox, afterlogin_string)
                
    def _clickcaptcha(self, driver: StealthBrowser, checkbox: bool):
        driver.switch_to.frame(driver.find_element_by_tag_name("iframe"))
        recaptcha_checkbox = driver.find_element_by_class_name(
            "recaptcha-checkbox-checkmark")
        driver.click_with_random_offset(recaptcha_checkbox)
        self._wait_for_captcha_resolution(driver, checkbox)
        driver.switch_to.default_content()

    def _wait_for_captcha_resolution(self, driver, checkbox: bool, afterlogin_string=""):
        if checkbox:
            try:
                WebDriverWait(driver, 120).until(
                    EC.visibility_of_element_located(
                        (By.CLASS_NAME, "recaptcha-checkbox-checked"))
                )
            except TimeoutException:
                logger.warning(
                    "Selenium.Timeoutexception when waiting for captcha to appear")
        else:
            xpath_string = f"//*[contains(text(), '{afterlogin_string}')]"
            try:
                WebDriverWait(driver, 120) \
                    .until(EC.visibility_of_element_located((By.XPATH, xpath_string)))
            except TimeoutException:
                logger.warning(
                    "Selenium.Timeoutexception when waiting for captcha to disappear")
                
    def _wait_for_iframe(self, driver: StealthBrowser):
        """Wait for iFrame to appear"""
        try:
            iframe = WebDriverWait(driver, 10).until(EC.visibility_of_element_located(
                (By.CSS_SELECTOR, "iframe[src^='https://www.google.com/recaptcha/api2/anchor?']")))
            return iframe
        except NoSuchElementException:
            logger.info(
                "No iframe found, therefore no chaptcha verification necessary")
            return None
        except TimeoutException:
            logger.info(
                "Timeout waiting for iframe element - no captcha verification necessary?")
            return None
        
    def _wait_until_iframe_disappears(self, driver: StealthBrowser):
        """Wait for iFrame to disappear"""
        try:
            WebDriverWait(driver, 10).until(EC.invisibility_of_element(
                (By.CSS_SELECTOR, "iframe[src^='https://www.google.com/recaptcha/api2/anchor?']")))
        except NoSuchElementException:
            logger.warning("Element not found")
