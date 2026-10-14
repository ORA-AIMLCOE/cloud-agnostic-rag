# Tests and validation

Activate your existing virtual environment, then from `backend` run:

```powershell
python -m pip install -r requirements.lock.txt
python -m pytest -q
python -m ruff check app tests alembic
python -m ruff format --check app tests alembic
```

Unit tests use a fresh SQLite database, in-memory provider fakes, FastAPI TestClient, and botocore Stubber.
They need no AWS credentials and create no cloud resources. Ordinary pytest skips all `integration` markers.
The mocked end-to-end scenario uploads a document, checks the indexing gate, verifies searchability, runs the
real LangGraph, saves Q&A, and reads history. SDK Stubber validates request/response schemas for S3, Retrieve,
Converse, ingestion starts, and per-document indexing status. Architecture checks reject SDK/provider imports
in application layers. SQLite validation is not a substitute for live PostgreSQL concurrency/TLS validation.

From `frontend`:

```powershell
npm ci
npm run build
npm test
npm audit
```

UI tests exercise upload/selection, asking, citations, history, disabled processing state and readable API errors
with a mocked API. They do not prove that a browser can call real AWS services.

## Explicit integration opt-in

Prepare a running backend and AWS resources from `aws-setup.md`, then:

```powershell
$env:INTEGRATION_BASE_URL = 'http://localhost:8000'
# Use a dedicated, migrated test database for the PostgreSQL transaction test.
$env:INTEGRATION_DATABASE_URL = '<postgresql+psycopg URL>'
# For the CloudWatch test, point BASE_URL at the deployed log-shipped application.
$env:INTEGRATION_LOG_GROUP = '<deployed-log-group>'
python -m pytest --run-integration -m integration -v
```

`test_aws_end_to_end` creates a uniquely named TXT fixture, checks stored bytes in S3, waits up to 15 minutes
for confirmed searchability, calls the real Bedrock model, and verifies database-backed history. It leaves
the fixture and history for inspection. Use a dedicated POC data source; these operations incur storage,
embedding, retrieval and inference costs. The database test inserts and reads records in a transaction then
rolls it back. The CloudWatch test calls health and searches for its correlation ID to verify actual shipping;
the test runner needs `logs:FilterLogEvents` on that log group.

No cloud integration run is triggered by installing dependencies, running ordinary tests, or building the UI.
If live resources are unavailable, report these tests as skipped, not passed.

## Manual acceptance

1. Start PostgreSQL, apply migrations, start backend, check readiness, then open the frontend.
2. Upload one PDF with selectable text, one UTF-8 TXT, and one Markdown document.
3. Confirm Uploaded/Processing → Ready and that Ask stays disabled before Ready.
4. Ask known facts and unsupported questions; expand citations and compare excerpts.
5. Switch documents and verify questions use only the selected document; reload and inspect History.
6. Upload two files rapidly to test queuing; stop a sync to test Failed. Test a scanned PDF separately.
7. In AWS, verify RDS rows and the same request ID in CloudWatch without document/question content.
8. Confirm unsupported file types, oversize uploads, empty questions and invalid IDs return consistent errors.

Cleanup: remove integration objects and matching metadata sidecars from the dedicated S3 prefix, sync the
data source to remove indexed content, and delete fixture Q&A rows before document rows from the isolated
test database. Do not automate broad deletion against a shared bucket/database.
