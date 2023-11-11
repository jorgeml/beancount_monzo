#!/usr/bin/python3

from os import environ, path
from dotenv import load_dotenv
import json
import requests
import sys
import getopt
import random
import string
from datetime import date, timedelta
from pathlib import Path

# Find .env file
basedir = path.abspath(path.dirname(__file__))
load_dotenv(path.join(basedir, ".env"))

# General Config
CLIENT_ID = environ.get("CLIENT_ID")
CLIENT_SECRET = environ.get("CLIENT_SECRET")
EMAIL = environ.get("EMAIL")
data_folder = Path(environ.get("DATA_FOLDER"))

# def get_authtoken():
#    token = request.args.get('auth_token', '')
#    print(token)
#    #state = request.args.get('auth_token', '')
#    return


def authenticate():
    state = "".join(
        random.choice(string.ascii_letters + string.digits) for i in range(10)
    )
    payload = {
        "email": EMAIL,
        "redirect_uri": "https://localhost",
        "client_id": CLIENT_ID,
        "response_type": "code",
        "state": state,
    }
    headers = {
        "Accept": "*/*",
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": "Python",
    }
    r = requests.post(
        "https://api.monzo.com/oauth2/authorize", data=payload, headers=headers
    )
    r.raise_for_status()
    print(
        "Check your email, click on the link and copy and paste the authorization code."
    )
    print(f"Check that state is", state)
    auth_code = input("Auth code:")
    return auth_code


def authorize(auth_code):
    payload = {
        "grant_type": "authorization_code",
        "redirect_uri": "https://localhost",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code": auth_code,
    }
    r = requests.post("https://api.monzo.com/oauth2/token", data=payload)
    r.raise_for_status()
    access_token = r.json().get("access_token")
    print("Authorise data access in the app when requested.")
    input("Press ENTER to continue...")
    return access_token


def get_accounts(token):
    headers = {"Authorization": f"Bearer {token}"}
    params = {"account_type": "uk_retail"}
    r = requests.get("https://api.monzo.com/accounts", headers=headers, params=params)
    r.raise_for_status()
    return r.json()


def get_accounts_balance(accounts, token):
    for account in accounts.get("accounts"):
        headers = {"Authorization": f"Bearer {token}", "account_id": account.get("id")}
        params = {"account_id": account.get("id")}
        r = requests.get(
            "https://api.monzo.com/balance", headers=headers, params=params
        )
        r.raise_for_status()
        sort_code = account.get("sort_code")
        account_number = account.get("account_number")
        balance = r.json().get("balance")
        currency = r.json().get("currency")
        print(f"{sort_code} {account_number}: {balance} {currency}")
    return


def get_accounts_transactions(accounts, token, fromdate):
    for account in accounts.get("accounts"):
        headers = {"Authorization": f"Bearer {token}"}
        account_id = account.get("id")
        params = {"account_id": account_id, "expand[]": ["merchant"], "since": fromdate}
        r = requests.get(
            "https://api.monzo.com/transactions", headers=headers, params=params
        )
        r.raise_for_status()
        filename = data_folder / f"{date.today()}-monzo-{account_id}.json"
        with open(filename, "w") as json_file:
            json.dump(r.json(), json_file, indent=2)
    return


def logout(token):
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.post("https://api.monzo.com/oauth2/logout", headers=headers)
    r.raise_for_status()
    print("Log out successful")


def main(argv):
    fromdate = date.today() - timedelta(89)
    try:
        opts, _ = getopt.getopt(argv, "hd:", "date=")
    except getopt.GetoptError:
        print("monzo-download.py -d <date>")
        sys.exit(2)
    for opt, arg in opts:
        if opt == "-h":
            print("monzo-download.py -d <date>")
            sys.exit()
        elif opt in ("-d", "--date"):
            fromdate = arg
    auth_code = authenticate()
    token = authorize(auth_code)
    print("## Accounts")
    accounts = get_accounts(token)
    print("## Balances")
    get_accounts_balance(accounts, token)
    print("## Transactions")
    get_accounts_transactions(accounts, token, fromdate)
    print("## Logout")
    logout(token)


if __name__ == "__main__":
    main(sys.argv[1:])
