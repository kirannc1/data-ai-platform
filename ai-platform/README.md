# AI platform starter

Merge this directory into the existing repository's `ai-platform/` directory.
Review any existing files with the same names before copying.

The shared FastAPI runtime loads and validates domain product manifests at
startup. The Finance manifest declares intended tool names, company scope,
and budgets. This milestone validates configuration and serves a health
check. Authorization and budget enforcement land with the first tool and
model integrations. The empty model allowlist means model selection is pending.

```mermaid
flowchart TB
    subgraph DOM["Domain-owned AI products"]
        FIN["Finance assistant (FastAPI or VS Code notebook)"]
        SPEC["Finance product configuration (Gold contract, policy, prompts, and eval cases)"]
        NEXT["Next domain (Own data, tools, prompts, and eval cases)"]
        SPEC --> FIN
    end

    subgraph PLATFORM["Shared AI platform"]
        ENTRY["Application gateway (FastAPI locally, API gateway and OIDC at scale)"]
        FLOW["Workflow runtime (Python locally, LangGraph for stateful orchestration)"]
        TOOL["Tool gateway and registry (Typed Python tools, MCP adapters where needed)"]
        CTX["Context builder (Evidence selection, scope checks, bounded history)"]
        PROMPT["Prompt builder and registry (Versioned templates in Git, token allocation)"]
        MODEL["Model gateway (Python provider adapter, Ollama or approved hosted models)"]
        VERIFY["Response validation (Schema, facts, citations, and review routing)"]

        ENTRY --> FLOW --> TOOL
        TOOL -->|"Authorized evidence"| CTX
        FLOW -->|"Question and workflow state"| CTX
        CTX --> PROMPT --> MODEL --> VERIFY
    end

    subgraph DATA["Domain-owned data and knowledge"]
        GOLD["Finance transaction evidence (Spark and Delta Lake on MinIO)"]
        DOC["Finance policy source (FIN-REC-001 Markdown in MinIO)"]
        INGEST["Document ingestion (Parse by section, attach metadata, publish index)"]
        INDEX["Versioned policy index (SQLite FTS locally, vector or hybrid search as needed)"]

        DOC --> INGEST --> INDEX
    end

    subgraph GOV["Shared governance and operations"]
        ACCESS["Identity and access (Company scope, service identities, secrets)"]
        SAFETY["Safety and privacy (Tool allowlists, redaction, injection checks)"]
        AUDIT["Observability and audit (Structured logs, OpenTelemetry, evidence lineage)"]
        FINOPS["FinOps (Token budgets, quotas, rate cards, usage ledger)"]
        RELEASE["Model and release governance (Registries, evaluations, CI gates, rollback)"]
    end

    FIN --> ENTRY
    NEXT --> ENTRY
    TOOL <-->|"Read-only Delta lookup"| GOLD
    TOOL <-->|"Retrieve approved clauses"| INDEX
    VERIFY -->|"Answer with citations"| FIN
    VERIFY -->|"Evidence gap or ambiguity"| REVIEW["Domain-owned human review"]

    ACCESS -.-> ENTRY
    ACCESS -.-> TOOL
    SAFETY -.-> CTX
    SAFETY -.-> VERIFY
    FLOW -.-> AUDIT
    MODEL -.-> AUDIT
    FINOPS -.-> MODEL
    RELEASE -.-> PROMPT
    RELEASE -.-> MODEL
```

## Docker Desktop Kubernetes smoke test

From the extracted `ai-platform/` folder, with Docker Desktop and its
Kubernetes cluster running:

```bash
kubectl config get-contexts
kubectl --context docker-desktop get nodes
docker build -t enterprise-ai-platform:0.1.0 .
kubectl --context docker-desktop apply -f deploy/k8s/platform.yaml
kubectl --context docker-desktop -n enterprise-ai rollout status deployment/ai-platform --timeout=120s
kubectl --context docker-desktop -n enterprise-ai port-forward service/ai-platform 18000:8000
```

In another terminal, run `curl http://127.0.0.1:18000/healthz` or open that URL
in a browser. Expect `{"status":"ok","registered_products":1}`.

The manifest assumes Kubernetes can see the Docker-built image. If a pod shows
`ErrImageNeverPull`, run `kubectl --context docker-desktop -n enterprise-ai describe pods`
to check the event. If the image is absent from the node, load it into your
cluster's image store or push it to a registry reachable by the node, then
update the image reference and pull policy accordingly.

## Next increment

Register the read-only Gold lookup as the first tool. Add policy retrieval,
context assembly, prompt rendering, model access, and governance enforcement
as the workflow takes shape.
