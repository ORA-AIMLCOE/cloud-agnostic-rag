# Distributor Aggregator

An AWS-backed question-answering app for BlueDart, Delhivery, Ekart and DTDC. One administrator-prepared document is ingested ahead of time; users ask questions and receive answers with source citations. The included document contains clearly labelled fictional demo data.

The React frontend, FastAPI API and LangGraph workflow retain the existing S3, Bedrock Knowledge Base, embedding model, answer model and RDS integrations. Distributor mode isolates questions and history to the active document. Document uploads are managed through a local administrator command.

## Run and integrate

Follow [the local run guide and API contract](docs/distributor-aggregator.md). The local UI is at http://127.0.0.1:5173/ and the authenticated integration endpoint is `POST http://127.0.0.1:8000/api/v1/answers`.

The current distributor update is local. The [existing VM runbook](docs/oci-vm-deployment.md) describes the earlier deployment; the new version has not been deployed there. OCI conversion remains a later step.

Keep the existing private `.env`; do not overwrite it with a template. Start the database tunnel with `scripts/start-db-tunnel.ps1`, apply migrations, start the backend on loopback port 8000, and start the frontend on port 5173. See the linked guide for exact commands, ingestion, rollback, API keys, and five demo questions.

## Test without AWS credentials

```powershell
cd backend
python -m pytest -q
python -m ruff check app tests alembic
cd ../frontend
npm ci
npm run build
npm test
```

Tests use provider fakes and SDK Stubber. Real AWS/PostgreSQL/CloudWatch tests require `--run-integration`
and configured endpoints; see [testing](docs/testing.md) and [validation results](docs/validation.md).

## Project structure

```text
aws_rag/
├── frontend/                  React + TypeScript, Vite, UI tests, Nginx, Docker
├── backend/
│   ├── app/
│   │   ├── api/               Stable routes and request/response contracts
│   │   ├── core/              Settings and dependency injection
│   │   ├── domain/            Provider-neutral models and errors
│   │   ├── interfaces/        LLM, storage, search, ingestion and repository ports
│   │   ├── providers/aws/     Real AWS adapters
│   │   ├── providers/oci/     Explicit unimplemented extension points
│   │   ├── providers/factory.py
│   │   ├── services/          Document validation and indexing lifecycle
│   │   ├── workflows/         LangGraph + reusable prompt
│   │   ├── database/          SQLAlchemy models and sessions
│   │   ├── repositories/      Cloud-independent persistence
│   │   └── observability/     JSON stdout + correlation IDs
│   ├── alembic/               Versioned schema migrations
│   ├── tests/                 Unit, contract, adapter and opt-in integration tests
│   ├── requirements.txt       Dependency ranges
│   ├── requirements.lock.txt  Tested versions
│   └── Dockerfile
├── infrastructure/aws/        Terraform foundation + ECS deployment template
├── infrastructure/oci/        Future infrastructure notes
├── docs/                      Architecture, setup, migration and validation
├── .env.example
└── docker-compose.yml
```

## API

| Method | Route | Behavior |
|---|---|---|
| POST | `/api/documents/upload` | Disabled in distributor mode; use the administrator ingestion command |
| GET | `/api/documents` | Active distributor document only |
| GET | `/api/documents/{id}/status` | Reconcile indexing/searchability and retry queued starts |
| POST | `/api/questions/ask` | Browser route; JSON `{ "question": "..." }`, active document selected automatically |
| POST | `/api/v1/answers` | Integration route; Bearer API key and JSON `{ "question": "..." }` |
| GET | `/api/knowledge` | Active document readiness, version and demo-data label |
| GET | `/api/questions/history` | Active document history; `limit`, `offset` |
| GET | `/api/health` | Liveness |
| GET | `/api/readiness` | Database, configured index and active knowledge checks |

Errors use `{ "error": { "code", "message", "request_id" } }`. Successful answers include question, answer,
document ID, actual retrieved source references, model ID, timestamps and latency. Provider exceptions are
sanitized; normal logs omit question/answer text, document contents, credentials and raw SDK responses.

## Scope and migration

This is a **shared-workspace POC without per-user or tenant isolation**. The integration route requires an API key;
browser routes require loopback access or an authenticated private gateway. The `owner_id` field is scaffolding,
not access control. No OCR, durable background worker, chat-memory
grounding, streaming responses, or automatic replay deduplication is included. Failed model/retrieval/database
requests do not create successful history entries; a disconnect after commit can leave an answer in history.

The Bedrock vector backend is separate from the PostgreSQL Q&A database. Conventional VECTOR/S3 and
Managed Knowledge Bases with managed S3 connectors are supported. Prompts and citation validation reduce unsupported
answers but do not mathematically establish their correctness. Check source excerpts.

For OCI, implement the four files in `backend/app/providers/oci/`, update `providers/factory.py`, configuration
and bootstrap wiring, dependencies, and OCI infrastructure. Migrate documents/history and rebuild the vector
index. The frontend, routes, services, graph, models, interfaces and database schema remain unchanged.
See the exact file list and cutover steps in [OCI migration](docs/oci-migration.md).

- [Architecture and lifecycle](docs/architecture.md)
- [AWS setup, IAM, deployment, costs and cleanup](docs/aws-setup.md)
- [Testing and cloud acceptance](docs/testing.md)
- [Validation results and remaining checks](docs/validation.md)
