import os
import time
import random
import pickle
import logging
from pathlib import Path
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.common.exceptions import NoSuchElementException, ElementClickInterceptedException
from selenium_stealth import stealth

from dotenv import load_dotenv

logger = logging.getLogger(__name__)
CHROME_PROFILE_PATH = r'C:\Users\flatmaster\AppData\Local\Google\Chrome\User Data'


class StealthBrowser(webdriver.Chrome):
    def __init__(self):
        # Load environment variables
        load_dotenv()
        self.cookies_dir = os.getenv("COOKIES_DIR", "cookies")
        os.makedirs(self.cookies_dir, exist_ok=True)

        self.logs_dir = os.path.join("logs", "StealthBrowserCaptures")
        os.makedirs(self.logs_dir, exist_ok=True)

        options = Options()
        # Set the custom Chrome binary location
        options.binary_location = r"Chrome installers\chrome-win64\chrome-win64\chrome.exe"

        # Add your options
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        options.add_argument("--disable-infobars")
        options.add_argument("--disable-popup-blocking")
        options.add_argument("--disable-notifications")
        options.add_argument("--ignore-certificate-errors")
        options.add_argument("--disable-web-security")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-extensions")
        options.add_argument("--remote-debugging-port=9222")
        options.add_argument(r"--user-data-dir=C:\Users\flatmaster\AppData\Local\Google\Chrome for Testing\User Data\Default")

        # Enable performance logging
        #capabilities = DesiredCapabilities.CHROME
        #capabilities["goog:loggingPrefs"] = {"performance": "ALL"}
        # Combine options with capabilities
        #options.set_capability("goog:loggingPrefs", {"performance": "ALL"})
        options.add_argument(
            "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        )

        # Use ChromeDriverManager to install and set up the driver service
        driver_service = Service(ChromeDriverManager().install())

        # Initialize the WebDriver with the specified service and options
        super().__init__(service=driver_service, options=options)
        stealth ( 
            self,
            languages=["en-US", "en"], #["de", "en-US", "en"],
            vendor="Google Inc.",
            platform="Win64",
            webgl_vendor="Intel Inc.",
            renderer="Intel Iris OpenGL Engine",
            fix_hairline=True,
            )

        
        self.maximize_window()

    def kill(self):
        logging.info("Killing browser")
        self.quit()

    def wait_for_user(self):
        #self.execute_script("window.stop();")
        input("Waiting for user, press Enter to continue...")

    @staticmethod
    def random_wait(min_seconds=2, max_seconds=5):
        wait_time = random.uniform(min_seconds, max_seconds)
        logging.info(f"Waiting for {wait_time:.2f} seconds...")
        time.sleep(wait_time)

    def safe_find_element(self, by, value):
        try:
            return self.find_element(by, value).text.strip()
        except Exception:
            return "Unknown"

    def random_mouse_movements(self, element):
        action = ActionChains(self)
        for _ in range(random.randint(2, 5)):
            offset_x = random.randint(-100, 100)
            offset_y = random.randint(-100, 100)
            action.move_to_element_with_offset(element, offset_x, offset_y).perform()
            logging.info(f"Moved mouse to offset ({offset_x}, {offset_y})")
            self.random_wait(0.5, 1.5)

    def random_scroll(self):
        scroll_amount = random.randint(-300, 300)
        self.execute_script(f"window.scrollBy(0, {scroll_amount})")
        logging.info(f"Scrolled by {scroll_amount} pixels")
        self.random_wait(0.5, 1.5)

    def perform_random_action(self):
        actions = [
            self.random_scroll,
            lambda: self.random_wait(42, 15),
        ]
        action = random.choice(actions)
        action()

    def save_cookies(self, site_name):
        cookie_file = os.path.join(self.cookies_dir, f"{site_name}_cookies.pkl")
        with open(cookie_file, "wb") as f:
            pickle.dump(self.get_cookies(), f)
        logging.info(f"Cookies saved for {site_name}.")

    def load_cookies(self, site_name):
        cookie_file = os.path.join(self.cookies_dir, f"{site_name}_cookies.pkl")
        if os.path.exists(cookie_file):
            with open(cookie_file, "rb") as f:
                cookies = pickle.load(f)
                for cookie in cookies:
                    try:
                        self.add_cookie(cookie)
                    except Exception as e:
                        logging.info(f"Failed to load cookie: {cookie}. Error: {e}")
            logging.info(f"Cookies loaded for {site_name}.")
        else:
            logging.warning(f"No Cookies found for {site_name}.")


    def save_page(self, file_prefix="capture"):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        capture_dir = os.path.join(self.logs_dir, timestamp)
        os.makedirs(capture_dir, exist_ok=True)

        # Save page source
        page_source_file = os.path.join(capture_dir, f"{file_prefix}_source.html")
        with open(page_source_file, "w", encoding="utf-8") as f:
            f.write(self.page_source)
        logging.warning(f"Page source saved: {page_source_file}")

        # Save screenshot
        screenshot_file = os.path.join(capture_dir, f"{file_prefix}_screenshot.jpg")
        self.save_screenshot(screenshot_file)
        logging.warning(f"Screenshot saved: {screenshot_file}")

    def dismiss_overlays(self):
        """Dismiss known overlays like cookie consent banners."""
        try:
            consent_banner = self.find_element(By.ID, "usercentrics-root")
            if consent_banner.is_displayed():
                close_button = consent_banner.find_element(By.TAG_NAME, "button")
                close_button.click()
                print("Overlay dismissed.")
        except NoSuchElementException:
            # Overlay not present, safe to proceed
            print("No overlay found.")

    def scroll_to_bottom(self):
        try:
            self.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            logging.info("Scrolled to the bottom of the page.")
        except Exception as e:
            logging.error(f"Error while scrolling to bottom: {e}")

    def send_keys_human_like(self, field, value, min_delay=0.1, max_delay=0.3):
        for char in value:
            field.send_keys(char)
            time.sleep(random.uniform(min_delay, max_delay))