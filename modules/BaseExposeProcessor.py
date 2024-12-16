import logging
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

    def __init__(self, email, password):
        self.email = email
        self.password = password
        self.database = ExposeDB
        self.ApplicationGenerator = ApplicationGenerator()
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
        expose_id = Expose.expose_id
        offer_link = self._generate_expose_link(Expose)
        logger.info(f"Processing expose: {offer_link}")
        self.stealth_chrome.get(offer_link)
        self.stealth_chrome.load_cookies(self.name)
        self.stealth_chrome.random_wait()

        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            logger.debug(f"Attempt {attempt}...")           

            if self.stealth_chrome.title != "":
                Expose, success = self._handle_page(Expose, self.stealth_chrome)
                if Expose.processed == True:
                    logger.info(f"Attempt {attempt} succeeded!")
                    return Expose, True
                else:
                    logger.debug(f"Attempt {attempt} failed.")
            if attempt < max_attempts:
                logger.debug("Retrying...\n")
                self.stealth_chrome.random_wait()
            else:
                logger.info(f"All attempts failed for expose ID {expose_id}.")
                Expose.failures += 1
                self.stealth_chrome.kill()
                return Expose, False
