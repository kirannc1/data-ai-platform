import hashlib
import os
import re

import boto3
from botocore.config import Config

def get_shared_candidate_clause() -> dict:
    return get_policy_clause(
        os.environ["FINANCE_POLICY_SHARED_CANDIDATE_HEADING"]
    )

def get_policy_clause(heading: str) -> dict:
    bucket = os.environ.get("FINANCE_POLICY_BUCKET", "finance-policy-documents")
    key = os.environ["FINANCE_POLICY_OBJECT_KEY"]
    version = os.environ["FINANCE_POLICY_VERSION"]

    client = boto3.client(
        "s3",
        endpoint_url=os.environ["MINIO_ENDPOINT"],
        region_name="us-east-1",
        config=Config(
            s3={"addressing_style": "path"},
            connect_timeout=3,
            read_timeout=5,
            retries={"total_max_attempts": 2},
        ),
    )
    response = client.get_object(Bucket=bucket, Key=key)
    with response["Body"] as body:
        raw = body.read(262_145)
    if len(raw) > 262_144:
        raise ValueError("Finance policy exceeds the supported document size.")

    text = raw.decode("utf-8-sig")
    headings = list(re.finditer(r"^(#{1,6})[ \t]+(.+?)[ \t]*$", text, re.MULTILINE))
    matching = [item for item in headings if item.group(2).strip() == heading]
    if len(matching) != 1:
        raise ValueError("Expected exactly one matching Finance policy heading.")

    section = matching[0]
    end = next(
        (item.start() for item in headings
         if item.start() > section.start() and len(item.group(1)) <= len(section.group(1))),
        len(text),
    )

    return {
        "document_id": "FIN-REC-001",
        "version": version,
        "section": heading,
        "object_uri": f"s3://{bucket}/{key}",
        "content_sha256": hashlib.sha256(raw).hexdigest(),
        "excerpt": text[section.end():end].strip(),
    }