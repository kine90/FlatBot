import os
import time
from datetime import datetime
import importlib
import logging
from modules.Database import ExposeDB, Expose
from modules.EmailFetcher import EmailFetcher
from modules.StealthBrowser import StealthBrowser



logger = logging.getLogger(__name__)
log_level = logging.INFO

def init_log():    # Create logs directory if it doesn't exist
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
    os.makedirs(log_dir, exist_ok=True)
    # Generate log file name
    current_time = datetime.now()
    log_file = f"Flatbot_{current_time.day}_{current_time.month}_{current_time.year}.log"
    log_file_path = os.path.join(log_dir, log_file)
    # Configure root logger
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_file_path),
            logging.StreamHandler()
        ]
    )


def main():
    init_log()
    logger.warning(">----------------------- Flatbot starting! -----------------------<")
    logger.debug('Log started')
    print("Initializing the database...")
    db_instance = ExposeDB()
    logger.info("Database initialized successfully!")
    email_processor = EmailFetcher(db_instance)
    while True:
        logger.info("Fetching emails...")
        new_exposes = email_processor.fetch_emails()
        logger.warning(f"Email fetching completed! Found {new_exposes} new exposes")
        time.sleep(2)
        logger.info("Starting processor...")
        exposes = db_instance.get_unprocessed_exposes()
        if  exposes:
            stealth_chrome = StealthBrowser()
            for expose in exposes:
                try:
                    processor_module = importlib.import_module(f"modules.{expose.source}_processor")
                    processor_class = getattr(processor_module, f"{expose.source}_processor", None)
                    if not processor_class:
                        logger.error(f"Processor class for {expose.source} not found")
                        continue
                    processor_instance = processor_class(stealth_chrome)
                    expose, success = processor_instance.process_expose(expose)
                    db_instance.update_expose(expose)
                    if success:
                        logger.warning("Expose processed and updated")
                except ModuleNotFoundError:
                    logger.error(f"Processor module for {expose.source} not found")
                except AttributeError as e:
                    logger.error(f"Error accessing processor class: {e}")
                except Exception as e:
                    logger.error(f"Error processing expose from {expose.source}: {e}")
            logger.warning("All new exposes processed.")
            stealth_chrome.kill()
        else:
            logger.warning("No unprocessed exposes found.")
        StealthBrowser.random_wait(200, 400)

############################################################
if __name__ == "__main__":
    main()
