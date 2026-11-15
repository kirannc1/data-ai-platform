# Data platform

Target Azure: ADF/Event Hubs -> company-isolated ADLS Gen2 -> Databricks/Delta Bronze, Silver, Gold -> Unity Catalog/Databricks SQL/Power BI, with Purview, MDM and security as cross-cutting capabilities.

**Included bootstrap:** synthetic posted GL lines from two fictional companies; a minimal DuckDB-based demonstration writes raw Bronze, validated Silver and aggregated Gold Parquet outputs. It is deliberately **not** the complete finance star schema, a Delta Lake implementation, or an enterprise consolidation engine.

Run from repository root:

```bash
python -m data_platform.demo
python -m pytest data-platform/tests -q
```

Outputs are created under `outputs/data-platform/` (gitignored). Next labs: schema drift and quarantine, incremental loads and replay, account mapping, SCD2, `Fact_GL_Transaction`, conformed dimensions, reconciliation, governed EBITDA definition and domain policies.

## Local reconciliation sources

[Set up ERPNext, PostgreSQL, Redpanda, MinIO and Airflow ](source-setup/README.md) for the bank reconciliation demo.

## Data Layer 
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
        GOLD["Gold Delta — Reconciliation results, exceptions, and metrics"]
    end

    BATCH -->|Land API extracts and SQL snapshots| RAW
    CONSUMER -->|Archive event and original CSV| RAW
    RAW -->|Read landed data| SPARK
    SPARK --> BRONZE
    BRONZE -->|Spark validation and standardization| SILVER
    SILVER -->|Spark matching and aggregation| GOLD
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

### Bronze ingestion setup

Airflow runs on the dev PC. ERPNext, PostgreSQL, MinIO, and Redpanda run on the source host.

- [ ] **Create the MinIO buckets.** Keep incoming CSVs in `bank-statements`, archive original extracts, events, and CSVs in `raw-landing`, and store Delta tables in `bronze`.
- [ ] **Verify source access.** From the ingestion runtimes, read an ERPNext GL entry, query PostgreSQL’s `bank_account_mapping`, fetch `statement-001.csv` through the MinIO S3 API, and read an event from Redpanda’s `bank.statement.received` topic.
- [ ] **Validate Spark and Delta Lake.** Write a small Delta table to MinIO and read it back.
- [ ] **Build and test the batch DAGs.** Create one Airflow DAG for a date-bounded ERPNext bank ledger extract and another for a PostgreSQL account mapping snapshot. Run both manually before enabling schedules.
- [ ] **Build and test the statement consumer.** Read the Redpanda event, fetch the referenced CSV, archive both originals, and write the event and statement rows to Bronze. Commit the Kafka offset after all required writes succeed.
- [ ] **Verify Bronze and replay.** Check all four Bronze tables. Replay the same statement event and confirm `statement-001` still has exactly two transaction rows.

### Silver validation

- [ ] Normalize the bank and ERP ledger records. Verify that the ₹10,000 withdrawal matches the ERPNext bank ledger credit and that the ₹250 bank charge remains unmatched.
