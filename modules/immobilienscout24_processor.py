import os
import base64
import re
import logging
from datetime import datetime
from modules.Expose import Expose
from modules.BaseExposeProcessor import BaseExposeProcessor
from modules.StealthBrowser import StealthBrowser
from modules.captcha.captcha_tester import CaptchaTester
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

class Immobilienscout24_processor(BaseExposeProcessor):
    name = "Immobilienscout24"
    domain = "immobilienscout24.de"

    def __init__(self, stealthbrowser):
   
        # Load environment variables
        load_dotenv()
        IMMO_EMAIL = base64.b64decode(os.getenv("IMMO_EMAIL")).decode("utf-8")
        IMMO_PASSWORD = base64.b64decode(os.getenv("IMMO_PASSWORD")).decode("utf-8")

        super().__init__(IMMO_EMAIL, IMMO_PASSWORD, stealthbrowser)

        self.immo_page_titles = {
            "captcha_wall": "Ich bin kein Roboter",
            "offer_expired": "Angebot nicht gefunden",
            "offer_deactivated": "Angebot wurde deaktiviert",
            "login_page": "Welcome - ImmobilienScout24",
            "error_page": "Fehler",
            "home_page": "ImmoScout24 – Die Nr. 1 für Immobilien"
        }

    @staticmethod
    def extract_expose_link(subject, email_body):
        #Extract unique expose links from the email body specific to Immobilienscout24#

    	# Filter Keywords
        subject_keywords = {"angebot", "offer"}

        # Normalize keywords to lowercase for consistent matching
        subject_keywords = {keyword.lower() for keyword in subject_keywords}

        # Check subject filter before processing
        subject_lower = subject.lower()
        if not any(keyword in subject_lower for keyword in subject_keywords):
            return []

        # Extract expose links using a regex pattern
        pattern = re.compile(r"https:\/\/[a-zA-Z0-9./?=&_-]*expose/(\d+)")
        return list(set(pattern.findall(email_body)))
    
    @staticmethod
    def _generate_expose_link(Expose):
        offer_link = f"https://push.search.is24.de/email/expose/{Expose.expose_id}"
        return offer_link

    #Returns updated Expose object, called in process_expose
    def _handle_page(self, Expose):
        page_title = self.stealth_chrome.title
        logger.info(f"Page title: {page_title}")
        self._accept_cookies()
        if self.immo_page_titles['captcha_wall'] in page_title:
            self._handle_captcha()
            #return Expose, False
        elif self.immo_page_titles['offer_expired'] in page_title or self.immo_page_titles['offer_deactivated'] in page_title:
            logger.info("Offer expired or deactivated, skipping.")
            Expose.processed = True
            logger.info(f"Expose {Expose.expose_id} marked as processed.")
            return Expose, False
        elif self.immo_page_titles['login_page'] in page_title:
            logger.warning("Login page detected, attempting login.")
            self._perform_login()
        elif self.immo_page_titles['error_page'] in page_title or self.immo_page_titles['home_page'] in page_title:
            logger.warning("Error or landed on home page, skipping.")
            return Expose, False
        self.stealth_chrome.perform_random_action()
        self._accept_cookies()
        # Could be a good offer, let´s check
        #Can we scrape it?
        Expose, scraped = self._scrape_expose(Expose)
        if not scraped:
            return Expose, False

        # Are we logged in?
        if not self._check_login():
            self._perform_login()
            return Expose, False
        
        # Can we apply?
        self._accept_cookies()
        Expose, applied = self._apply_for_offer(Expose)
        if not applied:
            return Expose, False      
        return Expose, True

    ###############################
    ####### IMMO FUNCTIONS ########
    ###############################
    
    def _check_login(self):
        # Check login status based on page elements
        try:
            login_header = self.stealth_chrome.find_element(By.CLASS_NAME, "topnavigation__sso-login__header")
            if login_header and "angemeldet als" in login_header.text:
                logger.info("User already logged in.")
                return True
        except Exception:
            logger.info("User does not seems to be logged in")
            return False
        
    def _perform_login(self):
        self.stealth_chrome.dismiss_overlays()
        try:
            login_link = self.stealth_chrome.find_element(By.CLASS_NAME, "topnavigation__sso-login__middle")
            if login_link and "Anmelden" in login_link.text:
                logger.info("User not logged in. Attempting login.")
                login_link.click()
                StealthBrowser.random_wait()
                try:
                    self._handle_captcha()
                except:
                    pass
                try:
                    StealthBrowser.random_wait()
                    email_field = WebDriverWait(self.stealth_chrome, 10).until(
                        EC.presence_of_element_located((By.ID, "username"))
                    )
                    self.stealth_chrome.send_keys_human_like(email_field, self.email)
                    logger.info("Email entered successfully.")
                    self.stealth_chrome.perform_random_action()

                    submit_button = WebDriverWait(self.stealth_chrome, 10).until(
                        EC.presence_of_element_located((By.ID, "submit"))
                    )
                    self.stealth_chrome.random_mouse_movements(submit_button)
                    self.stealth_chrome.dismiss_overlays()
                    submit_button.click()
                    logger.info("Email submission successful, waiting for password field.")

                    StealthBrowser.random_wait()
                    try:
                        self._handle_captcha()
                    except:
                        pass
                    password_field = WebDriverWait(self.stealth_chrome, 10).until(
                        EC.presence_of_element_located((By.ID, "password"))
                    )
                    self.stealth_chrome.send_keys_human_like(password_field, self.password)
                    logger.info("Password entered successfully.")
                    self.stealth_chrome.perform_random_action()

                    remember_me_checkbox = WebDriverWait(self.stealth_chrome, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "label[for='rememberMeCheckBox']"))
                    )
                    self.stealth_chrome.random_mouse_movements(remember_me_checkbox)
                    #remember_me_checkbox.click()
                    #logger.info("'Remember Me' checkbox selected.")
                    self.stealth_chrome.perform_random_action()
                    login_button = WebDriverWait(self.stealth_chrome, 10).until(
                        EC.presence_of_element_located((By.ID, "loginOrRegistration"))
                    )
                    self.stealth_chrome.random_mouse_movements(login_button)
                    self.stealth_chrome.dismiss_overlays()
                    login_button.click()
                    logger.info("Login submitted successfully.")
                    StealthBrowser.random_wait(5,10)

                    ## TO-DO validate success

                    #self.stealth_chrome.save_cookies(self.name)
                    #self.stealth_chrome.refresh()
                    logger.info("Page reloaded after login.")
                    return True
                except Exception as e:
                    logger.warning("Login failed.", e)
                    #self.stealth_chrome_helpers.wait_for_user()
                    # TO-DO Notify user
                    return False                           
        except Exception:
            logger.info("Login button not found.", e)
            #self.stealth_chrome_helpers.wait_for_user()
            # TO-DO Notify user
            return False
        

    def _scrape_expose(self, Expose):
        # Check title
        logger.info(f"Fetched scraped_at from DB: {Expose.scraped_at}, Type: {type(Expose.scraped_at)}")
        if Expose.scraped_at is None:
            logger.info(f"Scraping Expose {Expose.expose_id}")
            try:
                offer_title = self.stealth_chrome.safe_find_element(By.ID, "expose-title")

                if offer_title != "Unknown":
                    logger.info("Found Offer title, scriping the rest.")
                    logger.info(f"Scrape time: {datetime.utcnow()}")
                    Expose.location = self.stealth_chrome.safe_find_element(By.CLASS_NAME, "zip-region-and-country")
                    Expose.agent_name = self.stealth_chrome.safe_find_element(By.CLASS_NAME, "truncateChild_5TDve")
                    Expose.real_estate_agency = self.stealth_chrome.safe_find_element(By.CSS_SELECTOR, "p[data-qa='company-name']")
                    Expose.price_kalt = self.stealth_chrome.safe_find_element(By.CLASS_NAME, "is24-preis-value")
                    Expose.square_meters = self.stealth_chrome.safe_find_element(By.CLASS_NAME, "is24qa-wohnflaeche-main")
                    Expose.number_of_rooms = self.stealth_chrome.safe_find_element(By.CLASS_NAME, "is24qa-zi-main")
                    Expose.nebekosten = self.stealth_chrome.safe_find_element(By.CLASS_NAME, "is24qa-nebenkosten")
                    Expose.price_warm = self.stealth_chrome.safe_find_element(By.CSS_SELECTOR, "dd.is24qa-gesamtmiete")
                    Expose.construction_year = self.stealth_chrome.safe_find_element(By.CLASS_NAME, "is24qa-baujahr")
                    Expose.description = self.stealth_chrome.safe_find_element(By.CLASS_NAME, "is24qa-objektbeschreibung")
                    Expose.neighborhood = self.stealth_chrome.safe_find_element(By.CLASS_NAME, "is24qa-lage")
                    Expose.scraped_at = datetime.utcnow()
                    logger.info(f"Expose {Expose.expose_id} scraped to database.")
                    self.stealth_chrome.perform_random_action()
                    return Expose, True
                else:
                    logger.warning("No valid offer title found!")
            except Exception:
                logger.warning("Scrape failed, bad attempt!")
                return Expose, False
        else:
            logger.info(f"Expose {Expose.expose_id} already scraped")
            return Expose, True

    def _apply_for_offer(self, Expose):
        logger.info("Trying application...")
        try:
            message_button = WebDriverWait(self.stealth_chrome, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, "Button_button-primary__6QTnx"))
            )
            self.stealth_chrome.dismiss_overlays()
            message_button.click()
            logger.info("Message button found and clicked successfully.")
        except Exception as e:
            logger.info("Failed to find or click message button.")
            return Expose, False

        self.stealth_chrome.perform_random_action()

        if "Welcome - ImmobilienScout24" in self.stealth_chrome.title:
            logger.info("User not logged in. Bad attempt")
            return Expose, False

        if "MieterPlus freischalten | ImmoScout24" in self.stealth_chrome.title:
            logger.info("MieterPlus page detected. Skipping expose.")
            # moved in process_expose
            #database.mark_expose_as_processed(expose_id)
            logger.info(f"Expose {Expose.expose_id} marked as processed.")
            Expose.processed = True
            return Expose, True

        try:
            StealthBrowser.random_wait()
            message_label = WebDriverWait(self.stealth_chrome, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "label[for='message']"))
            )
            message_box = self.stealth_chrome.find_element(By.ID, "message")
            message_box.clear()
        except:
            logger.warning("Message pop-up did not open or message box not found, bad attempt")
            return Expose, False

        self._fill_application_form(Expose)
        logger.info("Application text entered successfully.")

        self.stealth_chrome.perform_random_action()
        try:
            send_button = WebDriverWait(self.stealth_chrome, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "button[type='submit'].Button_button-primary__6QTnx"))
            )
            self.stealth_chrome.execute_script("arguments[0].scrollIntoView(true);", send_button)
            self.stealth_chrome.dismiss_overlays()
            send_button.click()
            logger.info("Submit clicked, waiting for confirmation.")
        except:
            logger.info("Submit not fount!")
            return Expose, False

        confirmation_message = WebDriverWait(self.stealth_chrome, 10).until(
            EC.presence_of_element_located((By.XPATH, "//h2[text()='Nachricht gesendet']"))
        )
        if confirmation_message:
            # moved in process_expose
            #database.mark_expose_as_processed(expose_id)
            logger.info(f"Expose {Expose.expose_id} applied succesfully.")
            Expose.applied_at = datetime.utcnow()
            Expose.processed = True
            # TO-DO Notify user?
            return Expose, True
        else:
            # TO-DO Handle unfilled form fields
            logger.warning("Failed to send message or fill the form.", e)
            return Expose, False

    def _fill_application_form(self, Expose):
        """
        Example improved method to handle form fields that appear dynamically 
        as you scroll or interact with the page.
        """

        self.stealth_chrome.dismiss_overlays()

        # 1) Scroll in increments until no more new content
        self._scroll_in_increments()

        # 2) Wait for a known element to confirm the form is loaded
        try:
            WebDriverWait(self.stealth_chrome, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "label[for='message']"))
            )
        except Exception as e:
            logger.warning(f"Application form not fully loaded (or timed out): {e}")
            return

        # 3) Get (visible) form fields
        visible_fields = self._get_all_visible_form_fields()

        # Print them once for debugging (optional)
        for f in visible_fields:
            field_name = f.get_attribute("name")
            field_type_attr = f.get_attribute("type")
            if f.tag_name.lower() == "select":
                field_type = "select"
            else:
                field_type = field_type_attr.lower() if field_type_attr else f.tag_name.lower()
            logger.info(f"Found field: name={field_name}, type={field_type}")

        # 4) Fill fields
        # Use the same "form_values" list from your code
        form_values = [
            ("vonplz", "text", os.getenv("APPLICANT_POST_CODE")),
            ("nachplz", "text", ""),
            ("message", "textarea", self.ApplicationGenerator.generate_application(Expose)),
            ("salutation", "text", os.getenv("APPLICANT_SALUTATION")),
            ("salutation", "select", os.getenv("APPLICANT_SALUTATION")),
            ("firstName", "text", os.getenv("APPLICANT_NAME")),
            ("lastName", "text", os.getenv("APPLICANT_SURNAME")),
            ("phoneNumber", "tel", os.getenv("APPLICANT_PHONE")),
            ("phoneNumber", "text",  os.getenv("APPLICANT_PHONE")),
            ("phoneNumber", "number",  os.getenv("APPLICANT_PHONE")),
            ("emailAddress", "email",  os.getenv("APPLICANT_EMAIL")),
            ("emailAddress", "text",  os.getenv("APPLICANT_EMAIL")),
            ("street", "text", os.getenv("APPLICANT_STREET")),
            ("houseNumber", "text", os.getenv("APPLICANT_HOUSE_NUM")),
            ("postcode", "text", os.getenv("APPLICANT_POST_CODE")),
            ("city", "text", os.getenv("APPLICANT_CITY")),
            ("moveInDateType", "text", os.getenv("APPLICANT_MOVEIN_DATE_TYPE")),
            ("moveInDateType", "select", os.getenv("APPLICANT_MOVEIN_DATE_TYPE")),
            ("numberOfPersons", "text", os.getenv("APPLICANT_NUM_PERSONS")),
            ("numberOfPersons", "select", os.getenv("APPLICANT_NUM_PERSONS")),
            ("employmentRelationship", "text", os.getenv("APPLICANT_EMPLOYEMENT_RELATIONSHIP")),
            ("employmentRelationship", "select", os.getenv("APPLICANT_EMPLOYEMENT_RELATIONSHIP")),
            ("employmentStatus", "select",  os.getenv("APPLICANT_EMPLOYEMENT_STATUS")),
            ("employmentStatus", "text",  os.getenv("APPLICANT_EMPLOYEMENT_STATUS")),
            ("income", "select", os.getenv("APPLICANT_INCOME_RANGE")),
            ("incomeAmount", "tel", os.getenv("APPLICANT_INCOME_AMMOUNT")),
            ("incomeAmount", "text", os.getenv("APPLICANT_INCOME_AMMOUNT")),
            ("incomeAmount", "number", os.getenv("APPLICANT_INCOME_AMMOUNT")),
            ("applicationPackageCompleted", "text", os.getenv("APPLICANT_DOCUMENTS_AVAILABLE")),
            ("applicationPackageCompleted", "select", os.getenv("APPLICANT_DOCUMENTS_AVAILABLE")),
            ("hasPets", "text", os.getenv("APPLICANT_HAS_PETS")),
            ("hasPets", "select", os.getenv("APPLICANT_HAS_PETS")),
            ("sendUser", "checkbox", os.getenv("APPLICANT_SEND_PROFILE")),
            ("sendUserProfile", "checkbox", os.getenv("APPLICANT_SEND_PROFILE")),
            ("numberOfAdults", "number", os.getenv("APPLICANT_NUM_ADULTS")),
            ("numberOfAdults", "tel", os.getenv("APPLICANT_NUM_ADULTS")),
            ("numberOfKids", "number",  os.getenv("APPLICANT_NUM_KIDS")),
            ("numberOfKids", "tel", os.getenv("APPLICANT_NUM_KIDS")),
            ("isRelocationOfferChecked", "checkbox", "false"),
            ("rentArrears", "select", os.getenv("APPLICANT_RENT_ARREARS")),
            ("insolvencyProcess", "select", os.getenv("APPLICANT_INSOLVENCY_PROCESS")),
        ]

        for field in visible_fields:
            field_name = field.get_attribute("name")
            # Determine actual field type
            if field.tag_name.lower() == "select":
                field_type = "select"
            else:
                field_type_attr = field.get_attribute("type")
                field_type = field_type_attr.lower() if field_type_attr else field.tag_name.lower()

            for name, expected_type, value in form_values:
                # Match field name and type
                if field_name == name and field_type == expected_type:
                    try:
                        # Scroll this element into view before interacting
                        self.stealth_chrome.execute_script("arguments[0].scrollIntoView({block: 'center'});", field)
                        StealthBrowser.random_wait(0.5, 1)  # give time to settle
                        self.stealth_chrome.random_mouse_movements(field)

                        if field_type in ["text", "email", "tel", "number"] or field.tag_name.lower() == "textarea":
                            field.clear()
                            self.stealth_chrome.send_keys_human_like(field, value)
                            StealthBrowser.random_wait()

                        elif field_type == "select":
                            Select(field).select_by_visible_text(value)
                            StealthBrowser.random_wait()

                        elif field_type == "checkbox":
                            current_state = field.is_selected()
                            if value.lower() in ["true", "yes", "1"] and not current_state:
                                field.click()
                            elif value.lower() in ["false", "no", "0"] and current_state:
                                field.click()
                            StealthBrowser.random_wait(1,3)

                    except Exception as e:
                        logger.warning(f"Could not fill field '{field_name}' (type={field_type}): {e}")

        # 5) (Optional) Re-check or re-scroll if new fields appear after the first pass
        self._scroll_in_increments()
        # If you know new fields appear only after certain fields are filled, 
        # you could re-collect and fill again here.

        logger.info("Form filling completed.")


    def _scroll_in_increments(self):
        """
        Scroll the page in increments to ensure all dynamic content is fully loaded.
        """
        last_height = self.stealth_chrome.execute_script("return document.body.scrollHeight")
        while True:
            self.stealth_chrome.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            StealthBrowser.random_wait(2, 4)  # Adjust wait as needed
            new_height = self.stealth_chrome.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height


    def _get_all_visible_form_fields(self):
        """
        Return a list of only the visible input, textarea, and select fields.
        Hidden fields are skipped.
        """
        all_inputs = self.stealth_chrome.find_elements(By.TAG_NAME, "input")
        all_textareas = self.stealth_chrome.find_elements(By.TAG_NAME, "textarea")
        all_selects = self.stealth_chrome.find_elements(By.TAG_NAME, "select")
        
        all_fields = all_inputs + all_textareas + all_selects
        
        visible_fields = []
        for field in all_fields:
            # skip hidden or invisible
            if field.is_displayed() and field.get_attribute("type") != "hidden":
                visible_fields.append(field)
        
        return visible_fields

    def _accept_cookies(self):
        try:
            shadow_root = self.stealth_chrome.find_element(By.CSS_SELECTOR, "#usercentrics-root").shadow_root
            button = shadow_root.find_element(By.CSS_SELECTOR, "button[data-testid='uc-accept-all-button']")
            self.stealth_chrome.random_mouse_movements(button)
            button.click()
            logging.info("Successfully clicked the 'Accept All' button.")
        except:
            logging.info("Failed to click the 'Accept All' button")

    def _handle_captcha(self):
        logger.warning("Captcha detected.")
        attempts = 0
        max_attempts = 3
        while attempts < max_attempts:
            try:
                logger.info("Loading solver")
                tester = CaptchaTester()
                captcha_type = tester.detect_captcha(self.stealth_chrome)
                
                if not captcha_type:
                    logger.info("No CAPTCHA detected.")
                    return True  # No captcha => success

                logger.info(f"Detected CAPTCHA type: {captcha_type}")
                captcha_data = tester.get_captcha_data(captcha_type, self.stealth_chrome)
                solution = tester.solve_captcha(
                    captcha_type,
                    captcha_data,
                    self.stealth_chrome,
                    self.stealth_chrome.current_url
                )

                if captcha_type == "geetest":
                    extra_data = captcha_data.get("data")
                    tester.inject_solution(captcha_type, self.stealth_chrome, solution, extra_data)
                else:
                    tester.inject_solution(captcha_type, self.stealth_chrome, solution)

                if tester.validate_solution(captcha_type, self.stealth_chrome):
                    logger.info("CAPTCHA solved successfully.")
                    return True
                else:
                    logger.error("Failed to solve CAPTCHA, retrying...")
                    self.stealth_chrome.refresh()
                    attempts += 1

            except Exception as e:
                logger.error(f"Error while solving CAPTCHA: {e}", exc_info=True)
                self.stealth_chrome.refresh()
                attempts += 1

        logger.error("All attempts to solve CAPTCHA failed.")
        return False

        StealthBrowser.random_wait(1,3)

