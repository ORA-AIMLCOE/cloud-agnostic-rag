# Validation record

Validated locally on **13 October 2026** using the user's existing `aws_rag_env` (Python 3.11),
Node.js 20.20.0, and npm 10.8.2. Later the same day, private RDS and an SSM bridge were provisioned,
the existing Managed Knowledge Base integration was verified live, and the limited app IAM role was tested.

| Check | Result |
|---|---|
| Backend pytest | **51 passed, 3 opt-in integration tests skipped** after PDF extraction regression coverage |
| Ruff lint and formatting | Passed |
| Python dependency consistency (`pip check`) | Passed |
| React TypeScript + Vite production build | Passed |
| Frontend Vitest | **3 passed** |
| npm dependency audit | **0 vulnerabilities reported** at installation |
| Headless Edge, built frontend + real FastAPI/LangGraph/SQLite + fake cloud ports | Passed upload → processing/ready → question → citations → persisted history/reload |
| Desktop/mobile visual inspection | Inspected 1440px desktop and 390px mobile; no horizontal overflow or page errors |
| Alembic upgrade → downgrade → upgrade on isolated SQLite | Passed |
| Alembic schema comparison (`alembic check`) | No pending schema changes |
| Terraform 1.13.5 + AWS provider 6.68.0 `init -backend=false`, `fmt`, `validate` | Passed; no plan/apply against AWS |
| Docker Compose configuration using `.env.example` | Passed |
| Docker image builds / running containers | **Not run: local Docker engine unavailable** |
| Live PostgreSQL / RDS, TLS and persistence | Passed migrations, hostname-verified TLS 1.3, app-user connection and persistence integration test; multi-process contention stress testing not performed |
| Live S3, Managed Bedrock sync/retrieval/inference, model access and grounding | Passed end-to-end upload, INDEXED status, metadata filters, answer with sources and persisted history using `aws-rag-app` |
| Explicit real AWS + PostgreSQL integration run | **2 passed in 173.67 seconds** |
| Corrected IAM policy | AWS Access Analyzer: no findings; deployed and tested through dedicated app role |
| Actual CloudWatch delivery | **Not run** |
| OCI adapters | **Not implemented**; scaffolds fail explicitly |

The browser validation used test fixtures, never simulated AWS success in the production provider factory.
Its temporary database and screenshots are under the ignored `.validation/` directory. The preview server
was stopped after checking. The committed pytest/Vitest suites provide repeatable local validation.

AWS SDK tests used botocore Stubber, which validates installed SDK request/response shapes but cannot prove
account IAM, region availability, vector metadata filtering, service quotas, or document parsing behavior.
Terraform validation proves configuration/schema consistency, not successful resource creation.

The live tests used account `649901308226` in Sydney and the resources recorded in
`infrastructure/aws/development-resources.json`. Synthetic validation documents remain for inspection.
See `your-aws-setup.md` for startup and cost-control instructions. CloudWatch delivery remains untested
because this deployment runs locally and logs to stdout. Do not report that skipped check as passed.

A subsequent real-PDF investigation found poor parsing of a very tall resume. See
`pdf-retrieval-fix.md` for the extraction fix, re-indexing, prompt improvements and live question checks.
