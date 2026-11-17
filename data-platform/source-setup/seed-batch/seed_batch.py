"""Seed a synthetic reconciliation batch. Run one writer per run ID."""
import argparse
import csv
import hashlib
import io
import json
import re
from datetime import date
from decimal import Decimal
from pathlib import Path
from urllib.parse import quote


def read_csv(payload, columns):
    reader = csv.DictReader(io.StringIO(payload.decode("utf-8-sig"), newline=""))
    if reader.fieldnames != columns.split(","):
        raise ValueError(f"Expected CSV columns: {columns}")
    rows = list(reader)
    if not rows or any(None in row or None in row.values() for row in rows):
        raise ValueError(f"Expected nonempty, well-formed CSV: {columns}")
    return rows


def load_fixtures(folder):
    journals_bytes = (folder / "journals.csv").read_bytes()
    mappings_bytes = (folder / "mappings.csv").read_bytes()
    statement_bytes = (folder / "statement.csv").read_bytes()
    journals = read_csv(journals_bytes, "journal_ref,posting_date,amount")
    mappings = read_csv(mappings_bytes, "scenario,bank_account_id")
    statements = read_csv(statement_bytes, "transaction_id,bank_account_id,posting_date,amount,reference")
    refs = set()
    for row in journals:
        ref, amount = row["journal_ref"], row["amount"]
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", ref) or ref in refs:
            raise ValueError(f"Invalid or duplicate journal_ref: {ref}")
        refs.add(ref)
        date.fromisoformat(row["posting_date"])
        if not re.fullmatch(r"\d{1,12}(\.\d{1,2})?", amount) or Decimal(amount) <= 0:
            raise ValueError(f"Invalid positive journal amount: {amount}")
    keys = {(row["scenario"], row["bank_account_id"]) for row in mappings}
    if len(keys) != len(mappings) or any(not part.strip() for key in keys for part in key):
        raise ValueError("Mappings require unique, nonempty scenario and bank account pairs.")
    digests = [hashlib.sha256(blob).hexdigest()
               for blob in (journals_bytes, mappings_bytes, statement_bytes)]
    return journals, mappings, statements, statement_bytes, digests


def seed(args, cfg, fixtures):
    import boto3
    import psycopg
    import requests
    from botocore.config import Config
    from botocore.exceptions import ClientError
    from confluent_kafka import Producer

    def setting(name):
        value = cfg.get(name)
        if not value:
            raise ValueError(f"Missing setting: {name}")
        return value

    journals, mappings, statements, statement_bytes, digests = fixtures
    run = args.run_id
    company, bank, expense = (setting(name) for name in (
        "ERPNEXT_COMPANY", "ERPNEXT_BANK_ACCOUNT", "ERP_SEED_EXPENSE_ACCOUNT"))
    if bank == expense:
        raise ValueError("Use separate bank and expense GL accounts.")
    site = setting("ERPNEXT_URL").rstrip("/")
    collection = site + "/api/resource/Journal%20Entry"
    pg_dsn, broker, topic = (setting(name) for name in (
        "PG_DSN", "REDPANDA_BOOTSTRAP_SERVERS", "STATEMENT_TOPIC"))
    bucket = setting("STATEMENT_BUCKET")
    if bucket in {cfg.get("BRONZE_BUCKET") or "bronze",
                  cfg.get("SILVER_BUCKET") or "silver", cfg.get("GOLD_BUCKET") or "gold"}:
        raise ValueError("Use a dedicated statement source bucket.")
    key = f"silver-demo/{run}.csv"
    headers = {"Authorization": f"token {setting('ERP_SEED_API_KEY')}:{setting('ERP_SEED_API_SECRET')}"}
    s3 = boto3.client(
        "s3", endpoint_url=setting("MINIO_ENDPOINT"), region_name="us-east-1",
        aws_access_key_id=setting("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=setting("AWS_SECRET_ACCESS_KEY"),
        config=Config(s3={"addressing_style": "path"}, connect_timeout=5, read_timeout=20),
    )

    def immutable_object(object_key, payload, content_type):
        try:
            s3.put_object(Bucket=bucket, Key=object_key, Body=payload,
                          ContentType=content_type, IfNoneMatch="*")
        except ClientError as exc:
            if exc.response["ResponseMetadata"]["HTTPStatusCode"] != 412:
                raise
            with s3.get_object(Bucket=bucket, Key=object_key)["Body"] as body:
                if body.read(len(payload) + 1) != payload:
                    raise ValueError(f"Run {run} already has different source data. Choose a new run ID.") from None

    def erp(method, url, **kwargs):
        response = requests.request(method, url, headers=headers, timeout=30,
                                    allow_redirects=False, **kwargs)
        if not 200 <= response.status_code < 300:
            try:
                error = response.json()
            except ValueError:
                error = {}

            message = (
                error.get("_server_messages")
                or error.get("message")
                or error.get("exc_type")
                or "No validation message returned"
            )
            raise RuntimeError(
                f"ERPNext {method} returned HTTP {response.status_code}: {message}"
            )
        return response.json()["data"]

    identity = {"run_id": run, "fixture_sha256": digests, "company": company,
                "site": site, "bank": bank, "expense": expense}
    immutable_object(f"silver-demo/{run}/seed-inputs.json",
                     json.dumps(identity, sort_keys=True).encode(), "application/json")

    vouchers = []
    for row in journals:
        amount = Decimal(row["amount"])
        marker = f"bronze-batch:{run}:{row['journal_ref']}"
        found = erp("GET", collection, params={
            "filters": json.dumps([["company", "=", company], ["user_remark", "=", marker]]),
            "fields": json.dumps(["name"]), "limit_page_length": 2,
        })
        if len(found) > 1:
            raise RuntimeError(f"Multiple journals for {marker}")
        if found:
            journal = erp("GET", collection + "/" + quote(found[0]["name"], safe=""))
        else:
            journal = erp("POST", collection, json={
                "voucher_type": "Journal Entry", "company": company, "user_remark": marker,
                "posting_date": row["posting_date"], "accounts": [
                    {"account": expense, "debit_in_account_currency": float(amount)},
                    {"account": bank, "credit_in_account_currency": float(amount)},
                ],
            })
        lines = sorted((line["account"], Decimal(str(line.get("debit_in_account_currency") or 0)),
                        Decimal(str(line.get("credit_in_account_currency") or 0)))
                       for line in journal["accounts"])
        if journal["posting_date"] != row["posting_date"] or lines != sorted([
            (expense, amount, Decimal(0)), (bank, Decimal(0), amount)
        ]):
            raise RuntimeError(f"Existing journal {journal['name']} differs from fixture")
        if journal["docstatus"] == 0:
            journal = erp("PUT", collection + "/" + quote(journal["name"], safe=""),
                          json={"docstatus": 1})
        if journal["docstatus"] != 1:
            raise RuntimeError(f"Journal {journal['name']} is not submitted")
        vouchers.append({"journal_ref": row["journal_ref"], "voucher_no": journal["name"]})

    desired = {(row["scenario"], company, bank, row["bank_account_id"]) for row in mappings}
    with psycopg.connect(pg_dsn) as db:
        db.execute("""CREATE TABLE IF NOT EXISTS silver_demo_account_mapping (
            scenario_run text, scenario text, company text, ledger_account text,
            bank_account_id text, PRIMARY KEY (scenario_run, scenario, bank_account_id))""")
        existing = set(db.execute("""SELECT scenario, company, ledger_account, bank_account_id
            FROM silver_demo_account_mapping WHERE scenario_run = %s""", (run,)).fetchall())
        if existing - desired:
            raise ValueError(f"PostgreSQL already contains different mappings for {run}")
        for mapping in sorted(desired - existing):
            db.execute("""INSERT INTO silver_demo_account_mapping
                (scenario_run, scenario, company, ledger_account, bank_account_id)
                VALUES (%s,%s,%s,%s,%s)""", (run, *mapping))

    immutable_object(key, statement_bytes, "text/csv")
    event = {"event_id": f"statement-{run}", "bucket": bucket, "object_key": key}
    manifest = {"run_id": run, "company": company, "bank_gl_account": bank,
                "vouchers": vouchers, "statement_event": event,
                "expected": {"journals": len(journals), "mappings": len(mappings),
                             "statement_rows": len(statements)}}
    errors = []
    producer = Producer({"bootstrap.servers": broker, "enable.idempotence": True,
                         "message.timeout.ms": 15000})
    producer.produce(topic, key=event["event_id"], value=json.dumps(event),
                     on_delivery=lambda err, _: errors.append(str(err)) if err else None)
    if producer.flush(20) or errors:
        raise RuntimeError("Redpanda delivery was not confirmed. Retry with the same inputs.")
    print(json.dumps(manifest, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", args.run_id):
        parser.error("Invalid run ID")
    fixtures = load_fixtures(args.fixtures)
    if args.validate_only:
        print(f"PASS: {len(fixtures[0])} journals, {len(fixtures[1])} mappings, "
              f"{len(fixtures[2])} statement rows")
        return
    if not args.env_file or not args.env_file.is_file():
        parser.error("Provide --env-file pointing to data-platform/.env")
    from dotenv import dotenv_values

    seed(args, dotenv_values(args.env_file, interpolate=False), fixtures)


if __name__ == "__main__":
    main()
