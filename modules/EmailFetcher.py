import os
import imaplib
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
        #IMAP settings
        self.imap_server = os.getenv("EMAIL_SERVER_IMAP")
        self.imap_port = int(os.getenv("EMAIL_IMAP_PORT"))
        self.mark_read = os.getenv("EMAIL_MARK_READ", "False").lower() == "true"
        self.delete_from_server = os.getenv("EMAIL_DELETE", "False").lower() == "true"
        # Load processors dynamically
        self.processors = self.load_processors()

    def load_processors(self):
        logging.info("EmailFetcher: loading processors...")
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

    def get_email_body(self, email_message: EmailMessage) -> str:
        """Extract the body of the email in plain text."""
        if email_message.is_multipart():
            for part in email_message.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition"))
                if content_type == "text/plain" and "attachment" not in content_disposition:
                    return part.get_payload(decode=True).decode("utf-8", errors="ignore")
        else:
            return email_message.get_payload(decode=True).decode("utf-8", errors="ignore")
        return ""

    def fetch_emails(self):
        """
        Fetch unread emails via IMAP, parse them, and mark them as read.
        Returns the number of new exposes that were inserted into the database.
        """
        logging.info("Fetching emails via IMAP...")
        new_exposes = 0

        try:
            # Connect to the IMAP server
            logging.info(f"Connecting to IMAP {self.imap_server}:{self.imap_port} as {self.email_user}")
            mailbox = imaplib.IMAP4_SSL(self.imap_server, self.imap_port)
            mailbox.login(self.email_user, self.email_password)

            # Select the INBOX (read/write mode)
            mailbox.select("INBOX")

            # Search for unread emails (use "ALL" if you want everything)
            status, message_ids = mailbox.search(None, "UNSEEN")
            if status != "OK":
                logging.error("Could not search for emails.")
                mailbox.close()
                mailbox.logout()
                return new_exposes

            # message_ids[0] is a space-separated string of email IDs
            messages = message_ids[0].split()
            logging.info(f"Found {len(messages)} unread emails.")

            # Process each email
            for num in messages:
                # Retrieve the entire message
                status, data = mailbox.fetch(num, "(RFC822)")
                if status != "OK":
                    logging.warning(f"Failed to fetch email with ID {num}. Skipping...")
                    continue

                # The raw email content is in data[0][1]
                raw_email = data[0][1]
                try:
                    email_str = raw_email.decode("utf-8")
                except UnicodeDecodeError:
                    # If there's a decoding error, fallback
                    email_str = raw_email.decode("latin-1", errors="ignore")

                email_message = parser.Parser().parsestr(email_str)
                subject = email_message["Subject"] or ""
                sender = email_message["From"] or ""

                body = self.get_email_body(email_message)
                logger.info(f"Processing email from {sender} | Subject: {subject}")

                if not body:
                    logger.warning(f"Email with subject '{subject}' has no readable body.")
                else:
                    # Iterate over processors
                    for domain, processor_class in self.processors.items():
                        if domain in sender:
                            # We have a processor, Extract Expose IDs
                            expose_ids = processor_class.extract_expose_link(subject, body)
                            if expose_ids:
                                # It is an offer, attempt to store exposes
                                for expose_id in expose_ids:
                                    if not self.db.expose_exists(expose_id):
                                        new_expose = Expose(
                                            expose_id=expose_id,
                                            source=processor_class.name
                                        )
                                        self.db.insert_expose(new_expose)
                                        new_exposes += 1
                                        logging.info(
                                            f"Inserted expose {expose_id} into database (source='{processor_class.name}')."
                                        )
                                    else:
                                        logging.info(f"Expose {expose_id} already exists.")
                                # Then mark the email as read (add the \\Seen flag)
                                if self.mark_read:
                                    mailbox.store(num, "+FLAGS", "\\Seen")
                                # Or/and delete it
                                if self.delete_from_server:
                                    mailbox.store(num, "+FLAGS", "\\Deleted")
                                    mailbox.expunge()
                            break  # Found our processor; no need to check others


            mailbox.close()
            mailbox.logout()

        except imaplib.IMAP4.error as e:
            logging.error(f"IMAP4 error: {str(e)}")
        except Exception as e:
            logging.error(f"Error: {str(e)}")

        return new_exposes
