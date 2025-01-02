"""Captcha solver for 2Captcha Captcha Solving Service (https://2captcha.com)"""
import json
from dataclasses import dataclass
from typing import Dict
from time import sleep
import logging
import backoff
import requests
from twocaptcha import TwoCaptcha

from modules.captcha.captcha_solver import (
    CaptchaSolver,
    CaptchaBalanceEmpty,
    CaptchaUnsolvableError,
    GeetestResponse,
    RecaptchaResponse,
)

logger = logging.getLogger(__name__)

@dataclass
class GeetestResponse:
    """Responde from GeeTest Captcha"""
    challenge: str
    validate: str
    sec_code: str

@dataclass
class RecaptchaResponse:
    """Response from reCAPTCHA"""
    result: str

class CaptchaUnsolvableError(Exception):
    """Raised when Captcha was unsolveable"""
    def __init__(self):
        super().__init__()
        self.message = "Failed to solve captcha."

class CaptchaBalanceEmpty(Exception):
    """Raised when Captcha account is out of credit"""
    def __init__(self):
        super().__init__()
        self.message = "Captcha account balance empty."


class TwoCaptchaSolver():
    """Implementation of Captcha solver for 2Captcha"""

    def __init__(self, api_key):
        self.api_key = api_key

    def __get_geetest_solution(self, geetest: str, challenge: str, page_url: str) -> GeetestResponse:
        """Solves GeeTest Captcha"""
        logging.info("Trying to solve geetest.")
        params = {
            "key": self.api_key,
            "method": "geetest",
            "api_server": "api.geetest.com",
            "gt": geetest,
            "challenge": challenge,
            "pageurl": page_url
        }
        captcha_id = self.__submit_2captcha_request(params)
        untyped_result = json.loads(self.__retrieve_2captcha_result(captcha_id))
        return GeetestResponse(untyped_result["geetest_challenge"],
                               untyped_result["geetest_validate"],
                               untyped_result["geetest_seccode"])


    def __get_recaptcha_solution(self, google_site_key: str, page_url: str) -> RecaptchaResponse:
        logging.info("Trying to solve recaptcha.")
        params = {
            "key": self.api_key,
            "method": "userrecaptcha",
            "googlekey": google_site_key,
            "pageurl": page_url
        }
        captcha_id = self.__submit_2captcha_request(params)
        return RecaptchaResponse(self.__retrieve_2captcha_result(captcha_id))

    def __get_awswaf_solution(self, image):
        logging.info("Trying to solve amazon.")
        solver = TwoCaptcha(self.api_key, defaultTimeout=50, pollingInterval=5)
        result = solver.coordinates(image, lang='en')
        return result

    @backoff.on_exception(**CaptchaSolver.backoff_options)
    def __submit_2captcha_request(self, params: Dict[str, str]) -> str:
        submit_url = "http://2captcha.com/in.php"
        submit_response = requests.post(submit_url, params=params, timeout=30)
        logging.info("Got response from 2captcha/in: %s", submit_response.text)

        if not submit_response.text.startswith("OK"):
            raise requests.HTTPError(response=submit_response)

        return submit_response.text.split("|")[1]


    @backoff.on_exception(**CaptchaSolver.backoff_options)
    def __retrieve_2captcha_result(self, captcha_id: str):
        retrieve_url = "http://2captcha.com/res.php"
        params = {
            "key": self.api_key,
            "action": "get",
            "id": captcha_id,
        }
        while True:
            retrieve_response = requests.get(retrieve_url, params=params, timeout=30)
            logging.info("Got response from 2captcha/res: %s", retrieve_response.text)

            if "CAPCHA_NOT_READY" in retrieve_response.text:
                logging.info("Captcha is not ready yet, waiting...")
                sleep(5)
                continue

            if "ERROR_CAPTCHA_UNSOLVABLE" in retrieve_response.text:
                logging.info("The captcha was unsolvable.")
                raise CaptchaUnsolvableError()

            if "ERROR_ZERO_BALANCE" in retrieve_response.text:
                logging.error("2captcha account out of credit - buy more captchas.")
                raise CaptchaBalanceEmpty()

            if not retrieve_response.text.startswith("OK"):
                raise requests.HTTPError(response=retrieve_response)

            return retrieve_response.text.split("|", 1)[1]