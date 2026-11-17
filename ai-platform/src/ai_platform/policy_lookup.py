import hashlib
import os
import re
import boto3
import json
import logging
import math
from functools import lru_cache
from urllib.request import Request, urlopen
from botocore.config import Config

logger = logging.getLogger(__name__)

def get_shared_candidate_clause() -> dict:
    return get_policy_clause(
        os.environ["FINANCE_POLICY_SHARED_CANDIDATE_HEADING"]
    )

def _read_policy() -> tuple[str, dict[str, str]]:
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

    return raw.decode("utf-8-sig"), {
        "document_id": "FIN-REC-001",
        "version": version,
        "object_uri": f"s3://{bucket}/{key}",
        "content_sha256": hashlib.sha256(raw).hexdigest(),
    }

def _policy_sections(text: str, metadata: dict, *, include_subsections: bool) -> list[dict]:
    headings = list(re.finditer(
        r"^(#{1,6})[ \t]+(.+?)[ \t]*$", text, re.MULTILINE
    ))
    sections = []

    for index, heading in enumerate(headings):
        depth = len(heading.group(1))
        end = next(
            (
                item.start()
                for item in headings[index + 1:]
                if not include_subsections or len(item.group(1)) <= depth
            ),
            len(text),
        )
        excerpt = text[heading.end():end].strip()
        if excerpt:
            sections.append({
                **metadata,
                "section": heading.group(2).strip(),
                "excerpt": excerpt,
            })

    return sections

def get_policy_clause(heading: str) -> dict:
    text, metadata = _read_policy()
    matches = [
        section for section in _policy_sections(
            text, metadata, include_subsections=True
        )
        if section["section"] == heading
    ]
    if len(matches) != 1:
        raise ValueError("Expected exactly one matching Finance policy heading.")
    return matches[0]

def _embed(texts: list[str], *, base_url: str, model: str) -> list[list[float]]:
    request = Request(
        f"{base_url.rstrip('/')}/api/embed",
        data=json.dumps({
            "model": model,
            "input": texts,
            "truncate": False,
        }).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=15) as response:
        vectors = json.load(response)["embeddings"]

    if len(vectors) != len(texts):
        raise ValueError("Embedding response count differs from the request.")

    normalized = []
    dimension = len(vectors[0])
    for vector in vectors:
        if len(vector) != dimension or not all(math.isfinite(value) for value in vector):
            raise ValueError("Invalid embedding vector.")
        norm = math.hypot(*vector)
        if not norm or not math.isfinite(norm):
            raise ValueError("Invalid embedding norm.")
        normalized.append([value / norm for value in vector])
    return normalized

@lru_cache(maxsize=4)
def _policy_index(
    bucket: str, key: str, version: str, companies: tuple[str, ...],
    base_url: str, model: str,
) -> tuple:
    text, metadata = _read_policy()
    sections = _policy_sections(text, metadata, include_subsections=False)
    if not sections:
        raise ValueError("No sections found in Finance policy.")

    vectors = _embed(
        [f"{item['section']}\n{item['excerpt']}" for item in sections],
        base_url=base_url,
        model=model,
    )
    return tuple(
        ({**section, "allowed_companies": companies}, vector)
        for section, vector in zip(sections, vectors, strict=True)
    )

def retrieve_policy(
    *, question: str, company: str, allowed_companies: list[str]
) -> dict:
    policy_companies = tuple(sorted({
        name.strip()
        for name in os.environ["FINANCE_POLICY_COMPANIES"].split(",")
        if name.strip()
    }))
    if company not in allowed_companies or company not in policy_companies:
        raise PermissionError("Finance policy is outside the permitted scope.")

    bucket = os.environ.get("FINANCE_POLICY_BUCKET", "finance-policy-documents")
    key = os.environ["FINANCE_POLICY_OBJECT_KEY"]
    version = os.environ["FINANCE_POLICY_VERSION"]
    base_url = os.environ["OLLAMA_BASE_URL"]
    model = os.environ.get("POLICY_EMBEDDING_MODEL", "embeddinggemma")

    index = _policy_index(bucket, key, version, policy_companies, base_url, model)
    eligible = [
        (section, vector)
        for section, vector in index
        if company in section["allowed_companies"] and section["version"] == version
    ]
    if not eligible:
        raise LookupError("No applicable Finance policy sections.")

    query_vector = _embed([question], base_url=base_url, model=model)[0]

    def similarity(item: tuple) -> float:
        return math.fsum(
            left * right for left, right in zip(item[1], query_vector, strict=True)
        )

    section, _ = max(eligible, key=similarity)
    return {key: value for key, value in section.items() if key != "allowed_companies"}