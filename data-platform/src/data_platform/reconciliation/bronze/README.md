## Run the raw Bronze layer

Open [bronze_erpnext_ingestion.ipynb](data-platform/src/data_platform/reconciliation/bronze/bronze_erpnext_ingestion.ipynb)
in VS Code and select the Python 3.11 kernel configured for JDK 17.
Follow the notebook's setup instructions and populate the Git-ignored
`data-platform/.env` with the MinIO credentials, ERPNext read-only API credentials,
and demo voucher details.

Run all cells from a fresh kernel. The notebook runs the MinIO Delta smoke test,
lands the ERPNext response as raw JSON, and writes the bank-side GL row to Bronze
Delta. A successful run ends with
`PASS: raw capture verified and one Bronze row after replay`.
