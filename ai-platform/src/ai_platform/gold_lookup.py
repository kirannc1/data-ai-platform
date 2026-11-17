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

def search_reconciliation_gl_ids(
    *,
    company: str,
    allowed_companies: list[str],
    query: str,
    limit: int = 20,
) -> dict:
    if company not in allowed_companies:
        raise PermissionError("Company is outside the permitted scope.")
    if not 1 <= limit <= 100:
        raise ValueError("Limit must be between 1 and 100.")

    run_id = os.environ["DEMO_RUN_ID"]
    bucket = os.environ["GOLD_BUCKET"]
    source = os.environ["GOLD_SOURCE_INSTANCE"]
    path = f"s3a://{bucket}/tables/bank_reconciliation/{run_id}"

    scope = (
        (F.col("company") == company)
        & (F.col("demo_run_id") == run_id)
        & (F.col("source_instance") == source)
    )
    rows = (
        create_spark().read.format("delta").load(path)
        .where(scope & F.upper(F.col("gl_id")).contains(query.strip().upper()))
        .select("gl_id")
        .distinct()
        .orderBy("gl_id")
        .take(limit + 1)
    )
    return {
        "run_id": run_id,
        "gl_ids": [row["gl_id"] for row in rows[:limit]],
        "has_more": len(rows) > limit,
    }

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

def list_reconciliation_results(
    *,
    company: str,
    allowed_companies: list[str],
    limit: int = 50,
    after_gl_id: str | None = None,
) -> dict:
    if company not in allowed_companies:
        raise PermissionError("Company is outside the permitted scope.")

    run_id = os.environ["DEMO_RUN_ID"]
    bucket = os.environ["GOLD_BUCKET"]
    source = os.environ["GOLD_SOURCE_INSTANCE"]
    path = f"s3a://{bucket}/tables/bank_reconciliation/{run_id}"

    results = create_spark().read.format("delta").load(path).where(
        (F.col("company") == company)
        & (F.col("demo_run_id") == run_id)
        & (F.col("source_instance") == source)
    )

    if after_gl_id is not None:
        results = results.where(F.col("gl_id") > after_gl_id)

    rows = (
        results.select(
            "company", "gl_id", "amount", "currency", "status",
            "reason", "rule_version", "coverage_complete",
            F.expr("transform(candidates, c -> c.transaction_id)").alias(
                "statement_candidate_ids"
            ),
        )
        .orderBy("gl_id")
        .take(limit + 1)
    )

    items = []
    for row in rows[:limit]:
        item = row.asDict()
        item["amount"] = format(item["amount"], ".2f")
        items.append(item)

    return {
        "company": company,
        "run_id": run_id,
        "count": len(items),
        "next_after_gl_id": items[-1]["gl_id"] if len(rows) > limit else None,
        "items": items,
    }

def get_reconciliation_evidence(
    *, company: str, gl_id: str, allowed_companies: list[str]
) -> dict | None:
    if company not in allowed_companies:
        raise PermissionError("Company is outside the permitted scope.")

    run_id = os.environ["DEMO_RUN_ID"]
    bucket = os.environ["GOLD_BUCKET"]
    source = os.environ["GOLD_SOURCE_INSTANCE"]
    path = f"s3a://{bucket}/tables/bank_reconciliation/{run_id}"

    scoped = create_spark().read.format("delta").load(path).where(
        (F.col("company") == company)
        & (F.col("demo_run_id") == run_id)
        & (F.col("source_instance") == source)
    )

    rows = (
        scoped.where(F.col("gl_id") == gl_id)
        .select("gl_id", "amount", "currency", "status", "reason",
                "rule_version", "coverage_complete", "candidates")
        .take(2)
    )
    if not rows:
        return None
    if len(rows) > 1:
        raise RuntimeError("Multiple Gold rows for the same GL entry.")

    result = rows[0].asDict(recursive=True)
    result["amount"] = format(result["amount"], ".2f")
    candidates = result.pop("candidates") or []
    result["statement_candidate_ids"] = [
        candidate["transaction_id"] for candidate in candidates
    ]

    shared = []
    if result["status"] == "AMBIGUOUS" and candidates:
        target_lines = (
            scoped.where(F.col("gl_id") == gl_id)
            .select(F.explode("candidates").alias("line"))
            .select("line.raw_uri", "line.transaction_id")
            .distinct()
        )
        all_claims = (
            scoped.select("gl_id", F.explode("candidates").alias("line"))
            .select("gl_id", "line.raw_uri", "line.transaction_id")
        )
        matches = (
            all_claims.join(target_lines, ["raw_uri", "transaction_id"])
            .groupBy("raw_uri", "transaction_id")
            .agg(
                F.countDistinct("gl_id").alias("claimant_count"),
                F.slice(F.sort_array(F.collect_set("gl_id")), 1, 20)
                .alias("claimant_gl_ids"),
            )
            .where(F.col("claimant_count") > 1)
            .orderBy("raw_uri", "transaction_id")
            .take(21)
        )
        if len(matches) > 20:
            raise RuntimeError("Too many shared candidates for one explanation.")
        shared = [row.asDict() for row in matches]

    return {
        **result,
        "company": company,
        "run_id": run_id,
        "shared_statement_candidates": shared,
    }

def summarize_reconciliation_run(
    *, company: str, allowed_companies: list[str]
) -> dict:
    if company not in allowed_companies:
        raise PermissionError("Company is outside the permitted scope.")

    run_id = os.environ["DEMO_RUN_ID"]
    bucket = os.environ["GOLD_BUCKET"]
    source = os.environ["GOLD_SOURCE_INSTANCE"]
    path = f"s3a://{bucket}/tables/bank_reconciliation/{run_id}"

    scoped = create_spark().read.format("delta").load(path).where(
        (F.col("company") == company)
        & (F.col("demo_run_id") == run_id)
        & (F.col("source_instance") == source)
    )

    status_counts = {
        row["status"]: row["count"]
        for row in scoped.groupBy("status").count().orderBy("status").collect()
    }

    shared_candidates = (
        scoped.where(F.col("status") == "AMBIGUOUS")
        .select("gl_id", F.explode("candidates").alias("candidate"))
        .select(
            "gl_id",
            F.col("candidate.raw_uri").alias("raw_uri"),
            F.col("candidate.transaction_id").alias("transaction_id"),
        )
        .groupBy("raw_uri", "transaction_id")
        .agg(
            F.countDistinct("gl_id").alias("claimant_count"),
            F.min("gl_id").alias("example_gl_id"),
        )
        .where(F.col("claimant_count") > 1)
        .orderBy(F.desc("claimant_count"), "raw_uri", "transaction_id")
        .take(11)
    )

    return {
        "company": company,
        "run_id": run_id,
        "total_entries": sum(status_counts.values()),
        "status_counts": status_counts,
        "shared_candidates": [row.asDict() for row in shared_candidates[:10]],
        "more_shared_candidates": len(shared_candidates) > 10,
    }

def get_statement_claims(
    *, company: str, transaction_id: str, allowed_companies: list[str]
) -> dict:
    if company not in allowed_companies:
        raise PermissionError("Company is outside the permitted scope.")

    run_id = os.environ["DEMO_RUN_ID"]
    bucket = os.environ["GOLD_BUCKET"]
    source = os.environ["GOLD_SOURCE_INSTANCE"]
    path = f"s3a://{bucket}/tables/bank_reconciliation/{run_id}"

    scoped = create_spark().read.format("delta").load(path).where(
        (F.col("company") == company)
        & (F.col("demo_run_id") == run_id)
        & (F.col("source_instance") == source)
    )

    lines = (
        scoped.select("gl_id", F.explode("candidates").alias("candidate"))
        .where(
            F.upper(F.col("candidate.transaction_id")) == transaction_id.upper()
        )
        .groupBy("candidate.raw_uri", "candidate.transaction_id")
        .agg(
            F.countDistinct("gl_id").alias("claimant_count"),
            F.slice(F.sort_array(F.collect_set("gl_id")), 1, 20)
            .alias("claimant_gl_ids"),
        )
        .take(2)
    )

    return {"run_id": run_id, "statement_lines": [row.asDict() for row in lines]}