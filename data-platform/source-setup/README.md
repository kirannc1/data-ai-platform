# Local bank reconciliation sources

Install Docker with the Compose plugin, and Git. Use synthetic records in these disposable environments.

## ERPNext

Run the official demo from a directory outside this repository:

```bash
git clone https://github.com/frappe/frappe_docker.git
cd frappe_docker
docker compose -p reconciliation-erp -f pwd.yml up -d
docker compose -p reconciliation-erp -f pwd.yml logs -f create-site

$seed = "..\enterprise-data-ai-platform\data-platform\source-setup"

docker compose -p reconciliation-erp -f pwd.yml cp "$seed" backend:/tmp/seed_erpnext_demo.py
docker compose -p reconciliation-erp -f pwd.yml exec -T -w /home/frappe/frappe-bench backend ./env/bin/python -u /tmp/seed_erpnext_demo.py frontend
```

Once site initialization completes, open http://localhost:8080. Use the demo on a trusted local machine. Create a demo company in INR with a bank and an expense account. Submit a balanced journal that debits the expense and credits the bank by INR 10,000. Record the exact company and bank ledger account names.

Give a separate API user read access to the relevant GL Entry records. Verify that a GET request to `/api/resource/GL%20Entry` filtered to the company and bank account returns the posted credit and a stable record identifier. Keep API credentials out of Git.

## PostgreSQL

From this directory, edit `seed.sql` to match the ERP company and account names before the first start. The seed runs on a fresh database volume.

```bash
docker compose -p reconciliation-db -f ..\data-ai-platform\data-platform\source-setup\compose.yaml config --services
docker compose -p reconciliation-db -f ..\data-ai-platform\data-platform\source-setup\compose.yaml up -d
docker compose -p reconciliation-db -f ..\data-ai-platform\data-platform\source-setup\compose.yaml exec postgres psql -U demo -d reconciliation -c "SELECT * FROM bank_account_mapping;"
```

Run the query once initialization completes. Expect one mapping for `BANK-INR-001`. PostgreSQL listens on localhost port 5433 for host clients.

## Redpanda for events and MinIO for file storage

| Component | Role in bank reconciliation | First demo input |
|---|---|---|
| MinIO | Stores original bank statement files for ingestion and replay | A synthetic CSV with a ₹10,000 withdrawal |
| Redpanda | Delivers events that trigger ingestion | A `bank.statement.received` event pointing to the CSV in MinIO |

```bash
docker compose -p reconciliation-sources -f compose.sources.yml up -d
docker compose -p reconciliation-sources -f compose.sources.yml ps
```

MinIO — Open the console, sign in with demo-storage / demo-storage-local, and create a bucket named bank-statements. The S3 API endpoint is http://localhost:19000.

Redpanda — Create the bank.statement.received topic and verify it appears in the broker:
```
docker compose -p reconciliation-sources -f compose.sources.yml exec -T redpanda rpk topic create bank.statement.received -X brokers=redpanda:9092
docker compose -p reconciliation-sources -f compose.sources.yml exec -T redpanda rpk topic list -X brokers=redpanda:9092
```


## First integration check

Use the mapping to select the ERP cash account. Confirm that the posted INR 10,000 credit matches a synthetic statement withdrawal for the mapped account, using the payment reference where available. The statement generator and Kafka producer are later implementation steps.

## Teardown

These commands delete the respective demo volumes and their data. Run each from its own Compose directory.

```bash
docker compose -p reconciliation-db down -v
docker compose -p reconciliation-erp -f pwd.yml down -v
```

For Kubernetes, reuse the seed SQL and ingestion interfaces. Supply the workload, storage, services, and credentials through cluster deployment configuration.
