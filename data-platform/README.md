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

[Set up ERPNext and PostgreSQL](source-setup/README.md) for the bank reconciliation demo.

## Data Layer 
```mermaid
flowchart TB
    subgraph SOURCES["Source systems on 192.168.29.250"]
        ERP["ERPNext<br/>Bank GL entries"]
        PG["PostgreSQL<br/>Bank account mappings"]
        FILES["MinIO source bucket<br/>Bank statement CSVs"]
        KAFKA["Redpanda<br/>bank.statement.received"]
    end

    subgraph INGESTION["Ingestion and processing"]
        AIRFLOW["Apache Airflow<br/>Schedule and monitor batch jobs"]
        BATCH["Python extraction jobs<br/>ERPNext API and PostgreSQL query"]
        CONSUMER["Redpanda consumer<br/>Read event and fetch statement"]
        SPARK["Apache Spark<br/>Parse extracts and write Delta tables"]

        AIRFLOW -->|Orchestrates| BATCH
    end

    ERP -->|REST API| BATCH
    PG -->|SQL snapshot| BATCH
    KAFKA -->|Event with bucket and object key| CONSUMER
    FILES -->|CSV read via S3 API| CONSUMER

    subgraph LAKEHOUSE["Lakehouse on MinIO"]
        RAW["Raw landing<br/>Original extracts, events, and CSVs"]
        BRONZE["Bronze Delta<br/>GL entries, mappings, events, and statement rows"]
        SILVER["Silver Delta<br/>Validated transactions and normalized ledger entries"]
        GOLD["Gold Delta<br/>Reconciliation results, exceptions, and metrics"]

        RAW -->|Read landed data| SPARK
        SPARK --> BRONZE
        BRONZE -->|Spark validation and standardization| SILVER
        SILVER -->|Spark matching and aggregation| GOLD
    end

    BATCH -->|Land API extracts and SQL snapshots| RAW
    CONSUMER -->|Archive event and original CSV| RAW

    GOLD --> AI["AI layer<br/>Explain exceptions and answer reconciliation questions"]
```
