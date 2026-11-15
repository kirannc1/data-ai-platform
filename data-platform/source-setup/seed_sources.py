"""Seed demo sources. Run serially using dedicated demo identities."""
import csv
import io
import json
import re
from pathlib import Path
from datetime import date
from urllib.parse import quote

import boto3
import psycopg
import requests
from botocore.config import Config
from confluent_kafka import Producer
from dotenv import dotenv_values

def settings():
    cwd = Path.cwd().resolve()
    paths = [p / "data-platform" / ".env" for p in (cwd, *cwd.parents)]
    paths += [p / ".env" for p in (cwd, *cwd.parents) if p.name == "data-platform"]
    return dotenv_values(next((p for p in paths if p.is_file()), Path("data-platform/.env")),
                         interpolate=False)

def seed(c):
    run = c["DEMO_RUN_ID"]
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", run):
        raise ValueError("Invalid DEMO_RUN_ID")
    posting = date.fromisoformat(c["DEMO_POSTING_DATE"]).isoformat()
    company, account = c["ERPNEXT_COMPANY"], c["ERPNEXT_BANK_ACCOUNT"]
    api = c["ERPNEXT_URL"].rstrip("/") + "/api/resource/Journal%20Entry"
    marker = f"silver-fixture:{run}"
    headers = {"Authorization": f"token {c['ERP_SEED_API_KEY']}:{c['ERP_SEED_API_SECRET']}"}

    def erp(method, url, **kwargs):
        response = requests.request(method, url, headers=headers, timeout=30,
                                    allow_redirects=False, **kwargs)
        if not response.ok or response.is_redirect:
            raise RuntimeError(f"ERPNext returned HTTP {response.status_code}")
        return response.json()["data"]

    found = erp("GET", api, params={"filters": json.dumps(
        [["company", "=", company], ["user_remark", "=", marker]]),
        "fields": json.dumps(["name", "docstatus"]), "limit_page_length": 2})
    if len(found) > 1:
        raise RuntimeError("Multiple journals have the same seed marker.")
    journal = found[0] if found else erp("POST", api, json={
        "voucher_type": "Journal Entry", "company": company, "posting_date": posting,
        "user_remark": marker, "accounts": [
            {"account": c["ERP_SEED_EXPENSE_ACCOUNT"], "debit_in_account_currency": 10000},
            {"account": account, "credit_in_account_currency": 10000},
        ]})
    if journal["docstatus"] == 0:
        journal = erp("PUT", api + "/" + quote(journal["name"], safe=""), json={"docstatus": 1})
    if journal["docstatus"] != 1:
        raise RuntimeError("Fixture journal is not submitted.")

    # Isolate test mappings from existing application schemas.
    with psycopg.connect(c["PG_DSN"]) as db:
        db.execute("""CREATE TABLE IF NOT EXISTS silver_demo_account_mapping (
            scenario_run text, scenario text, company text, ledger_account text,
            bank_account_id text, PRIMARY KEY (scenario_run, scenario, bank_account_id))""")
        for scenario, bank_id in [("baseline", "DEMO-001"),
                                  ("ambiguous", "DEMO-001"), ("ambiguous", "DEMO-002")]:
            db.execute("""INSERT INTO silver_demo_account_mapping VALUES (%s,%s,%s,%s,%s)
                ON CONFLICT (scenario_run, scenario, bank_account_id) DO UPDATE
                SET company=EXCLUDED.company, ledger_account=EXCLUDED.ledger_account""",
                (run, scenario, company, account, bank_id))

    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(["transaction_id", "bank_account_id", "posting_date", "amount", "reference"])
    valid = ["TX-001", "DEMO-001", posting, "10,000.00", " DEMO-JOURNAL "]
    writer.writerows([valid, valid, ["TX-002", "DEMO-001", "2026-02-30", "10.00", "INVALID"]])
    bucket, key = c["STATEMENT_BUCKET"], f"silver-demo/{run}.csv"
    if bucket == c.get("BRONZE_BUCKET", "bronze"):
        raise ValueError("Use a dedicated source statement bucket.")
    s3 = boto3.client("s3", endpoint_url=c["MINIO_ENDPOINT"],
        aws_access_key_id=c["AWS_ACCESS_KEY_ID"], aws_secret_access_key=c["AWS_SECRET_ACCESS_KEY"],
        region_name="us-east-1", config=Config(s3={"addressing_style": "path"}))
    s3.put_object(Bucket=bucket, Key=key, Body=buffer.getvalue().encode(), ContentType="text/csv")
    event = {"event_id": f"statement-{run}", "bucket": bucket, "object_key": key}
    errors = []
    producer = Producer({"bootstrap.servers": c["REDPANDA_BOOTSTRAP_SERVERS"]})
    producer.produce(c["STATEMENT_TOPIC"], key=event["event_id"], value=json.dumps(event),
                     on_delivery=lambda err, _: errors.append(err) if err else None)
    if producer.flush(15) or errors:
        raise RuntimeError("Statement event was not acknowledged. Rerun serially.")
    print(f"Set ERPNEXT_VOUCHER_NO={journal['name']} in your .env")

if __name__ == "__main__":
    seed(settings())
