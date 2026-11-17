import json
import logging
import re
import os

from pathlib import Path
from fastapi import FastAPI
from fastapi import HTTPException
from pydantic import BaseModel, Field
from fastapi.responses import FileResponse

from typing import Annotated

from fastapi import HTTPException, Query
from pyspark.errors import AnalysisException
from pyspark.sql import functions as F

from .gold_lookup import get_reconciliation_result, list_reconciliation_results, get_reconciliation_evidence, search_reconciliation_gl_ids, summarize_reconciliation_run, get_statement_claims
from .policy_lookup import get_shared_candidate_clause, get_policy_clause, retrieve_policy
from .explanation import ExplanationContext, generate_explanation
from .policy_answer import answer_policy
from .investigation import investigate_reconciliation

class DataScope(BaseModel):
    companies: list[str] = Field(min_length=1)


class Limits(BaseModel):
    max_input_tokens: int = Field(gt=0)
    max_output_tokens: int = Field(gt=0)
    max_model_calls: int = Field(gt=0)


class Product(BaseModel):
    schema_version: int
    domain_id: str
    product_id: str
    owner: str
    data_scope: DataScope
    tools: list[str]
    approved_models: list[str]
    limits: Limits


domain_root = Path(__file__).resolve().parents[2] / "domains"
products = {}
for path in sorted(domain_root.glob("*/product.json")):
    product = Product.model_validate(json.loads(path.read_text(encoding="utf-8")))
    if product.schema_version != 1 or path.parent.name != product.product_id:
        raise ValueError(f"Invalid product manifest: {path}")
    if product.product_id in products:
        raise ValueError(f"Duplicate product ID: {product.product_id}")
    products[product.product_id] = product

if not products:
    raise RuntimeError("No domain product manifests found")

app = FastAPI(title="Enterprise AI Platform")
logger = logging.getLogger(__name__)

@app.get("/healthz")
def health() -> dict:
    return {"status": "ok", "registered_products": len(products)}


@app.get("/v1/finance/reconciliation/{gl_id}")
def read_reconciliation(gl_id: str, company: str) -> dict:
    product = products["finance-reconciliation"]
    try:
        result = get_reconciliation_result(
            company=company,
            gl_id=gl_id,
            allowed_companies=product.data_scope.companies,
        )
    except PermissionError:
        raise HTTPException(403, "Company is outside the permitted scope.") from None
    except Exception as exc:
        logger.error("Gold lookup failed: %s", type(exc).__name__)
        raise HTTPException(503, "Gold lookup unavailable.") from None

    if result is None:
        raise HTTPException(404, "GL entry not found in this Gold run.")

    return result

@app.get("/v1/finance/reconciliation")
def read_reconciliations(
    company: str,
    limit: int = Query(50, ge=1, le=100),
    after_gl_id: str | None = Query(None, min_length=1),
) -> dict:
    product = products["finance-reconciliation"]
    try:
        return list_reconciliation_results(
            company=company,
            allowed_companies=product.data_scope.companies,
            limit=limit,
            after_gl_id=after_gl_id,
        )
    except PermissionError:
        raise HTTPException(403, "Company is outside the permitted scope.") from None
    except Exception as exc:
        logger.error("Gold list lookup failed: %s", type(exc).__name__)
        raise HTTPException(503, "Gold lookup unavailable.") from None


@app.get("/chat", include_in_schema=False)
def chat_page() -> FileResponse:
    return FileResponse(Path(__file__).with_name("chat.html"), media_type="text/html")


@app.get("/v1/finance/chat/companies")
def chat_companies() -> dict[str, list[str]]:
    product = products["finance-reconciliation"]
    return {"companies": sorted(product.data_scope.companies)}


_GL_ID_PATTERN = re.compile(r"\bACC-GLE-\d{4}-\d+\b", re.IGNORECASE)

class FinanceChatRequest(BaseModel):
    company: str = Field(min_length=1, max_length=200)
    message: str = Field(min_length=1, max_length=2000)

def validate_reconciliation_evidence(
    evidence: dict, *, company: str, gl_id: str
) -> None:
    if evidence["company"] != company or evidence["gl_id"] != gl_id:
        raise ValueError("Gold returned evidence for a different entry.")

    candidate_ids = set(evidence["statement_candidate_ids"])
    for line in evidence["shared_statement_candidates"]:
        claimant_ids = line["claimant_gl_ids"]
        claimant_count = line["claimant_count"]

        if (
            evidence["status"] != "AMBIGUOUS"
            or line["transaction_id"] not in candidate_ids
            or claimant_count < 2
            or len(claimant_ids) != len(set(claimant_ids))
            or len(claimant_ids) != min(claimant_count, 20)
            or (claimant_count <= 20 and gl_id not in claimant_ids)
        ):
            raise ValueError("Gold returned inconsistent shared-candidate evidence.")

def explain_reconciliation(*, company: str, gl_id: str) -> dict:
    product = products["finance-reconciliation"]

    try:
        evidence = get_reconciliation_evidence(
            company=company,
            gl_id=gl_id,
            allowed_companies=product.data_scope.companies,
        )
    except PermissionError:
        raise HTTPException(403, "Company is outside the permitted scope.") from None
    except Exception as exc:
        logger.error("Gold evidence lookup failed: %s", type(exc).__name__)
        raise HTTPException(503, "Gold evidence unavailable.") from None

    if evidence is None:
        raise HTTPException(404, "GL entry not found in this Gold run.")

    try:
        validate_reconciliation_evidence(evidence, company=company, gl_id=gl_id)
    except (KeyError, TypeError, ValueError) as exc:
        logger.error("Invalid Gold evidence: %s", type(exc).__name__)
        raise HTTPException(503, "Gold evidence could not be verified.") from None

    citations = []
    if evidence["shared_statement_candidates"]:
        try:
            citations.append(get_shared_candidate_clause())
        except Exception as exc:
            logger.error("Finance policy lookup failed: %s", type(exc).__name__)
            raise HTTPException(503, "Finance policy unavailable.") from None

    context = ExplanationContext.model_validate({
        **evidence,
        "citations": citations,
    })

    return {
        **generate_explanation(context),
        "evidence": evidence,
        "citations": citations,
    }

@app.post("/v1/finance/chat")
def finance_chat(request: FinanceChatRequest) -> dict:
    company = request.company.strip()
    message = request.message.strip()
    if not message:
        raise HTTPException(422, "Enter a question.")

    allowed = products["finance-reconciliation"].data_scope.companies
    if company not in allowed:
        raise HTTPException(403, "Company is outside the permitted scope.")

    list_ids = re.fullmatch(r"list\s+gl\s+ids", message, re.IGNORECASE)
    search = re.fullmatch(r"search\s+gl\s+ids\s+(.+)", message, re.IGNORECASE)
    if list_ids or search:
        query = search.group(1).strip() if search else ""
        try:
            result = search_reconciliation_gl_ids(
                company=company, allowed_companies=allowed, query=query
            )
        except Exception as exc:
            logger.error("Gold ID search failed: %s", type(exc).__name__)
            raise HTTPException(503, "GL ID search unavailable.") from None

        ids = result["gl_ids"]
        if not ids:
            reply = f"No GL IDs found in Gold run {result['run_id']}."
        else:
            reply = f"GL IDs in Gold run {result['run_id']}.\n" + "\n".join(ids)
            if result["has_more"]:
                reply += "\nShowing the first 20. Narrow your search with a longer ID fragment."
        return {"reply": reply, **result}

    gl_ids = {match.upper() for match in _GL_ID_PATTERN.findall(message)}
    if len(gl_ids) > 1:
        return {"reply": "Please ask about one GL entry at a time."}
    if gl_ids:
        return explain_reconciliation(company=company, gl_id=next(iter(gl_ids)))

    run_request = re.fullmatch(
        r"(?:what should finance review(?:\s+in)?"
        r"|summarize(?:\s+the)?\s+(?:reconciliation\s+)?run)"
        r"(?:\s+(?:`(?P<quoted_run>[^`]+)`|(?P<plain_run>[A-Za-z0-9_-]+)"
        r"|(?P<current_run>this run|the current run)))?[?.!]?",
        message,
        re.IGNORECASE,
    )
    if re.fullmatch(
        r"what\s+exceptions\s+should\s+i\s+review\s+in\s+this\s+run"
        r"(?:\s*,?\s+and\s+why)?[?.!]?",
        message,
        re.IGNORECASE,
    ):
        try:
            return investigate_reconciliation(
                question=message, company=company, allowed_companies=allowed
            )
        except PermissionError:
            raise HTTPException(403, "Company is outside the permitted scope.") from None
        except Exception as exc:
            logger.error("Gold investigation failed: %s", type(exc).__name__)
            raise HTTPException(503, "Gold investigation unavailable.") from None
    if run_request:
        requested_run = run_request.group("quoted_run") or run_request.group("plain_run")

        try:
            summary = summarize_reconciliation_run(
                company=company, allowed_companies=allowed
            )
        except PermissionError:
            raise HTTPException(403, "Company is outside the permitted scope.") from None
        except Exception as exc:
            logger.error("Gold run summary failed: %s", type(exc).__name__)
            raise HTTPException(503, "Gold run summary unavailable.") from None

        run_id = summary["run_id"]
        if requested_run and requested_run != run_id:
            return {"reply": f"This deployment is configured for Gold run {run_id}."}

        counts = summary["status_counts"]
        lines = [
            f"Gold run {run_id} has {summary['total_entries']} GL entries for {company}."
        ]
        for status, count in counts.items():
            lines.append(f"{status}: {count}")

        for candidate in summary["shared_candidates"]:
            lines.append(
                f"Review statement transaction {candidate['transaction_id']}: "
                f"{candidate['claimant_count']} ambiguous GL entries claim that line."
            )
        if summary["more_shared_candidates"]:
            lines.append("Showing the first 10 shared statement candidates.")

        unmatched = counts.get("UNMATCHED", 0)
        if unmatched:
            lines.append(f"Review the {unmatched} unmatched entries separately.")

        return {
            "reply": "\n".join(lines),
            "generation_mode": "deterministic",
            "summary": summary,
        }

    handoff = re.fullmatch(
        r"prepare\s+a\s+note\s+for\s+finance\s+operations\s+about\s+"
        r"`?(TX-[A-Za-z0-9_-]+)`?[?.!]?",
        message,
        re.IGNORECASE,
    )
    if handoff:
        transaction_id = handoff.group(1).upper()

        try:
            claims = get_statement_claims(
                company=company,
                transaction_id=transaction_id,
                allowed_companies=allowed,
            )
        except PermissionError:
            raise HTTPException(403, "Company is outside the permitted scope.") from None
        except Exception as exc:
            logger.error("Statement claimant lookup failed: %s", type(exc).__name__)
            raise HTTPException(503, "Statement evidence unavailable.") from None

        run_id = claims["run_id"]
        statement_lines = claims["statement_lines"]

        if not statement_lines:
            return {"reply": f"No GL candidates reference {transaction_id} in {run_id}."}
        if len(statement_lines) > 1:
            return {
                "reply": f"{transaction_id} appears in multiple statement files in "
                        f"{run_id}. Specify the statement file before drafting a note."
            }

        line = statement_lines[0]
        count = line["claimant_count"]
        ids = line["claimant_gl_ids"]
        label = "GL entries shown" if len(ids) < count else "GL entries"

        reply = "\n".join([
            f"Draft for Finance Operations — {transaction_id}",
            "",
            f"Please review statement transaction {transaction_id} for {company} "
            f"in Gold run {run_id}. Gold lists this statement line as a candidate "
            f"for {count} GL entries.",
            f"{label}: {', '.join(ids)}.",
            "Please confirm the correct allocation against the bank statement "
            "and supporting records.",
        ])
        return {
            "reply": reply,
            "generation_mode": "deterministic",
            "summary": claims,
        }
    question = message.casefold()
    if not any(term in question for term in (
        "coverage", "unmatched", "ambiguous", "conflicting account mapping"
    )):
        return {
            "reply": "Include a GL ID, type 'list GL IDs' or 'summarize run', "
                     "or ask about statement coverage or review rules."
        }

    try:
        citation = retrieve_policy(
            question=message,
            company=company,
            allowed_companies=allowed,
        )
    except PermissionError:
        raise HTTPException(403, "Finance policy is outside the permitted scope.") from None
    except Exception as exc:
        logger.error("Finance policy lookup failed: %s", type(exc).__name__)
        raise HTTPException(503, "Finance policy unavailable.") from None

    return answer_policy(question=message, citation=citation)

@app.get("/v1/finance/reconciliation/{gl_id}/explanation")
def read_reconciliation_explanation(gl_id: str, company: str) -> dict:
    return explain_reconciliation(company=company.strip(), gl_id=gl_id.strip().upper())

    