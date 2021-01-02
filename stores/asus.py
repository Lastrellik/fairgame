import os
import json
import random
import time
from json.decoder import JSONDecodeError
from chromedriver_py import binary_path  # this will get you the path variable
import fileinput

import requests

from stores.basestore import BaseStoreHandler
from utils.logger import log
from utils.selenium_utils import options, enable_headless, button_click_using_xpath, button_click_using_id, field_send_keys, send_keys_by_xpath, click_by_xpath, wait_for_element_by_xpath, wait_for_element, wait_for_element_to_disappear, select_input_by_id, check_exists_by_xpath
from utils.encryption import get_credentials_from_file, get_credit_card_data_from_file

from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait

CREDENTIAL_FILE = "config/asus_credentials.json"
CREDIT_CARD_FILE = "config/credit_card.json"
ASUS_STORE_URL = "https://store.asus.com"
ASUS_REALTIME_INVENTORY_URL = "https://store.asus.com/us/category/get_real_time_data"
ASUS_ITEM_URL = "https://store.asus.com/us/item/{sm_id}"
SHOPPING_CART_URL = "https://shop-us1.asus.com/AW000706/cart"

CONFIG_FILE_PATH = "config/asus_config.json"

HEADERS = {
    "authority": "store.asus.com",
    "pragma": "no-cache",
    "cache-control": "no-cache",
    "accept": "application/json, text/javascript, */*; q=0.01",
    "x-requested-with": "XMLHttpRequest",
    "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/51.0.2704.103 "
                  "Safari/537.36",
    "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
    "origin": "https://store.asus.com",
    "sec-fetch-site": "same-origin",
    "sec-fetch-mode": "cors",
    "sec-fetch-dest": "empty",
    "accept-language": "en-US,en;q=0.9",
}


class AsusStoreHandler(BaseStoreHandler):
    def __init__(
        self,
        notification_handler,
        encryption_pass=None,
    ) -> None:
        super().__init__()
        self.notification_handler = notification_handler
        self.sm_list = []
        self.stock_checks = 0
        self.start_time = int(time.time())

        # Load up our configuration
        self.parse_config()

        # Initialize the Session we'll use for this run
        self.session = requests.Session()
        self.username, self.password = get_credentials_from_file('Asus', CREDENTIAL_FILE, encryption_pass)
        self.credit_card_dict = get_credit_card_data_from_file(CREDIT_CARD_FILE, encryption_pass)
        self.create_driver()
        self.driver.get(ASUS_STORE_URL)
        if not self.is_logged_in():
            self.login()

    def __del__(self):
        message = "Shutting down Asus Store Handler."
        log.info(message)
        self.notification_handler.send_notification(message)

    def is_logged_in(self):
        try:
            text = self.driver.find_element_by_xpath("//a[contains(text(), 'Sign Up')]").text
            return text != "Login / Sign Up"
        except:
            return False

    def login(self):
        self.driver.find_element_by_xpath("//a[contains(text(), 'Sign Up')]").click()
        field_send_keys(self.driver, 'Front_txtAccountID', self.username)
        send_keys_by_xpath(self.driver, "//input[@id='Front_txtPassword']", self.password)
        click_by_xpath(self.driver, "//label[@class='checkbox inline']")
        button_click_using_id(self.driver, "btnLogin")

    def run(self, delay=45):
        # Load real-time inventory for the provided SM list and clean it up as we go
        self.verify()
        message = "Starting to hunt SKUs at ASUS Store"
        log.info(message)
        self.notification_handler.send_notification(message)

        while self.sm_list:
            status_collection = self.get_sm_status_dict()
            for sm_id, sm_details in status_collection.items():
                if self.stock_checks > 0 and self.stock_checks % 1000 == 0:
                    checks_per_second = self.stock_checks / self.get_elapsed_time(
                        self.start_time
                    )
                    log.info(
                        f"Performed {self.stock_checks} stock checks so far ({checks_per_second} cps). Continuing to "
                        f"scan... "
                    )
                if self.check_stock(sm_id, sm_details):
                    url = ASUS_ITEM_URL.format(sm_id=sm_id)
                    log.info(f'Item {sm_id} is available at url {url}')
                    self.add_item_to_cart(sm_id)
                    self.checkout()
                    log.debug(f"Removing {sm_id} from hunt list.")
                    self.sm_list.remove(sm_id)
                    self.notification_handler.send_notification(
                        f"Found in-stock item at ASUS: {url}"
                    )
            time.sleep(delay)

    def add_item_to_cart(self, sm_id):
        add_to_cart_url = f'https://shop-us1.asus.com/AW000706/cart_api/set_sdata?callback=jQuery19105768661324897866_1609447575379&source=https%3A%2F%2Fstore.asus.com%2Fus%2Fitem%2F{sm_id}&send_data=%7B%22s%22%3A%22{sm_id}%22%2C%22t%22%3A%221%22%2C%22q%22%3A1%2C%22g%22%3A%5B%5D%2C%22p%22%3A%5B%5D%2C%22m%22%3A%5B%5D%2C%22c%22%3A%22%22%2C%22a%22%3A%22%22%2C%22item_source%22%3A%22%2F%2Fstore.asus.com%2Fus%2Fitem%2F{sm_id}%22%2C%22is_market_cross%22%3A%22%22%7D&ws_seq=AW000706&store=0&_=1609447575381'
        url = ASUS_ITEM_URL.format(sm_id=sm_id)
        self.driver.get(add_to_cart_url)
        log.info(f'Added item {sm_id} to cart')

    def checkout(self):
        self.driver.get(SHOPPING_CART_URL)
        button_click_using_xpath(self.driver, '//button[contains(text(),"Checkout")]')
        #TODO add personal info and shipping info logic
        self.set_billing_address()
        self.set_shipping_speed()
        self.set_payment_method()
        self.accept_terms_and_conditions()
        button_click_using_xpath(self.driver, '//*[@id="checkout-step__review"]/div[2]/div[4]/div[3]/a')
        self.enter_credit_card_details()
        button_click_using_xpath(self.driver, '//*[@id="payment_details_lower"]/input[2]')
        time.sleep(100000)

    def set_billing_address(self):
        log.info('Setting billing address...')
        wait_for_element_by_xpath(self.driver, '//label[@for="billing-add-new"]')
        if not self.config.get('billing_address').get('same_as_shipping'):
            self.select_different_billing_address()

        while not(check_exists_by_xpath(self.driver, '//*[@id="form-shipping-method"]/div/div/div[1]/div/label')):
            button_click_using_xpath(self.driver, '//section[@id="checkout-step__shipping-and-billing"]/div/div/a')
            time.sleep(3)

    def select_different_billing_address(self):
        billing_mobile_number = str(self.config.get('billing_address').get('mobile_number'))
        button_click_using_xpath(self.driver, '//label[@for="billing-add-new"]')
        phone_number_xpath = f'//span[contains(text(), "{billing_mobile_number}")]'
        wait_for_element_by_xpath(self.driver, phone_number_xpath)
        button_click_using_xpath(self.driver, phone_number_xpath)
        button_click_using_xpath(self.driver, '//button[contains(text(), "Confirm")]')
        wait_for_element_to_disappear(self.driver, '//button[contains(text(), "Confirm")]')


    def set_shipping_speed(self):
        # TODO make this customizable
        log.info('Setting shipping speed...')
        wait_for_element_by_xpath(self.driver, '//input[@name="some-radios"]')
        button_click_using_xpath(self.driver, '//section[@id="checkout-step__shipping-method"]/div/div/a')

    def set_payment_method(self):
        log.info('Setting payment method...')
        # Credit cards is the only supported method at this time
        button_click_using_xpath(self.driver, '//label[@for="card"]')
        button_click_using_xpath(self.driver, '//section[@id="checkout-step__payment-method"]/div/div/a')

    def accept_terms_and_conditions(self):
        log.info('Accepting terms and conditions...')
        wait_for_element_by_xpath(self.driver, '//*[@id="checkout-step__review"]/div[2]/ul/li[4]/div[2]/div[2]/a')
        #TODO be more explicit about this
        time.sleep(5)
        button_click_using_xpath(self.driver, '//label[@for="accept-terms"]')
        button_click_using_xpath(self.driver, '//label[@for="accept-privacy"]')

    def enter_credit_card_details(self):
        log.info('Entering credit card information...')
        card_type_map = {
            'Visa': '001',
            'Mastercard': '002',
            'Amex': '003',
            'Discover': '004'
        }
        wait_for_element_by_xpath(self.driver, '//*[@id="payment_details_upper"]')
        card_type_index = card_type_map.get(self.credit_card_dict.get('card_type'))
        button_click_using_id(self.driver, f'card_type_{card_type_index}')
        field_send_keys(self.driver, 'card_number', self.credit_card_dict.get('card_number'))
        select_input_by_id(self.driver, 'card_expiry_month', self.credit_card_dict.get('card_expiration_month'))
        select_input_by_id(self.driver, 'card_expiry_year', self.credit_card_dict.get('card_expiration_year'))
        field_send_keys(self.driver, 'card_cvn', self.credit_card_dict.get('card_ccv'))

    def parse_config(self):
        log.info(f"Processing config file from {CONFIG_FILE_PATH}")
        # Parse the configuration file to get our hunt list
        try:
            with open(CONFIG_FILE_PATH) as json_file:
                self.config = json.load(json_file)
                self.sm_list = self.config.get("sm_list")
        except FileNotFoundError:
            log.error(
                f"Configuration file not found at {CONFIG_FILE_PATH}.  Please see {CONFIG_FILE_PATH}_template."
            )
            exit(1)
        log.info(f"Found {len(self.sm_list)} SM numbers to track at the ASUS store.")

    def verify(self):
        log.info("Verifying item list...")
        sm_status_list = self.get_sm_status_dict()
        for sm_id, sm_details in sm_status_list.items():
            if sm_details["not_found"]:
                log.error(
                    f"ASUS store reports {sm_id} not found.  Removing {sm_id} from list"
                )
                # Remove from the list, since ASUS reports it as "not found"
                self.sm_list.remove(sm_id)
            else:
                name = sm_details["market_info"]["name"]
                if " (" in name:
                    stop_index = name.index(" (")
                    short_name = name[0:stop_index]
                log.info(
                    f"Found {sm_id}: {name} @ {sm_details['market_info']['price']['final_price']['price']}"
                )
        log.info(f"Verified {len(self.sm_list)} items on Asus Store")

    def get_sm_status_dict(self):
        # Get the list of SM responses or an empty response
        return self.get_real_time_data().get("data", {})

    def get_real_time_data(self):
        """ASUS website XHR request that we're borrowing for lightweight inventory queries.  Returns JSON"""
        log.debug(f"Calling ASUS web service with {len(self.sm_list)} items.")
        payload = {"sm_seq_list[]": self.sm_list}
        try:
            response = self.session.post(
                ASUS_REALTIME_INVENTORY_URL, headers=HEADERS, data=payload
            )
            response_json = response.json()
            return response_json
        except JSONDecodeError:
            log.error("Failed to receive valid JSON response.  Skipping")
            return {}

    def check_stock(self,sm_id, item):
        price = item["market_info"]["price"]["final_price"]["price"]
        quantity = item["market_info"]["quantity"]
        if item["market_info"]["buy"]:
            response = requests.get(ASUS_ITEM_URL.format(sm_id=sm_id))
            if response.status_code != 200:
                # Item is unavailable
                self.stock_checks += 1
                return False
            log.info(
                f"Asus has {quantity} of {item['market_info']['sm_seq']} available to buy for {price}"
            )
            return True
        else:
            # log.info(f"{sm_id} is unavailable.  Offer price listed as {price}")
            self.stock_checks += 1
        return False

    def create_driver(self):
        # TODO enable headless, no_image
        prefs = {
            "profile.password_manager_enabled": False,
            "credentials_enable_service": False,
        }
        options.add_experimental_option("prefs", prefs)
        options.add_argument(f"user-data-dir=.profile-asus")
        # Delete crashed, so restore pop-up doesn't happen
        path_to_prefs = os.path.join(
            os.path.dirname(os.path.abspath("__file__")),
            ".profile-amz",
            "Default",
            "Preferences",
        )
        try:
            with fileinput.FileInput(path_to_prefs, inplace=True) as file:
                for line in file:
                    print(line.replace("Crashed", "none"), end="")
        except FileNotFoundError:
            pass

        try:
            self.driver = webdriver.Chrome(executable_path=binary_path, options=options)
        except Exception as e:
            log.error(e)
            log.error(
                "If you have a JSON warning above, try deleting your .profile-asus folder"
            )
            log.error(
                "If that's not it, you probably have a previous Chrome window open. You should close it."
            )

