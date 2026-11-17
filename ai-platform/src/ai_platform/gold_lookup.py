import os
from functools import lru_cache
from pathlib import Path

from pyspark.sql import SparkSession, functions as F


@lru_cache(maxsize=1)
def create_spark() -> SparkSession:
    cache = Path("/tmp/enterprise-ai-spark")
    cache.mkdir(parents=True, exist_ok=True)
    endpoint = os.environ["MINIO_ENDPOINT"]
    jar_paths = sorted(Path("/opt/spark-jars").glob("*.jar"))
    if not jar_paths:
        raise RuntimeError("No Spark dependency JARs found in /opt/spark-jars")
    return (
        SparkSession.builder.master("local[2]")
        .appName("enterprise-ai-gold-lookup")
        .config("spark.sql.warehouse.dir", (cache / "warehouse").as_uri())
        .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
        .config(
            "spark.sql.catalog.spark_catalog",
            "org.apache.spark.sql.delta.catalog.DeltaCatalog",
        )
        .config("spark.sql.shuffle.partitions", "2")
        .config("spark.databricks.delta.snapshotPartitions", "2")
        .config("spark.ui.enabled", "false")
        .config("spark.hadoop.fs.s3a.endpoint", endpoint)
        .config("spark.hadoop.fs.s3a.path.style.access", "true")
        .config(
            "spark.hadoop.fs.s3a.connection.ssl.enabled",
            str(endpoint.startswith("https://")).lower(),
        )
        .config(
            "spark.hadoop.fs.s3a.aws.credentials.provider",
            "com.amazonaws.auth.EnvironmentVariableCredentialsProvider",
        )
        .config("spark.jars", ",".join(str(path) for path in jar_paths))
        .getOrCreate()
    )


def get_reconciliation_result(
    *, company: str, gl_id: str, allowed_companies: list[str]
) -> dict | None:
    if company not in allowed_companies:
        raise PermissionError("Company is outside the permitted scope.")

    run_id = os.environ["DEMO_RUN_ID"]
    bucket = os.environ["GOLD_BUCKET"]
    source = os.environ["GOLD_SOURCE_INSTANCE"]
    path = f"s3a://{bucket}/tables/bank_reconciliation/{run_id}"

    rows = (
        create_spark().read.format("delta").load(path)
        .where(
            (F.col("company") == company)
            & (F.col("demo_run_id") == run_id)
            & (F.col("source_instance") == source)
            & (F.col("gl_id") == gl_id)
        )
        .select(
            "company", "gl_id", "amount", "currency", "status",
            "reason", "rule_version", "coverage_complete",
            F.expr("transform(candidates, c -> c.transaction_id)").alias(
                "statement_candidate_ids"
            ),
        )
        .take(2)
    )

    if len(rows) > 1:
        raise RuntimeError("Multiple Gold rows for the same GL entry.")
    if not rows:
        return None

    result = rows[0].asDict()
    result["amount"] = format(result["amount"], ".2f")
    return result