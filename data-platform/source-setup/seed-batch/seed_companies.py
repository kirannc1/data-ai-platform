"""Seed each demo company into its own reconciliation run."""
import argparse
import json
import re
from pathlib import Path
from types import SimpleNamespace

from seed_batch import load_fixtures, seed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    profiles = json.loads((root / "companies.json").read_text(encoding="utf-8"))
    if not profiles:
        parser.error("Add at least one company to companies.json")

    batches = []
    company_names, run_ids, account_ids = set(), set(), set()
    for profile in profiles:
        company_id = profile["id"]
        run_id = f"{args.batch_id}-{company_id}"
        if not re.fullmatch(r"[A-Za-z0-9_-]+", company_id) or not re.fullmatch(
            r"[A-Za-z0-9_-]{1,80}", run_id
        ):
            parser.error(f"Invalid company ID or run ID: {run_id}")
        company = profile["company"]
        if company in company_names or run_id in run_ids:
            parser.error("Each profile needs a distinct company and ID")
        if any(not profile[field].strip() for field in ("company", "bank_gl", "expense_gl")):
            parser.error(f"Missing company or ledger for {company_id}")
        if profile["bank_gl"] == profile["expense_gl"]:
            parser.error(f"Bank and expense ledgers must differ for {company_id}")
        fixtures = load_fixtures(root / "fixtures" / company_id)
        mapped_accounts = {row["bank_account_id"] for row in fixtures[1]}
        if account_ids & mapped_accounts:
            parser.error("Demo bank account IDs must be distinct across companies")
        if any(row["bank_account_id"] not in mapped_accounts for row in fixtures[2]):
            parser.error(f"Statement account without a mapping for {company_id}")
        account_ids.update(mapped_accounts)
        company_names.add(company)
        run_ids.add(run_id)
        batches.append((profile, run_id, fixtures))
        print(f"{run_id}: {len(fixtures[0])} journals, {len(fixtures[1])} mappings, "
              f"{len(fixtures[2])} statement rows", flush=True)

    if args.validate_only:
        return
    if not args.env_file or not args.env_file.is_file():
        parser.error("Provide --env-file pointing to data-platform/.env")

    from dotenv import dotenv_values

    shared = dotenv_values(args.env_file, interpolate=False)
    for profile, run_id, fixtures in batches:
        config = {
            **shared,
            "ERPNEXT_COMPANY": profile["company"],
            "ERPNEXT_BANK_ACCOUNT": profile["bank_gl"],
            "ERP_SEED_EXPENSE_ACCOUNT": profile["expense_gl"],
        }
        seed(SimpleNamespace(run_id=run_id), config, fixtures)


if __name__ == "__main__":
    main()
