# Single-company reconciliation seed

Extract into `data-platform/source-setup/`. Use the existing WSL Python environment with
python-dotenv, requests, psycopg[binary], boto3 >= 1.36, and confluent-kafka.

Check these values in `data-platform/.env` alongside the existing source settings
and credentials.

```dotenv
ERPNEXT_COMPANY="Demo Finance"
ERPNEXT_BANK_ACCOUNT="Demo Operating Bank - DF"
ERP_SEED_EXPENSE_ACCOUNT="Demo Operating Expense - DF"
```

From the repository root, validate the bundled fixtures.

```bash
cd data-platform/source-setup/single-company-seed
python seed_batch.py --run-id bronze-demo-004-demo-finance --validate-only
```

The bundled fixtures are from the completed Finance run. Use its existing vouchers
for Bronze ingestion. To add transactions, prepare a new batch in `fixtures/`
with unique journal references in `journals.csv` and the corresponding statement
data in `statement.csv`. Keep the bank account mapping in `mappings.csv`.
Run with a fresh ID, for example:

```bash
python seed_batch.py --run-id bronze-demo-005-demo-finance --env-file ../../.env
```

A fresh run ID creates new journals for every journal row supplied. For a partial
failure, retry with the same ID and identical inputs. The retry reuses journals
and may republish the same logical statement event. Run one writer per run ID.

The script posts ERPNext journals, seeds PostgreSQL account mappings, uploads the
CSV to the MinIO statement source bucket, and sends a Redpanda notification.
Use the printed voucher IDs and run ID to run the Bronze ingestion separately.
