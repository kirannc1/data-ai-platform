# Run reconciliation from a seed manifest

Merge this reconciliation directory into data-platform/src/data_platform/.
Keep the existing .env credentials, Spark kernel and source configuration.
Save the seeder's JSON output as a file. Set RECON_BATCH_MANIFEST in
data-platform/.env to an absolute path or a path relative to data-platform.
Choose a distinct run ID for each company and statement batch. Run Bronze 2,
Bronze 3, Silver and Gold in order. Omit RECON_BATCH_MANIFEST for the original
single-voucher environment-based workflow.

Required manifest fields from the existing seeder:

- run_id, company, bank_gl_account
- vouchers, an array of objects containing voucher_no
- statement_event, containing event_id, bucket and object_key

An optional gold object can specify bank_account_id, statement_direction,
currency, window_days, coverage_start and coverage_end. Unspecified settings
fall back to the existing GOLD_DEMO_* and GOLD_MATCH_WINDOW_DAYS settings.
Use the actual statement coverage dates for each batch. Dates are ISO YYYY-MM-DD.
The statement feed must already use the configured currency and direction.

Bronze 2 publishes the GL snapshot at tables/reconciliation/erpnext_gl/<run_id>.
Bronze 3 reads the PostgreSQL mappings for that company and GL account, consumes
the referenced statement notification and lands the statement CSV. Silver and
Gold keep their existing run-specific paths. Replaying the same run and manifest
replaces that run's Delta snapshots. Use one writer per run ID. Gold prints the
published URI and counts by status.

Use one manifest per company, bank GL account and statement file. Multiple
journals and CSV transaction rows can be processed in that run. For more companies
or statement files, run the same notebooks with a different manifest and run ID.
Process related journals and the full statement coverage together when they need
to compete for the same candidate transactions. Gold retains the existing
driver-side limit of 1,000 rows per Silver input and requires one statement
direction per run. The Finance API is outside this notebook archive.

For the existing Finance batch, use bronze-demo-004-demo-finance and vouchers
ACC-JV-2026-00003, ACC-JV-2026-00004 and ACC-JV-2026-00005 with its original
statement event. Save the previously printed JSON to avoid reseeding. Run twice
and check that Bronze and Gold counts and GL IDs agree across both runs.
