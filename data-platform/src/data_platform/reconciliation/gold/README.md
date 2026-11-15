# Gold bank reconciliation

1. Extract under `data-platform/`. Complete the existing Bronze and Silver runs first.
2. Merge the missing keys from `.env.example` into your existing `data-platform/.env`. Keep `DEMO_RUN_ID` and `SILVER_BUCKET` aligned with the successful Silver run. Commit the example and keep the populated `.env` Git-ignored.
3. Create the Gold bucket in MinIO. Use credentials that can read the Silver tables and create or replace the Gold demo snapshot.
4. Review the synthetic statement. For the seeded same-day withdrawal with a zero-day match window, set both coverage dates to the seeded posting date in YYYY-MM-DD format once coverage is confirmed. Leave both blank to exercise INCOMPLETE_COVERAGE. Direction and currency are explicit demo inputs because Silver does not supply those fields.
5. In VS Code, select a fresh Python 3.11 kernel configured with JDK 17. Install `pyspark==3.5.6` and `python-dotenv` in that environment if needed. Open `gold_bank_reconciliation.ipynb` and select **Run All**.

The notebook checks seven rule scenarios, writes one Gold result per Silver GL entry, and verifies the Delta read-back. The seeded baseline should produce one MATCHED result with complete coverage. Output is under `s3a://<GOLD_BUCKET>/tables/bank_reconciliation/<DEMO_RUN_ID>`. Reruns replace that demo run's snapshot.

The existing source seeder is in the Silver package. Gold uses those Silver outputs and needs no additional seeded source data. Rule scenarios were verified locally. Spark and MinIO verification requires your environment.
