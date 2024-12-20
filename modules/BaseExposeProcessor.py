import logging
import time
from modules.Database import ExposeDB
from modules.Expose import Expose
from modules.ApplicationGenerator import ApplicationGenerator
from dotenv import load_dotenv
from modules.StealthBrowser import StealthBrowser
from datetime import datetime

logger = logging.getLogger(__name__)


# Base class for real estate automation
class BaseExposeProcessor:
    name = "BaseProcessor"
    domain = "BaseDomain"
    ApplicationGenerator = ApplicationGenerator()

    def __init__(self, email, password):
        self.email = email
        self.password = password
        self.stealth_chrome = StealthBrowser()
        

    def get_name(self):
        return self.name
    
    def get_domain(self):
        return self.domain
    
    def set_application_text(self, application_text):
        self.application_text = application_text
    
    @staticmethod
    def extract_expose_link(subject, email_body):
        raise NotImplementedError
    
    @staticmethod
    def _generate_expose_link(Expose):
        raise NotImplementedError
    
    #Returns updated Expose object
    def _handle_page(self, Expose, StealthBrowser):
        logger.error(self.name)
        raise NotImplementedError

    #Returns updated Expose object
    def process_expose(self, Expose):
        logger.info(f"Processing expose: {Expose.expose_id}")
        max_attempts = 4
        for attempt in range(1, max_attempts + 1):
            logger.info(f"Attempt {attempt}...")
            offer_link = self._generate_expose_link(Expose)
            self.stealth_chrome.get(offer_link)
            self.stealth_chrome.load_cookies(self.name)
            self.stealth_chrome.random_wait()
            self.stealth_chrome.random_scroll()
            self.stealth_chrome.random_wait()

            Expose, success = self._handle_page(Expose)
            if Expose.processed == True:
                logger.warning(f"Attempt {attempt} succeeded!")
                return Expose, True
            else:
                logger.info(f"Attempt {attempt} failed.")
            if attempt < max_attempts:
                logger.info("Retrying...\n")
                self.stealth_chrome.random_wait(5,20)
            else:
                logger.warning(f"All attempts failed.")
                Expose.failures += 1
                self.stealth_chrome.kill()
                return Expose, False
