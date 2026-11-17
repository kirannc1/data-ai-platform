import json
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi import HTTPException
from pydantic import BaseModel, Field

from .gold_lookup import get_reconciliation_result

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
