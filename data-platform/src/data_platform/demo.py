"""Minimal reproducible Bronze/Silver/Gold example. Not a Delta implementation."""
from pathlib import Path
import duckdb

ROOT = Path(__file__).resolve().parents[3]
INPUT = ROOT / "data-platform" / "data" / "sample" / "gl_journal.csv"
OUTPUT = ROOT / "outputs" / "data-platform"


def run(input_path: Path = INPUT, output_dir: Path = OUTPUT) -> dict[str, int]:
    output_dir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(":memory:")
    try:
        con.execute("CREATE TABLE bronze AS SELECT *, current_timestamp AS ingested_at FROM read_csv_auto(?)", [str(input_path)])
        con.execute("CREATE TABLE silver AS SELECT company, journal_id, line_id, account, CAST(posting_date AS DATE) AS posting_date, currency, CAST(debit AS DOUBLE) AS debit, CAST(credit AS DOUBLE) AS credit, CAST(credit - debit AS DOUBLE) AS signed_amount FROM bronze WHERE company IS NOT NULL AND journal_id IS NOT NULL AND debit >= 0 AND credit >= 0")
        con.execute("CREATE TABLE gold AS SELECT company, account, currency, SUM(signed_amount) AS net_amount, COUNT(*) AS journal_lines FROM silver GROUP BY company, account, currency")
        for layer in ("bronze", "silver", "gold"):
            con.execute(f"COPY {layer} TO ? (FORMAT PARQUET)", [str(output_dir / f"{layer}.parquet")])
        return {layer: con.execute(f"SELECT COUNT(*) FROM {layer}").fetchone()[0] for layer in ("bronze", "silver", "gold")}
    finally:
        con.close()


if __name__ == "__main__":
    print("Data platform bootstrap rows:", run())
