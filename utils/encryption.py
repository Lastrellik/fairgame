import getpass as getpass
import stdiomask
import json
import os
from base64 import b64encode, b64decode
from Crypto.Cipher import ChaCha20_Poly1305
from Crypto.Random import get_random_bytes
from Crypto.Protocol.KDF import scrypt

from utils.logger import log


def encrypt(pt, password):
    """Encryption function to securely store user credentials, uses ChaCha_Poly1305
    with a user defined SCrypt key."""
    salt = get_random_bytes(32)
    key = scrypt(password, salt, key_len=32, N=2 ** 20, r=8, p=1)
    nonce = get_random_bytes(12)
    cipher = ChaCha20_Poly1305.new(key=key, nonce=nonce)
    ct, tag = cipher.encrypt_and_digest(pt)
    json_k = ["nonce", "salt", "ct", "tag"]
    json_v = [b64encode(x).decode("utf-8") for x in (nonce, salt, ct, tag)]
    result = json.dumps(dict(zip(json_k, json_v)))

    return result


def decrypt(ct, password):
    """Decryption function to unwrap and return the decrypted creds back to the main thread."""
    try:
        b64Ct = json.loads(ct)
        json_k = ["nonce", "salt", "ct", "tag"]
        json_v = {k: b64decode(b64Ct[k]) for k in json_k}

        key = scrypt(password, json_v["salt"], key_len=32, N=2 ** 20, r=8, p=1)
        cipher = ChaCha20_Poly1305.new(key=key, nonce=json_v["nonce"])
        ptData = cipher.decrypt_and_verify(json_v["ct"], json_v["tag"])

        return ptData
    except (KeyError, ValueError):
        print("Incorrect Password.")
        exit(0)


def create_encrypted_config(data, file_path, encryption_pass):
    """Creates an encrypted credential file if none exists.  Stores results in a
    file in the root directory."""
    if isinstance(data, dict):
        data = json.dumps(data)
    payload = bytes(data, "utf-8")
    if not encryption_pass:
        log.info("Create a password for the credential file")
        cpass = stdiomask.getpass(prompt="Credential file password: ", mask="*")
        vpass = stdiomask.getpass(prompt="Verify credential file password: ", mask="*")
        if cpass == vpass:
            result = encrypt(payload, cpass)
            with open(file_path, "w") as f:
                f.write(result)
            log.info("Sensitive data safely stored.")
        else:
            print("Password and verify password do not match.")
            exit(0)
    else:
        result = encrypt(payload, encryption_pass)
        with open(file_path, "w") as f:
            f.write(result)
        log.info("Sensitive data safely stored.")


def load_encrypted_config(config_path, encrypted_pass=None):
    """Decrypts a previously encrypted credential file and returns the contents back
    to the calling thread."""
    log.info("Reading credentials from: " + config_path)
    with open(config_path, "r") as json_file:
        data = json_file.read()
    try:
        if "nonce" in data:
            if encrypted_pass is None:
                password = stdiomask.getpass(
                    prompt="Credential file password: ", mask="*"
                )
            else:
                password = encrypted_pass
            decrypted = decrypt(data, password)
            return json.loads(decrypted)
        else:
            log.info(
                "Your configuration file is unencrypted, it will now be encrypted."
            )
            create_encrypted_config(data, config_path, encrypted_pass)
            return json.loads(data)
    except Exception as e:
        log.error(e)
        log.error(
            f"Failed to decrypt the credential file. If you have forgotten the password, delete {config_path} and rerun the bot"
        )

def await_credential_input(website):
    username = input(f"{website} login ID: ")
    password = stdiomask.getpass(prompt=f"{website} password: ")
    return {
        "username": username,
        "password": password,
    }

def get_credentials_from_file(website, credential_file_path, encryption_pass):
    credential = None
    if os.path.exists(credential_file_path):
        credential = load_encrypted_config(credential_file_path, encryption_pass)
    else:
        log.info("No credential file found, let's make one")
        log.info("NOTE: DO NOT SAVE YOUR CREDENTIALS IN CHROME, CLICK NEVER!")
        credential = await_credential_input(website)
        create_encrypted_config(credential, credential_file_path, encryption_pass)
    return credential["username"], credential["password"]

def await_credit_card_input():
    card_type = input("Credit card type (Visa, Mastercard, Amex, Discover):")
    card_number = input("Credit card number (no spaces or dashes):")
    card_expiration_month = input("Credit card expiration month (MM):")
    card_expiration_year = input("Credit card expiration year (YYYY):")
    card_ccv = input("Credit card ccv number:")
    return {
        'card_type': card_type,
        'card_number': card_number,
        'card_expiration_month': card_expiration_month,
        'card_expiration_year': card_expiration_year,
        'card_ccv': card_ccv
    }

def get_credit_card_data_from_file(credit_card_file_path, encryption_pass):
    credit_card = None
    if os.path.exists(credit_card_file_path):
        log.info('Found credit card file. Decrypting....')
        credit_card = load_encrypted_config(credit_card_file_path, encryption_pass)
    else:
        log.info("No credit card file found, let's make one")
        log.info("Note: Your credit card information is stored locally in an encrypted file and never sent anywhere outside of the website accepting the credit card information.")
        credit_card = await_credit_card_input()
        create_encrypted_config(credit_card, credit_card_file_path, encryption_pass)
    return credit_card


# def main():
#
#    password = getpass.getpass(prompt="Password: ")
#
#    if not os.path.isfile("../amazon_config.enc"):
#        verify = getpass.getpass(prompt="Verify Password: ")
#
#        if verify == password:
#            ptFile = open("../amazon_config.json", "rb")
#            data = ptFile.read()
#            ct = encrypt(data, password)
#
#            ctFile = open("../amazon_config.enc", "w")
#            ctFile.write(ct)
#            ctFile.close()
#        else:
#            print("Passwords do no match")
#            exit(0)
#
#    ctFile = open("../amazon_config.enc", "r")
#    data = ctFile.read()
#    pt = decrypt(data, password)
#    print(pt)
#
#
# main()
