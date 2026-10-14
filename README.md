# aws_rag

A document question-answering application built with React, FastAPI, LangGraph and PostgreSQL.
AWS adapters provide S3 storage, Bedrock Knowledge Base retrieval/indexing, and Bedrock Converse inference.
The frontend, APIs, domain models, workflow and persistence are provider independent. OCI adapters are explicit
future extension points, not a working OCI deployment.

## Start with your existing environment

Your Sydney AWS setup is configured. Follow [your verified run instructions](docs/your-aws-setup.md),
including the private database tunnel. The personalized `.env.example` contains the database password
and is excluded from Git. The generic local-Docker alternative follows below.

From this project directory in PowerShell:

```powershell
& 'C:\Users\adarshmi\Desktop\EXPLORE\0_virtual_environment\aws_rag_env\Scripts\Activate.ps1'
python -m pip install -r backend/requirements.lock.txt
Copy-Item .env.example .env
```

Set `.env` with your AWS region, Converse model/inference-profile ID, private S3 bucket,
Knowledge Base ID and S3 data-source ID. Set `AWS_KB_MODE=managed` for a Managed Knowledge Base,
or `conventional` for a customer-managed VECTOR KB. `AWS_PROFILE` in `.env` selects the local profile;
omit it to use the default credential chain or an AWS workload role.

Start a local PostgreSQL database (Docker Desktop must be running):

```powershell
docker compose up -d postgres
cd backend
python -m alembic upgrade head
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --no-access-log
```

In a second terminal:

```powershell
cd frontend
npm ci
npm run dev
```

Open **http://localhost:5173**. Backend API docs are at **http://localhost:8000/docs**.
Check `/api/readiness` before uploading. Use PDF, UTF-8 TXT, or Markdown up to 10 MB. Q&A is enabled only when
indexing and document-filtered retrieval confirm readiness. Sources expand to the retrieved text; History
persists across page reloads. Keep the page open to retry queued ingestion automatically.

With Managed Knowledge Bases, PDFs must have a readable native text layer on every page. The app retains
the original PDF and indexes extracted text, avoiding image-caption summaries of dense layouts. Scanned
PDFs need OCR first. The extraction limits are 200 pages and two million text characters per PDF.

If using an existing PostgreSQL/RDS database, set DATABASE_URL and skip the local Postgres command.
RDS requires private network access and TLS; the [AWS guide](docs/aws-setup.md) covers this and infrastructure setup.
No resources are automatically created by starting the application.

To run all application services in Docker with a local AWS profile:

```powershell
docker compose -f docker-compose.yml -f docker-compose.profile.yml up --build
```

Open http://localhost:8080. The migration container applies Alembic before backend startup. Compose uses a
local database; use the ECS deployment template for RDS/CloudWatch deployments.

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
| POST | `/api/documents/upload` | Multipart field `file`; persist and request indexing |
| GET | `/api/documents` | Paginated documents (`limit`, `offset`) |
| GET | `/api/documents/{id}/status` | Reconcile indexing/searchability and retry queued starts |
| POST | `/api/questions/ask` | JSON `{ "document_id": "...", "question": "..." }` |
| GET | `/api/questions/history` | Optional `document_id`, `limit`, `offset` |
| GET | `/api/health` | Liveness |
| GET | `/api/readiness` | Database/schema and configured index checks |

Errors use `{ "error": { "code", "message", "request_id" } }`. Successful answers include question, answer,
document ID, actual retrieved source references, model ID, timestamps and latency. Provider exceptions are
sanitized; normal logs omit question/answer text, document contents, credentials and raw SDK responses.

## Scope and migration

This is a **single-user POC with no login or tenant isolation**. Run locally or behind an authenticated private
gateway. The `owner_id` field is scaffolding, not access control. No OCR, durable background worker, chat-memory
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
