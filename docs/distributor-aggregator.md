# Distributor Aggregator

The app answers self-contained questions about BlueDart, Delhivery, Ekart and DTDC from one administrator-prepared document. Users do not upload or choose documents. Answers cite retrieved passages. Missing information must remain missing; the model must not invent real prices, policies or tracking status.

The initial document, [Distributor_Knowledge_Base_DEMO.md](Distributor_Knowledge_Base_DEMO.md), contains explicitly fictional data. The API retains the `demo_data` metadata; the UI and answer text omit demo labels. Replace it with approved information before using the answers for business decisions.

## Existing AWS services

The local app continues to use the existing Sydney resources: S3 document storage, Bedrock managed Knowledge Base `YNZKTQSGBJ` and data source `TSRBHBQ9IN`, Titan Text Embeddings V2 (1024 dimensions), Nova Lite for answers, and PostgreSQL on RDS for document metadata and question history. The Knowledge Base uses 300-token chunks with 20% overlap. Retrieval always filters to the active document. Comparisons retrieve evidence for each named distributor before combining the context.

No new AWS infrastructure is required. The migration adds release-tracking tables to the existing database. Old documents and history remain stored but are excluded from the new distributor UI and retrieval. Local logs go to stdout; this change does not deploy CloudWatch shipping.

## Run locally on this laptop

Keep three terminals open. Run from the `aws_rag` directory. The existing private `.env` must remain in place; do not overwrite it with a template.

Terminal 1: start the existing private RDS tunnel:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start-db-tunnel.ps1
```

Terminal 2: activate the existing Python environment and start the backend:

```powershell
& 'C:\Users\adarshmi\Desktop\EXPLORE\0_virtual_environment\aws_rag_env\Scripts\Activate.ps1'
cd backend
python -m alembic upgrade head
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

Terminal 3:

```powershell
cd frontend
npm run dev -- --port 5173 --strictPort
```

Open http://127.0.0.1:5173/ . API documentation is at http://127.0.0.1:8000/docs . Stop each local process with Ctrl+C; stopping the tunnel does not stop or delete AWS resources.

If the AWS session expires, renew the existing profile with `aws login --profile aws-rag-provision --region ap-southeast-2`. Complete browser sign-in to account `649901308226`. The app uses its existing assumed app role; a renewable login is not permanent unattended authentication. See the existing AWS setup guide for configuration.

## Prepare or replace the document

Run one ingestion command at a time, from `backend`, while the database tunnel and AWS credentials are available:

```powershell
python -m app.admin ingest ../docs/Distributor_Knowledge_Base_DEMO.md --version demo-2026-10-19-v2 --demo --timeout 900
python -m app.admin status
```

The command uploads to S3, starts or queues the existing Knowledge Base sync, waits for indexing, checks that all four distributor topics are retrievable, and activates the release. It leaves the previous active release unchanged if verification fails. Repeating the same content reuses its release and does not upload a duplicate. If a timeout occurs, rerun the same command to resume.

Use a new version and omit `--demo` only for approved, non-fictional information. Include all four distributors and keep each paragraph self-contained with its distributor name, units, conditions, and date. A shared content hash cannot be relabelled from fictional to approved. Ingest updated content as a new release instead.

To roll back to an already indexed release:

```powershell
python -m app.admin activate DOCUMENT_ID
```

Activation is global for the shared workspace. Each question pins its document version when it starts. History shown in the UI belongs to the currently active document; it is shared, not private per user.

## Integration endpoint

Your other project's **backend** calls:

```http
POST http://127.0.0.1:8000/api/v1/answers
Authorization: Bearer YOUR_INTEGRATION_API_KEY
Content-Type: application/json

{"question":"Compare BlueDart and Delhivery COD limits and settlement times."}
```

This localhost address works only from this laptop. The remote HTTPS URL will be configured in the later VM deployment.

The local test key is stored in `.validation/distributor-api-key.txt`, and configured through the ignored `.env` file. It is not part of the frontend bundle or Git. From the project directory:

```powershell
$distributorKey = (Get-Content .validation/distributor-api-key.txt -Raw).Trim()
$answerRequest = @{ question = 'Compare BlueDart and Delhivery COD limits and settlement times.' } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/answers -Headers @{ Authorization = "Bearer $distributorKey" } -ContentType application/json -Body $answerRequest
```

The response includes:

| Field | Meaning |
| --- | --- |
| `answer` | Answer text with citation markers; without an automatic demo-disclaimer prefix. |
| `sources` | Cited document names, excerpts, reference IDs, and available page/score metadata. |
| `knowledge_version` | Document release used for this answer. |
| `demo_data` | Whether the release contains fictional data. |
| `answer_status` | `answered` when cited evidence is returned; otherwise `insufficient_information`. A cited answer can explain that a requested attribute is not documented. |
| `request_id` | Correlation ID for troubleshooting, also returned in `X-Request-ID`. |
| `id`, `document_id`, `question`, `model_id`, `latency_ms`, `created_at` | Saved answer and execution metadata. |

Only `question` is accepted (1–4000 characters after trimming). Each request is independent; include distributor names and relevant context instead of relying on chat memory. Callers do not need AWS credentials. They must keep the integration key on their server, outside browser code and repositories.

Errors: `401` missing/invalid key; `422` invalid request; `429` rate/concurrency limit (`Retry-After: 60`); `503` no ready document or unavailable provider. Allow up to 240 seconds client timeout for slower comparisons. Do not blindly retry a timed-out POST: an answer may already have been saved, and idempotency keys are not implemented. Responses use `Cache-Control: no-store`.

Private `.env` configuration:

```dotenv
DISTRIBUTOR_MODE=true
INTEGRATION_API_KEYS={"client-project":"REPLACE_WITH_A_RANDOM_SECRET"}
INTEGRATION_REQUESTS_PER_MINUTE=30
INTEGRATION_MAX_CONCURRENT=2
```

Restart the backend after changing keys. Give each integration its own entry. Rotate by adding a new entry, updating the caller, then removing the old one. Limits apply to the integration route per process; run one worker or use a shared rate-limit gateway when scaling. Local browser routes use the existing local/shared-workspace access model, so keep the local server bound to loopback.

## Later VM deployment

1. Deploy this tested `aws_rag` version separately from Cloudshift; preserve the colleague's app and existing paths.
2. Apply the additive database migration and private environment configuration, then run a persistent service with working AWS credentials.
3. Serve the UI at the existing `/aws-rag/` prefix under HTTPS and the existing browser login.
4. Expose only the exact integration endpoint under HTTPS with application Bearer authentication. Configure that proxy location to pass the Authorization header and avoid a conflicting browser Basic-auth challenge. Keep all other UI/history routes behind the browser login.
5. Test authentication, source citations, timeouts and key rotation from the consuming project's backend, then provide that project the final URL and its own key through a private channel.

No VM deployment or OCI conversion is included in this local implementation.

## Five demo questions

1. What services, coverage and delivery timelines does BlueDart offer?
2. Compare BlueDart and Delhivery COD limits, fees and settlement times.
3. Which distributors offer reverse pickup, and what are their request windows?
4. What conditions apply to Ekart Metro Next Day delivery?
5. What information does the document provide about DTDC COD support?
