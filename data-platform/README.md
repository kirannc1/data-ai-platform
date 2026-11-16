# Data platform

This enterprise data platform starter uses bank statement reconciliation to demonstrate multi-source ingestion, Bronze–Silver–Gold processing, data quality checks, and traceable reconciliation results.

Target Azure: ADF/Event Hubs -> company-isolated ADLS Gen2 -> Databricks/Delta Bronze, Silver, Gold -> Unity Catalog/Databricks SQL/Power BI, with Purview, MDM and security as cross-cutting capabilities.

## **Silver Delta snapshot replay** 
synthetic posted GL lines from two fictional companies; a minimal DuckDB-based demonstration writes raw Bronze, validated Silver and aggregated Gold Parquet outputs. The local bank reconciliation demo below uses Spark and Delta Lake.

Run from repository root:

```bash
python -m data_platform.demo
python -m pytest data-platform/tests -q
```

Outputs are created under `outputs/data-platform/` (gitignored). Next labs: schema drift and quarantine, incremental loads and replay, account mapping, SCD2, `Fact_GL_Transaction`, conformed dimensions, governed EBITDA definition and domain policies.

## Local reconciliation sources

[Set up ERPNext, PostgreSQL, Redpanda, and MinIO](source-setup/README.md) for the bank statement reconciliation demo. Airflow is the planned orchestrator. The current demo runs manually from notebooks.

### Bank statement reconciliation scope

The demo reconciles a synthetic **₹10,000 bank withdrawal** against a submitted **ERPNext bank GL credit**. PostgreSQL maps the company and GL account to a bank account. Redpanda signals that a statement is available and carries the MinIO bucket and object key for its CSV.

| Layer | Reads | Produces |
|---|---|---|
| Bronze | ERPNext GL entries, PostgreSQL mappings, and the MinIO CSV referenced by Redpanda | Source-aligned Delta tables and references to raw evidence |
| Silver | Bronze records for the demo | Validated GL and statement rows, duplicate counts, quarantined rows, and missing or ambiguous mapping exceptions. The Delta snapshot replay check writes the same Silver snapshot twice to MinIO and verifies that the schemas and row counts stay the same. |
| Gold | Silver tables for the same run | One result per Silver GL entry, with match status, reason, rule version, and evidence references |

Gold checks account mapping, amount, direction, currency, and the configured date window. The notebook covers matched, unmatched, ambiguous, incomplete coverage, and mapping-exception outcomes. Direction, currency, and statement coverage are explicit demo inputs because the current Silver statement schema does not carry them. The demo uses synthetic data and a bounded run. Scheduled ingestion, cross-file deduplication, statement-side exception reporting, and AI consumption are future work.

### Planned enterprise extensions

- **Master data management (MDM).** Extend the existing PostgreSQL account   mapping with canonical company and bank-account IDs, effective-dated   source mappings, and a process for resolving mapping conflicts.
- **Dimensional modeling.** Add a reconciliation reporting fact with an   explicit grain and shared company, bank account, date, and currency   dimensions. Retain the existing Gold detail for transaction investigation.

## Data layer architecture

The Airflow scheduling and AI handoff in this diagram show the intended integration.

```mermaid
flowchart TB
    subgraph SOURCES["Source systems"]
        ERP["ERPNext — Bank GL entries"]
        PG["PostgreSQL — Bank account mappings"]
        FILES["MinIO source bucket — Bank statement CSVs"]
        KAFKA["Redpanda — bank.statement.received"]
    end

    subgraph INGESTION["Ingestion and processing"]
        AIRFLOW["Apache Airflow — Schedule and monitor batch jobs"]
        BATCH["Python extraction jobs — ERPNext API and PostgreSQL query"]
        CONSUMER["Redpanda consumer — Read event and fetch statement"]
        SPARK["Apache Spark — Parse extracts and write Delta tables"]

        AIRFLOW -->|Orchestrates| BATCH
    end

    ERP -->|REST API| BATCH
    PG -->|SQL snapshot| BATCH
    KAFKA -->|Event with bucket and object key| CONSUMER
    FILES -->|CSV read via S3 API| CONSUMER

    subgraph LAKEHOUSE["Lakehouse on MinIO"]
        RAW["Raw landing — Original extracts, events, and CSVs"]
        BRONZE["Bronze Delta — GL entries, mappings, events, and statement rows"]
        SILVER["Silver Delta — Validated transactions and normalized ledger entries"]
        GOLD["Gold Delta — Reconciliation results and evidence"]
    end

    BATCH -->|Land API extracts and SQL snapshots| RAW
    CONSUMER -->|Archive event and original CSV| RAW
    RAW -->|Read landed data| SPARK
    SPARK --> BRONZE
    BRONZE -->|Spark validation and standardization| SILVER
    SILVER -->|Spark matching| GOLD
    GOLD --> AI["AI layer — Explain exceptions and answer reconciliation questions"]

    classDef source fill:#E9F2FF,stroke:#3974BA,color:#15365E,stroke-width:1.5px
    classDef processing fill:#E4F6F3,stroke:#238378,color:#123D39,stroke-width:1.5px
    classDef raw fill:#F1EBFC,stroke:#8061B4,color:#3F2A62,stroke-width:1.5px
    classDef bronze fill:#F7E8D9,stroke:#A46432,color:#56351F,stroke-width:1.5px
    classDef silver fill:#E7EDF4,stroke:#6D8095,color:#27394D,stroke-width:1.5px
    classDef gold fill:#FFF0BA,stroke:#9F750E,color:#4C3405,stroke-width:2px
    classDef ai fill:#4C3481,stroke:#36225E,color:#FFFFFF,stroke-width:2px

    class ERP,PG,FILES,KAFKA source
    class AIRFLOW,BATCH,CONSUMER,SPARK processing
    class RAW raw
    class BRONZE bronze
    class SILVER silver
    class GOLD gold
    class AI ai

    style SOURCES fill:#F7FAFF,stroke:#9CBCE2,color:#15365E
    style INGESTION fill:#F4FBFA,stroke:#8CBEB8,color:#123D39
    style LAKEHOUSE fill:#FBF9FF,stroke:#BAAAD6,color:#3F2A62
    linkStyle default stroke:#627286,stroke-width:1.5px
```

## Run the local reconciliation demo

1. Create the configured MinIO buckets (defaults: `bank-statements`, `bronze`, `silver`, and `gold`) and confirm the Redpanda topic `bank.statement.received` exists.
2. Set up the Python 3.11 WSL kernel with JDK 17. Install the notebook and seed dependencies in that environment.

   ```bash
   python -m pip install "pyspark==3.5.6" python-dotenv ipykernel requests "boto3>=1.36,<2" "psycopg[binary]" confluent-kafka
   ```

   If Spark cannot create `spark-warehouse` under a Windows-mounted repo, point `spark.sql.warehouse.dir` to a writable directory under your WSL home before creating the Spark session. Restart the kernel after changing the setting.
3. Use one Git-ignored `data-platform/.env` for the seed script and notebooks. Set MinIO, ERPNext, PostgreSQL, and Redpanda connection details. Use the same `DEMO_RUN_ID` throughout. Keep real credentials out of Git and notebook outputs.
4. Run `source-setup/seed_sources.py` from `data-platform`. It prepares the ERPNext journal, seeds `silver_demo_account_mapping` in PostgreSQL, uploads the CSV, and publishes its Redpanda event. Copy the printed voucher into `ERPNEXT_VOUCHER_NO`.
5. Run the notebooks in the order below using the WSL kernel.

| Order | Notebook | What to verify |
|---|---|---|
| Optional | `delta_smoke_test.ipynb` | Two synthetic rows written to and read from MinIO. The ERPNext Bronze notebook also performs a connectivity check. |
| 1 | `bronze_erpnext_ingestion.ipynb` | The selected ERPNext GL row and raw JSON reference land in Bronze. |
| 2 | `bronze_mapping_statement.ipynb` | The mapping snapshot, statement, and event land in Bronze. |
| 3 | `silver_reconciliation.ipynb` | One validated GL row, one accepted statement row, one duplicate, one quarantined statement row, and two mapping exceptions. The replay checks preserve the schemas and counts. |
| 4 | `gold_bank_reconciliation.ipynb` | Expect one `MATCHED` result for the seeded ₹10,000 withdrawal, with references to the GL row and statement transaction. |

For the same-day Gold fixture, use `GOLD_MATCH_WINDOW_DAYS=0` and set both Gold coverage dates to the seeded posting date if the statement represents that full day. Leave both blank if coverage is unknown. A missing match that needs coverage to be classified is then reported as `INCOMPLETE_COVERAGE`.

**Local verification.** The Delta smoke test, Bronze landing, and Silver schema, quarantine, mapping, and replay checks passed. Gold write and read-back still need confirmation. To inspect Gold after a successful run, read the Delta table at `s3a://<GOLD_BUCKET>/tables/bank_reconciliation/<DEMO_RUN_ID>` in Spark. MinIO shows its Parquet files and `_delta_log/`.

## Folder layout

```text
enterprise-data-ai-platform/
└── data-platform/
    ├── .env
    ├── README.md
    ├── source-setup/
    │   └── seed_sources.py
    ├── data-layer/
    │   └── airflow/
    │       └── .env
    └── src/
        └── data_platform/
            └── reconciliation/
                ├── bronze/
                │   ├── delta_smoke_test.ipynb
                │   ├── bronze_erpnext_ingestion.ipynb
                │   └── bronze_mapping_statement.ipynb
                ├── silver/
                │   └── silver_reconciliation.ipynb
                └── gold/
                    └── gold_bank_reconciliation.ipynb
```

The Airflow Compose `.env` is separate from the notebook and seed configuration.
