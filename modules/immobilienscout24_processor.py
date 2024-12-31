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
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.support.ui import Select

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

class Immobilienscout24_processor(BaseExposeProcessor):
    name = "Immobilienscout24"
    domain = "immobilienscout24.de"
    # Offers email subject filter
    subject_filter = {"angebot", "offer"}
    #Relevant page titles
    page_titles = {
            "captcha_wall": "Ich bin kein Roboter",
            "offer_expired": "Angebot nicht gefunden",
            "offer_deactivated": "Angebot wurde deaktiviert",
            "login_page": "Welcome - ImmobilienScout24",
            "error_page": "Fehler",
            "home_page": "ImmoScout24 – Die Nr. 1 für Immobilien"
        }

    def __init__(self, stealthbrowser):
        # Load environment variables
        load_dotenv()
        IMMO_EMAIL = os.getenv("IMMO_EMAIL")
        IMMO_PASSWORD = os.getenv("IMMO_PASSWORD")
        self.premium = os.getenv("IMMO_PREMIUM", "False").lower() == "true"
        super().__init__(IMMO_EMAIL, IMMO_PASSWORD, stealthbrowser)

    #Extracts unique expose links from the email body specific to Immobilienscout24 and returns them as list
    @staticmethod
    def extract_expose_link(subject, email_body):
        # Normalize keywords to lowercase for consistent matching
        subject_keywords = {keyword.lower() for keyword in Immobilienscout24_processor.subject_filter}

        # Check subject filter before processing
        subject_lower = subject.lower()
        if not any(keyword in subject_lower for keyword in subject_keywords):
            return []

        # Extract expose links using a regex pattern
        pattern = re.compile(r"https:\/\/[a-zA-Z0-9./?=&_-]*expose/(\d+)")
        return list(set(pattern.findall(email_body)))
    
    # Takes an exposeID and returns the link to the page as sent in an email
    @staticmethod
    def _generate_expose_link(Expose):
        offer_link = f"https://push.search.is24.de/email/expose/{Expose.expose_id}&immoTypeId=0&utm_medium=email&utm_source=system&utm_campaign=fulfillment_update&utm_content=expose_link&referrer=ff_listing"
        return offer_link

    #updates expose, called in process_expose
    def _handle_page(self, Expose: Expose):
        page_title = self.stealth_chrome.title
        logger.info(f"Page title: {page_title}")
        self._accept_cookies()
        if Immobilienscout24_processor.page_titles['captcha_wall'] in page_title:
            self._solve_captcha()
        elif Immobilienscout24_processor.page_titles['offer_expired'] in page_title or Immobilienscout24_processor.page_titles['offer_deactivated'] in page_title:
            logger.info("Offer expired or deactivated, skipping.")
            Expose.processed = True
            logger.info(f"Expose {Expose.expose_id} marked as processed.")
            return
        elif Immobilienscout24_processor.page_titles['login_page'] in page_title:
            logger.warning("Login page detected, attempting login.")
            self._perform_login()
        elif Immobilienscout24_processor.page_titles['error_page'] in page_title or Immobilienscout24_processor.page_titles['home_page'] in page_title:
            logger.warning("Error or landed on home page, skipping attempt.")
            return
        
        # Are we logged in?
        if not self._check_login():
            self._perform_login()
            # After a login we are redirected to our profile page, abort to start a new attempt and refresh the expose link
            return
        
        #Do something random as an human would
        self.stealth_chrome.perform_random_action()

        # After login or captcha we may need to accept cookies, let´s check again
        self._accept_cookies()
        
        # At this point we could be on a valid offer page, let´s validate
        if not self._has_expose_title():
            # If not there is some issue, abort the attempt
            return
        
        # Validated, let´s scrape it
        if self._scrape_expose(Expose):
            # and try to apply
            self._apply_for_offer(Expose)     
        return

    ###############################
    ####### IMMO FUNCTIONS ########
    ###############################
    
    # Check login status based on page elements, returns boolean
    def _check_login(self):
        try:
            login_header = self.stealth_chrome.find_element(By.CLASS_NAME, "topnavigation__sso-login__header")
            if login_header and "angemeldet als" in login_header.text:
                logger.info("User already logged in.")
                return True
        except Exception:
            logger.debug("User does not seems to be logged in")
            return False

    # Performs Login, returns boolean for success    
    def _perform_login(self):
        self.stealth_chrome.dismiss_overlays()
        try:
            login_link = self.stealth_chrome.find_element(By.CLASS_NAME, "topnavigation__sso-login__middle")
            if login_link and "Anmelden" in login_link.text:
                logger.info("User not logged in. Attempting login.")
                login_link.click()
                StealthBrowser.random_wait()
                try:
                    # sometimes we get a captcha
                    self._solve_captcha()
                except:
                    pass
                # At this point we should be good to go
                try:
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
                    #self.stealth_chrome.dismiss_overlays()
                    submit_button.click()
                    logger.info("Email submission successful, waiting for password field.")

                    StealthBrowser.random_wait()
                    try:
                        self._solve_captcha()
                    except:
                        pass

                    password_field = WebDriverWait(self.stealth_chrome, 10).until(
                        EC.presence_of_element_located((By.ID, "password"))
                    )
                    self.stealth_chrome.send_keys_human_like(password_field, self.password)
                    logger.info("Password entered successfully.")
                    self.stealth_chrome.perform_random_action()

                    checkbox_input = WebDriverWait(self.stealth_chrome, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "#rememberMeCheckBox"))
                    )

                    # Wait until the label is present (if you need to click the label instead of the input)
                    remember_me_label = WebDriverWait(self.stealth_chrome, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "label[for='rememberMeCheckBox']"))
                    )

                    # Check if the checkbox is already selected
                    if not checkbox_input.is_selected():
                        # If not selected, click the label (or checkbox_input) to select it
                        remember_me_label.click()
                        logger.info("'Remember Me' checkbox was not selected. Selecting it now.")
                    else:
                        logger.debug("'Remember Me' checkbox is already selected. No action taken.")
                                            
                    login_button = WebDriverWait(self.stealth_chrome, 10).until(
                        EC.presence_of_element_located((By.ID, "loginOrRegistration"))
                    )
                    self.stealth_chrome.random_mouse_movements(login_button)
                    self.stealth_chrome.dismiss_overlays()
                    login_button.click()
                    logger.info("Login submitted successfully.")

                    StealthBrowser.random_wait(5,10)
                    ## TO-DO validate success
                    return True
                except Exception as e:
                    logger.warning("Login failed.", e)
                    # TO-DO Notify user
                    return False                           
        except Exception:
            logger.info("Login button not found.", e)
            #self.stealth_chrome_helpers.wait_for_user()
            # TO-DO Notify user
            return False
    
    # Checks if there is a valid offer title in the page, returns boolean
    def _has_expose_title(self):
        try:
            offer_title = self.stealth_chrome.safe_find_element(By.ID, "expose-title")
            return True
        except NoSuchElementException:
            logger.warning("Could not find offer title in page.")
            return False

    # Scrapes the expose details, updates the Expose and returns a boolean for success or if already scraped  
    def _scrape_expose(self, Expose: Expose):
        
        #logger.info(f"Fetched scraped_at from DB: {Expose.scraped_at}, Type: {type(Expose.scraped_at)}")
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
                    logger.info(f"Expose {Expose.expose_id} scraped")
                    self.stealth_chrome.perform_random_action()
                    return True
                else:
                    logger.warning("No valid offer title found, scraping aborted!")
                    return False
            except Exception:
                logger.warning("Scrape failed, bad attempt!")
                return False
        else:
            logger.info(f"Expose {Expose.expose_id} already scraped")
            return True

    # Applies for an offer, updates the expose and returns boolean for success
    def _apply_for_offer(self, Expose: Expose):
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
            return False

        self.stealth_chrome.perform_random_action()

        if "Welcome - ImmobilienScout24" in self.stealth_chrome.title:
            logger.info("User not logged in. Bad attempt")
            return False

        #This happens if we are not logged in, or if we have not premium
        if "MieterPlus freischalten | ImmoScout24" in self.stealth_chrome.title:
            logger.info("MieterPlus page detected. Aborting application attempt")
            if not self.premium:
                # If user is not premium we mark as processed
                Expose.processed = True
                logger.info(f"User is not premium, expose {Expose.expose_id} marked as processed.")
            return False
        
        # User should be able to apply, let´s check we can interact with the form
        try:
            StealthBrowser.random_wait()
            message_label = WebDriverWait(self.stealth_chrome, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "label[for='message']"))
            )
            message_box = self.stealth_chrome.find_element(By.ID, "message")
            message_box.clear()
        except:
            logger.warning("Message pop-up did not open or message box not found, aborting application attempt")
            return False

        #And fill it
        self._fill_application_form(Expose)
        
        # Submit the form
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
            return False

        # Validating submission
        confirmation_message = WebDriverWait(self.stealth_chrome, 10).until(
            EC.presence_of_element_located((By.XPATH, "//h2[text()='Nachricht gesendet']"))
        )
        if confirmation_message:
            logger.info(f"Expose {Expose.expose_id} applied succesfully.")
            Expose.applied_at = datetime.utcnow()
            Expose.processed = True
            # TO-DO Notify user?
            return True
        else:
            logger.warning("Could not validate application submission.")
            return False

    # Takes info from Expose and fills the application form
    def _fill_application_form(self, Expose):

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

        # Print them once for debugging
        for f in visible_fields:
            field_name = f.get_attribute("name")
            field_type_attr = f.get_attribute("type")
            if f.tag_name.lower() == "select":
                field_type = "select"
            else:
                field_type = field_type_attr.lower() if field_type_attr else f.tag_name.lower()
            logger.debug(f"Found field: name={field_name}, type={field_type}")

        #Fill fields
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

                        elif field_type == "select":
                            Select(field).select_by_visible_text(value)

                        elif field_type == "checkbox":
                            current_state = field.is_selected()
                            if value.lower() in ["true", "yes", "1"] and not current_state:
                                field.click()
                            elif value.lower() in ["false", "no", "0"] and current_state:
                                field.click()

                    except Exception as e:
                        logger.warning(f"Could not fill field '{field_name}' (type={field_type}). log debug for more details.")
                        logger.debug(e)


        logger.info("Form filling completed.")
        return

    # Scrolls the page in increments to ensure all dynamic content is fully loaded.
    def _scroll_in_increments(self):
        last_height = self.stealth_chrome.execute_script("return document.body.scrollHeight")
        while True:
            self.stealth_chrome.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            StealthBrowser.random_wait(2, 4)  # Adjust wait as needed
            new_height = self.stealth_chrome.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height

    #Return a list of only the visible input, textarea, and select fields. Hidden fields are skipped.
    def _get_all_visible_form_fields(self):
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

    # Tries to accept cookies
    def _accept_cookies(self):
        try:
            shadow_root = self.stealth_chrome.find_element(By.CSS_SELECTOR, "#usercentrics-root").shadow_root
            button = shadow_root.find_element(By.CSS_SELECTOR, "button[data-testid='uc-accept-all-button']")
            self.stealth_chrome.random_mouse_movements(button)
            button.click()
            logging.info("Successfully clicked the 'Accept All' button.")
        except:
            logging.debug("Failed to click the 'Accept All' button")
        return


    def _solve_captcha(self):
        logger.debug("Trying to solve captcha")
        attempts = 0
        max_attempts = 3
        while attempts < max_attempts:
            try:
                logger.debug("Loading solver")
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

