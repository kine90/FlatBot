import os
import poplib
import base64
import re
import importlib
import logging
from email import parser
from email.message import EmailMessage
from dotenv import load_dotenv
from modules.Database import ExposeDB
from modules.Expose import Expose
from modules.BaseExposeProcessor import BaseExposeProcessor

logger = logging.getLogger(__name__)

class EmailFetcher:
    def __init__(self, db=None):
        load_dotenv()
        self.db = db if db else ExposeDB()

        # Decoded email credentials
        self.email_user = os.getenv("EMAIL_USER")
        self.email_password = os.getenv("EMAIL_PASSWORD")
        self.pop3_server = os.getenv("EMAIL_SERVER")
        self.pop3_port = int(os.getenv("EMAIL_PORT"))

        # Control Features
        self.delete_emails_after_processing = os.getenv("EMAIL_DELETE", "False").lower() == "true"

        # Load processors dynamically
        self.processors = self.load_processors()
   
    def load_processors(self):
        logging.info("Emailfetcher loading processors...")
        processors = {}
        modules_dir = "modules"
        for module_name in os.listdir(modules_dir):
            if module_name.endswith("_processor.py"):
                module = importlib.import_module(f"{modules_dir}.{module_name[:-3]}")
                for attr in dir(module):
                    processor_class = getattr(module, attr)
                    # Check if it's a subclass of BaseExposeProcessor and not BaseExposeProcessor itself
                    if (
                        isinstance(processor_class, type) 
                        and issubclass(processor_class, BaseExposeProcessor) 
                        and processor_class is not BaseExposeProcessor
                    ):
                        # Since domain is a class attribute, we can access it directly
                        if hasattr(processor_class, 'domain'):
                            domain = processor_class.domain
                            processors[domain] = processor_class
                            logger.info(f"Registered processor class for domain: {domain}")
                        else:
                            logger.warning(f"Processor {processor_class.__name__} does not have a 'domain' attribute.")
                logging.info("Imported " + module_name)
        return processors

    def get_email_body(self, email_message: EmailMessage):
        """Extract the body of the email in plain text."""
        if email_message.is_multipart():
            for part in email_message.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition"))
                if content_type == "text/plain" and "attachment" not in content_disposition:
                    return part.get_payload(decode=True).decode("utf-8", errors="ignore")
        else:
            return email_message.get_payload(decode=True).decode("utf-8", errors="ignore")
        return None

    def fetch_emails(self):
        logging.info("Fetching emails...")
        new_exposes = 0
        logging.info(f"Connecting to {self.pop3_server}:{self.pop3_port} with user {self.email_user}")
        try:
            mailbox = poplib.POP3_SSL(self.pop3_server, self.pop3_port)
            mailbox.user(self.email_user)
            mailbox.pass_(self.email_password)

            num_messages = len(mailbox.list()[1])
            logging.info(f"Found {num_messages} emails.")

            if num_messages > 0:
                for i in range(num_messages):
                    raw_email = b"\n".join(mailbox.retr(i+1)[1])
                    email_message = parser.Parser().parsestr(raw_email.decode("utf-8"))
                    subject = email_message["Subject"]
                    sender = email_message["From"]
                    body = self.get_email_body(email_message)
                    logger.info("Processing email from " + sender + " Subject: " + subject)
                    if body:
                        # Iterate over class-based processors
                        for domain, processor_class in self.processors.items():
                            if domain in sender:
                                # Call the static method directly on the class
                                expose_ids = processor_class.extract_expose_link(subject, body)
                                if expose_ids:
                                    for expose_id in expose_ids:
                                        if not self.db.expose_exists(expose_id):
                                            new_expose = Expose(
                                                expose_id=expose_id, 
                                                source=processor_class.name
                                            )
                                            self.db.insert_expose(new_expose)
                                            new_exposes += 1
                                            logging.info(
                                                f"Inserted expose {expose_id} into the database with source '{processor_class.name}'."
                                            )
                                        else:
                                            logging.info(f"Expose {expose_id} already exists.")
                                    if self.delete_emails_after_processing:
                                        mailbox.dele(i+1)
                                        logging.warning(f"Deleted email with subject: {subject}")
                                break
                    else:
                        logging.warning(f"Email with subject '{subject}' has no readable body.")

            mailbox.quit()

        except Exception as e:
            logging.error(f"Error: {str(e)}")
        return new_exposes
