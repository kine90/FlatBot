import os
import time
import importlib
import stealth_browser
from database import get_unprocessed_exposes, update_expose, mark_expose_as_processed
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains

def process_all_exposes():
    exposes = get_unprocessed_exposes()
    if not exposes:
        print("No unprocessed exposes found.")
        return
    stealthdriver = stealth_browser.get_stealth_browser()

    for expose in exposes:
        source_key = expose['source']
        print(f"Debug: Processing source key: {source_key}")
        try:
            processor_module = importlib.import_module(f"{source_key}_processor")
            processor_module.process_expose(stealthdriver, expose)
        except ModuleNotFoundError:
            print(f"Processor module for {source_key} not found")
        except AttributeError:
            print(f"process_expose function missing in module {source_key}_processor")
        except Exception as e:
            print(f"Error processing expose from {source_key}: {e}")

    stealthdriver.quit()
