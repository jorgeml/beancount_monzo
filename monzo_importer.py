"""Monzo JSON file importer

This importer parses a list of transactions in JSON format obtained from the Monzo API:

https://monzo.com/docs/#list-transactions
/transactions?expand[]=merchant&account_id=$account_id

Original code by Adam Gibbins <adam@adamgibbins.com>.
"""

__author__ = "Jorge Martínez López <jorgeml@jorgeml.me>"
__license__ = "MIT"

import datetime
import json

from os import path

from beancount.core import account
from beancount.core import amount
from beancount.core import data
from beancount.core import flags
from beancount.core import position
from beancount.core.number import D
from beancount.core.number import ZERO

import beangulp
from beangulp import mimetypes
from beangulp.testing import main

class Importer(beangulp.Importer):
    """An importer for Monzo Bank JSON files."""

    def __init__(self, account_id, account):
        self.account_id = account_id
        self.importer_account = account

    def identify(self, filepath):
        identifier = get_account_id(filepath)
        return identifier == self.account_id
    
    def filename(self, filepath):
        return 'monzo.{}'.format(path.basename(filepath))

    def account(self, filepath):
        return self.importer_account

    def date(self, filepath):
        transactions = get_transactions(filepath)
        return parse_transaction_time(transactions[0]["created"])

    def extract(self, filepath, existing=None):
        entries = []
        transactions = get_transactions(filepath)

        for transaction in transactions:

            metadata = {
                "bank_id": transaction["id"],
                "bank_dedupe_id": transaction["dedupe_id"],
                "bank_description": transaction["description"],
                "bank_created_date": transaction["created"],
                "bank_settlement_date": transaction["settled"],
                "bank_updated_date": transaction["updated"],
            }

            if "account_number" in transaction["counterparty"]:
                metadata["counterparty_account_number"] = transaction["counterparty"][
                    "account_number"
                ]
                metadata["counterparty_sort_code"] = transaction["counterparty"][
                    "sort_code"
                ]
            elif "number" in transaction["counterparty"]:
                metadata["counterparty_phone_number"] = transaction["counterparty"][
                    "number"
                ]
                metadata["counterparty_user_id"] = transaction["counterparty"][
                    "user_id"
                ]

            meta = data.new_metadata(filepath, 0, metadata)

            if transaction["notes"].lower() == "pin change":
                entries.append(
                    data.Note(
                        meta,
                        parse_transaction_time(transaction["created"]),
                        self.importer_account,
                        "PIN Change",
                    )
                )
                continue

            if "decline_reason" in transaction:
                note = "%s transaction declined with reason %s" % (
                    get_payee(transaction),
                    transaction["decline_reason"],
                )
                entries.append(
                    data.Note(
                        meta,
                        parse_transaction_time(transaction["created"]),
                        self.importer_account,
                        note,
                    )
                )
                continue

            date = parse_transaction_time(transaction["created"])
            price = get_unit_price(transaction)
            payee = get_payee(transaction)
            narration = get_narration(transaction)

            postings = []
            unit = amount.Amount(D(transaction["amount"]) / 100, transaction["currency"])
            postings.append(data.Posting(self.importer_account, unit, None, price, None, None))

            # Default to warning as requires human review/categorisation
            flag = flags.FLAG_WARNING
            # second_account = 'Expenses:FIXME'
            link = set()

            if transaction["scheme"] == "uk_retail_pot":
                second_account = self.importer_account
                flag = None
                link = {transaction["metadata"]["pot_id"]}
                postings.append(
                    data.Posting(second_account, -unit, None, None, flag, None)
                )

            # postings.append(data.Posting(second_account, -unit, None, None, flag, None))

            entries.append(
                data.Transaction(
                    meta, date, flags.FLAG_OKAY, payee, narration, set(), link, postings
                )
            )

        return entries

def get_account_id(filepath):
    mimetype, encoding = mimetypes.guess_type(filepath)
    if mimetype != 'application/json':
        return False

    with open(filepath) as data_file:
        try:
            transactions = json.load(data_file)["transactions"]
            if len(transactions) == 0:
                return False
            if "account_id" in transactions[0]:
                return transactions[0]["account_id"]
            else:
                return False
        except KeyError:
            return False


def get_transactions(filepath):
    mimetype, encoding = mimetypes.guess_type(filepath)
    if mimetype != 'application/json':
        return False

    with open(filepath) as data_file:
        data = json.load(data_file)
        if "transactions" in data:
            return data["transactions"]
        else:
            return False


def get_unit_price(transaction):
    # local_amount is 0 when the transaction is an active card check,
    # putting a price in for this throws a division by zero error
    if (
        transaction["local_currency"] != transaction["currency"]
        and transaction["local_amount"] != 0
    ):
        total_local_amount = D(transaction["amount"])
        total_foreign_amount = D(transaction["local_amount"])
        # all prices need to be positive
        unit_price = round(abs(total_foreign_amount / total_local_amount), 5)
        return data.Amount(unit_price, transaction["local_currency"])
    else:
        return None


def get_payee(transaction):
    if transaction["merchant"]:
        return transaction["merchant"]["name"]
    elif "prefered_name" in transaction["counterparty"]:
        return transaction["counterparty"]["prefered_name"]
    elif "name" in transaction["counterparty"]:
        return transaction["counterparty"]["name"]
    else:
        return None


def get_narration(transaction):
    if transaction["notes"] != "":
        return transaction["notes"]
    elif transaction["scheme"] == "uk_retail_pot":
        return "Internal pot transfer"
    # elif get_payee(transaction) is None:
    else:
        return transaction["description"]

def parse_transaction_time(date_str):
    """Parse a time string and return a datetime object.

    Args:
      date_str: A string, the date to be parsed, in ISO format.
    Returns:
      A datetime.date() instance.
    """
    timestamp = datetime.datetime.fromisoformat(date_str)
    return timestamp.date()
