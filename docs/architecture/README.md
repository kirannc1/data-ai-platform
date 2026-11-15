# Architecture sources and scope

`azure-enterprise-data-platform.drawio` is the supplied four-page target-state diagram:
1. Azure Landing Zone (CAF, platform/workload subscriptions and central controls)
2. Hub-spoke network (private connectivity and company workload isolation)
3. End-to-end data platform (ingestion, company-isolated landing, Bronze/Silver/Gold, MDM, consolidation, consumption)
4. Gold financial star schema (`Fact_GL_Transaction` and conformed dimensions)

`ed-interview-cheatsheet-v3.html` is the accompanying conceptual/logical/physical mapping and finance delivery reference. The initial local Python implementation intentionally implements only a thin vertical slice. Azure provisioning and service parity are out of scope for bootstrap.

The AI Harness design is summarized in the root README. Upload/re-add its original HTML architecture document when available to include a copy in this repository.
