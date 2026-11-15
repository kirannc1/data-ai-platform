# AI platform

Target harness: Silver document parsing -> chunking -> embeddings/index -> authorized retrieval -> context assembly -> model gateway -> citation-first grounded generation -> tools/agents/A2A, with evaluation, identity, safety, tracing and cost controls.

**Included bootstrap:** standard-library-only demo that formats an answer from a supplied evidence record with a source citation and abstains when evidence is missing. This is a deterministic demonstration, **not** an LLM, vector retrieval, groundedness evaluator, model gateway or A2A implementation.

Run from repository root:

```bash
python -m ai_platform.demo
python -m pytest ai-platform/tests -q
```

Next labs: chunking, local embeddings, FAISS or Qdrant, ACL-aware retrieval, grounded prompt and citation validation, LiteLLM gateway, LangGraph agent, real A2A protocol service adapter and regression evaluation.
