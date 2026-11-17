# Multi-company reconciliation seeder

Extract `multi-company-seed/` into `data-platform/source-setup/`. Use your
existing Python 3.11 WSL environment with python-dotenv, requests, psycopg[binary],
boto3 >= 1.36, and confluent-kafka.

## ERPNext setup

Demo Finance uses the existing company and bank and expense ledgers.
For the example second profile, create an INR company named Demo Trading with
abbreviation DT and create two leaf accounts under its chart of accounts.
Use Demo Operating Bank under Assets with account type Bank, and Demo Operating
Expense under Expenses. Confirm the full account names in ERPNext and put them
in companies.json. You can instead point that profile at an existing test
company and its ledgers. The seed API user must be able to read, create, and submit
Journal Entries for both companies. Use a posting date in an open period and
keep the corresponding statement dates aligned.

## Run in Ubuntu WSL

From the repository root:

```bash
cd data-platform/source-setup/multi-company-seed
source ~/.venvs/bronze-py311/bin/activate
python seed_companies.py --batch-id bronze-demo-004 --validate-only
python seed_companies.py --batch-id bronze-demo-004 --env-file ../../.env
```

One shared .env supplies connection settings and credentials. The company and
account settings in companies.json take precedence for each company. The
PostgreSQL mapping table is silver_demo_account_mapping. Create the configured
MinIO source bucket and Redpanda topic before running.

The runner seeds ERPNext journals and PostgreSQL mappings, uploads each raw
statement CSV byte-for-byte to the MinIO source bucket, and publishes a Redpanda
event per company after the respective upload succeeds.

| Company | Run ID | Journal count | Mapping count | CSV rows | MinIO object key |
|---|---|---:|---:|---:|---|
| Demo Finance | bronze-demo-004-demo-finance | 3 | 1 | 3 | silver-demo/bronze-demo-004-demo-finance.csv |
| Demo Trading | bronze-demo-004-demo-trading | 1 | 1 | 1 | silver-demo/bronze-demo-004-demo-trading.csv |

## Load Bronze

Use the per-company run ID, company, and bank GL account in the Bronze notebook
configuration. The runner prints each submitted voucher ID. Run ERPNext Bronze
once per printed voucher, then run the mappings and statement notebook once per
company run. Verify the counts above and one logical statement event per run.
Gold computes the match status. The matching INR 10,000 examples share a date and
amount, while the two bank account IDs and company scopes keep their evidence
distinct.

For a new company, add a companies.json entry and copy a fixture directory to
fixtures/<company-id>. Edit journals.csv, mappings.csv, and statement.csv. Use a
new batch ID when changing fixture contents. If a run stops partway through,
retry with the same batch ID and inputs. Earlier companies may already have
seeded successfully, and a retry can publish the same logical event again.
Run one seeder at a time for a given batch.

The existing Silver notebook has single-fixture assertions. Update them before
running this larger batch through Silver and Gold.
