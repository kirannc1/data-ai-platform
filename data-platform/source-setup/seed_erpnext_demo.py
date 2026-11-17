"""Seed the local ERPNext reconciliation demo through Frappe DocTypes."""

from decimal import Decimal
import fcntl
from pathlib import Path
import sys
import os

import frappe
from frappe.utils import nowdate

COMPANY = "Demo Finance"
ABBR = "DF"
CURRENCY = "INR"
MARKER = "reconciliation-demo-expense-v1"
AMOUNT = Decimal("10000")


def ensure(doctype, filters, fields):
    name = frappe.db.exists(doctype, filters)
    if name:
        return frappe.get_doc(doctype, name)
    return frappe.get_doc({"doctype": doctype, **fields}).insert()


def ledger(label, root_type, account_type=None):
    parent = frappe.db.get_value(
        "Account", {"company": COMPANY, "root_type": root_type,
                    "parent_account": ["is", "not set"], "is_group": 1}, "name"
    )
    if not parent:
        raise RuntimeError(f"Missing {root_type} root account for {COMPANY}")

    fields = {"account_name": label, "company": COMPANY, "parent_account": parent,
              "is_group": 0, "account_currency": CURRENCY}
    if account_type:
        fields["account_type"] = account_type
    account = ensure("Account", {"company": COMPANY, "account_name": label}, fields)
    if (account.is_group or account.root_type != root_type
            or account.account_currency != CURRENCY
            or (account_type and account.account_type != account_type)):
        raise RuntimeError(f"Existing ledger has incompatible settings: {account.name}")
    return account.name


def journal(bank, expense, cost_center):
    names = frappe.get_all("Journal Entry", filters={"company": COMPANY, "user_remark": MARKER},
                           pluck="name")
    if len(names) > 1:
        raise RuntimeError(f"Multiple journals have the seed marker: {MARKER}")
    if names:
        doc = frappe.get_doc("Journal Entry", names[0])
    else:
        doc = frappe.get_doc({
            "doctype": "Journal Entry", "company": COMPANY,
            "voucher_type": "Journal Entry", "posting_date": nowdate(),
            "user_remark": MARKER,
            "accounts": [
                {"account": expense, "debit_in_account_currency": AMOUNT,
                 "cost_center": cost_center},
                {"account": bank, "credit_in_account_currency": AMOUNT},
            ],
        }).insert()
    expected = sorted([(expense, AMOUNT, Decimal(0)), (bank, Decimal(0), AMOUNT)])
    actual = sorted((row.account, Decimal(str(row.debit_in_account_currency or 0)),
                     Decimal(str(row.credit_in_account_currency or 0)))
                    for row in doc.accounts)
    if doc.docstatus == 2 or actual != expected:
        raise RuntimeError(f"Existing journal is cancelled or differs: {doc.name}")
    if doc.docstatus == 0:
        doc.submit()
    return doc.name


def demo_user(email, first_name, role):
    if not frappe.db.exists("User", email):
        frappe.get_doc({
            "doctype": "User", "email": email, "first_name": first_name,
            "user_type": "System User", "enabled": 1, "send_welcome_email": 0,
            "roles": [{"role": role}],
        }).insert()
    ensure("User Permission", {"user": email, "allow": "Company", "for_value": COMPANY},
           {"user": email, "allow": "Company", "for_value": COMPANY})


def seed():
    if frappe.get_meta("System Settings").has_field("setup_complete"):
        setup_complete = frappe.db.get_single_value("System Settings", "setup_complete")
    else:
        setup_complete = frappe.db.get_default("setup_complete")
    if not setup_complete or str(setup_complete) == "0":
        raise RuntimeError("Complete the ERPNext setup wizard at http://localhost:8080 first.")

    company = ensure("Company", COMPANY, {"company_name": COMPANY, "abbr": ABBR,
                                          "country": "India", "default_currency": CURRENCY})
    if company.default_currency != CURRENCY:
        raise RuntimeError(f"Existing {COMPANY} must use {CURRENCY}")
    bank = ledger("Demo Operating Bank", "Asset", "Bank")
    expense = ledger("Demo Operating Expense", "Expense")
    bank_master = ensure("Bank", {"bank_name": "Demo Bank"}, {"bank_name": "Demo Bank"})
    bank_account = ensure("Bank Account", {"company": COMPANY, "account": bank,
                                           "is_company_account": 1},
                          {"account_name": "Demo Operating Bank", "bank": bank_master.name,
                           "company": COMPANY, "is_company_account": 1, "account": bank,
                           "bank_account_no": "000000000001"})
    cost_center = company.get("cost_center") or frappe.db.get_value(
        "Cost Center", {"company": COMPANY, "is_group": 0}, "name"
    )
    if not cost_center:
        raise RuntimeError(f"Set a default cost center for {COMPANY}")
    entry = journal(bank, expense, cost_center)
    users = ("demo.accounts@example.test", "demo.reviewer@example.test")
    demo_user(users[0], "Demo Accounts", "Accounts User")
    demo_user(users[1], "Demo Reviewer", "Accounts Manager")
    return {
        "Company": company.name, "Bank GL account": bank, "Bank Account": bank_account.name,
        "Expense GL account": expense, "Submitted journal": entry, "Demo users": ", ".join(users),
    }


def main():
    site = sys.argv[1] if len(sys.argv) > 1 else "frontend"
    sites_path = Path("sites").resolve()
    os.chdir(sites_path)
    with (sites_path / site / "reconciliation-demo-seed.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        frappe.init(site=site, sites_path=str(sites_path))
        try:
            frappe.connect()
            frappe.set_user("Administrator")
            result = seed()
            frappe.db.commit()
        except Exception:
            db = getattr(frappe.local, "db", None)
            if db is not None:
                db.rollback()
            raise
        finally:
            frappe.destroy()
    for key, value in result.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()



