# Reconciliation Silver demo

This package implements a bounded synthetic run. It includes a source seeder, two Bronze notebooks, a Silver notebook with explicit Delta schemas and scenario assertions, and an environment template.

1. Extract the package under `data-platform`. Merge the template into your existing Git-ignored `data-platform/.env`. Use synthetic test systems and dedicated identities. Create the source statement, Bronze, and Silver buckets in MinIO and ensure the statement topic exists.
2. Select a Python 3.11 kernel with JDK 17. Install `pyspark==3.5.6 python-dotenv requests "boto3>=1.36,<2" "psycopg[binary]" confluent-kafka` in that environment.
3. Run `python seed_sources.py` from the package folder. Fill in the demo posting date, INR company and accounts, and authorized API credentials. The seed identity needs ERPNext Journal Entry creation and submission and PostgreSQL access to create/write the isolated demo mapping table. The Bronze API identity needs read access to GL Entry. Set the printed voucher in `.env`.
4. Run `bronze_erpnext_ingestion.ipynb`, then `bronze_mapping_statement.ipynb` in fresh kernels. The statement notebook selects the seeded event by run ID and lands the statement CSV, event, and PostgreSQL snapshot in Bronze.
5. Run `silver_reconciliation.ipynb` in a fresh kernel. Expect one GL row, one statement row, one duplicate, one statement quarantine and two mapping exceptions. Each Silver table is scoped to a demo run and written twice to verify replay.

Keep the same fixture settings for a replay. Use a new demo run ID to seed a different fixture. The seed script assumes direct access to the demo broker without SASL and single-writer execution. The PostgreSQL table is deliberately isolated from any existing mapping schema. Silver tests overlapping candidates through that demo table. Shared environments should use TLS and separate scoped identities. Source credentials belong only in the local `.env`.
