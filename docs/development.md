# Development in VS Code

Open the repository root in VS Code. Install the Python extension and, for AI-assisted changes, the Codex extension. GitHub Copilot is optional for inline suggestions.

Create a virtual environment with Python 3.11 or 3.12 and select it using **Python: Select Interpreter** in the Command Palette.

```bash
python -m venv .venv
# macOS/Linux: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pytest -q
python -m data_platform.demo
```

Use the integrated terminal from the repository root. The bootstrap tests also run in GitHub Actions. Use Docker Compose for the [ERPNext and PostgreSQL sources](../data-platform/source-setup/README.md).

## Working with Codex

Give Codex one acceptance criterion at a time. Ask it to run the relevant tests and review the diff before committing. Keep credentials out of prompts and Git, and use synthetic data.

For reconciliation, preserve raw inputs for replay, use fixed-precision amounts, and make retries idempotent. One acceptance case is a Friday ledger payment that stays outstanding at Friday's cutoff and matches when Monday's statement arrives.

## Data Platform handoff to AI

The local reference milestone is complete when the bank file, ERPNext REST feed, PostgreSQL mapping, and simulated Kafka settlement feed land with traceable source IDs, can be replayed without duplicate results, and produce verified Gold matches and exceptions. Verify the Friday-to-Monday case and the bank fee awaiting a ledger posting. The Gold exception interface is the starting point for the AI workflow.
