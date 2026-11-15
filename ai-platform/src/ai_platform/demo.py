"""Deterministic citation-formatting example; not LLM inference."""


def answer(question: str, evidence: dict | None) -> str:
    if not question.strip():
        raise ValueError("question must not be empty")
    if not evidence or not evidence.get("text") or not evidence.get("source_id"):
        return "Insufficient evidence to answer."
    return f"Evidence: {evidence['text']} [source: {evidence['source_id']}]"


if __name__ == "__main__":
    print(answer("What is Bronze?", {"text": "Bronze stores source-aligned raw data for replay.", "source_id": "architecture/medallion"}))
