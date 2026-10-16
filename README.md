# AWS to OCI Converter (Cloudshift)

A local, single-user conversion application for the `aws_rag` project. Inspect a GitHub branch,
configure existing OCI resources, use OCI-hosted Astra to review/adapt a versioned OCI recipe,
validate the result, and publish a new branch in the same repository. The original branch is preserved.

## Repository branches

In `ORA-AIMLCOE/cloud-agnostic-rag`, `main` contains this Cloudshift converter and
`aws_rag` contains the source AWS RAG application. Select `aws_rag` as the source branch
when inspecting this repository in the converter; it is the form's default.
Generated OCI projects are published to separate `migration/oci-*` branches.

## Start locally

From the project root with `aws_to_oci_converter_env` active:

```powershell
python -m pip install -r backend/requirements.lock.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
cd frontend
npm ci
npm run build
cd ..
.\scripts\start-backend.ps1
```

Open **http://127.0.0.1:8011**. The backend serves the built UI. Repository inspection works before
Astra is configured. The conversion button stays disabled until server configuration is present.
The status indicates configuration presence, not verified model access.

For frontend development, use a second terminal in `frontend` and run `npm run dev` (port 5175).
Keep the backend on port 8011. These ports are separate from the existing AWS RAG app.
Run one backend process with one worker; do not use multiple uvicorn workers or auto-reload during jobs.

For a shared HTTPS deployment, see [Remote access](docs/remote-access.md).
The backend stays on loopback and the reverse proxy must authenticate all requests.

## Before the first conversion

1. Start your Docker-compatible Linux container engine (Docker Desktop or Rancher Desktop with dockerd).
2. Run `.\scripts\prepare-validation.ps1` once to build the trusted validation image. Initial image
   construction downloads pinned Python and Node dependencies. Generated repository code never builds
   this image; validation containers have network disabled, no host credentials, and bounded resources.
3. Add your exact OCI Astra configuration to `.env`, then restart the backend. Do not guess a model ID.
4. Provide a repository-scoped GitHub fine-grained token with Contents read/write in the UI. Repository
   branch rules and organization token policies still apply. This first local release uses tokens;
   GitHub App installation onboarding is not implemented.
5. Enter existing OCI resource/model details, Autonomous AI Database Serverless with AI Vector Search, and optionally OCI
   signing credentials. Deployment, network provisioning and source-data migration are out of scope.

OCI Astra configuration (native Python SDK, matching the supplied Astra sample):

```dotenv
ASTRA_BASE_URL=https://inference.generativeai.<region>.oci.oraclecloud.com
ASTRA_MODEL_ID=<Astra-model-ocid>
ASTRA_COMPARTMENT_ID=<compartment-ocid>
ASTRA_API_FORMAT=oci_generic
ASTRA_AUTH_MODE=oci_profile
ASTRA_OCI_CONFIG_FILE=~/.oci/config
ASTRA_OCI_PROFILE=DEFAULT
ASTRA_VERBOSITY=MEDIUM
ASTRA_MAX_OUTPUT_TOKENS=24000
```

Fill the three blank endpoint/model/compartment values in the converter's root `.env`.
Your local OCI profile must already contain tenancy, user, fingerprint, key_file and region, with its
signing key present. Use a different profile name or config path if needed. Native mode does not use
`ASTRA_API_KEY`. Restart the backend after changing `.env`.

The native client uses `GenericChatRequest`, `OnDemandServingMode`, `max_completion_tokens`,
`verbosity`, no SDK retries and a 10-second connect / 240-second read timeout. The output budget is
larger than the 2048-token sample because complete source files need more room; adjust it to the
model's supported limit. Missing, truncated or invalid patches block publication.

Optional compatible modes remain available: `ASTRA_API_FORMAT=responses` or `chat_completions`.
For these, set the base URL including the API prefix (for example `/openai/v1`) but excluding the
action path. Configure `ASTRA_AUTH_MODE=api_key` with an OCI service key, or `oci_profile` for signing,
only when supported by that endpoint. Native mode requires the service root URL without an API prefix.
Only HTTPS OCI endpoints under `.oci.oraclecloud.com` are accepted in this release.
Model access and permissions require live verification with your details. No public OpenAI API is used.
These settings select the conversion model; the generated RAG app's answer and embedding models are
configured independently in the UI.

## How conversion works

- Pin the selected branch to a source commit and download its GitHub archive.
- Reject unsafe paths, oversized archives, committed runtime secrets detected by the scanner, and
  incompatible project scaffolding. Secret detection is best-effort, not a complete security audit.
- Build a minimal patch from `migration_recipes/aws_rag_v1`. Astra receives interfaces, sanitized
  capabilities and OCI adapter code, then can refine only five exact adapter files. It cannot rewrite
  the UI, workflow, prompts, APIs, history schema, GitHub publishing logic or tests.
- Test inside the prebuilt isolated Docker container: original backend tests, new OCI tests, frontend
  TypeScript/build/tests. Docker failure or failed tests blocks branch publication.
- Create blobs, a tree and a commit based on the pinned source; create a unique new branch ref. No force
  push or merge. Source changes made after inspection do not change the conversion baseline.
- Ask OCI Astra to summarize the final diff for every changed file; display these development summaries alongside the code comparison.
- Show the real diff and measured file counts. Download code separately from Private ENV Configuration.

The source's `push`/`create` GitHub Actions triggers are checked before publication. Unknown or broad
triggers block automatic publishing; download-only conversion remains available. Branch-triggered
external webhooks cannot be discovered by this limited-permission tool; review repository automation
before using it with an automatically deployed repository.

The recipe implements Object Storage, OCI chat, OCI native EmbedText, and document-filtered Oracle AI Vector Search. LLM and embedding configurations are independent. Different chunking and answer
wording from AWS are expected. Changing embedding identity/dimensions/chunking requires fresh indexing.
Source history files stay intact. OCI-specific persistence adapters and an explicit setup script create Oracle metadata, history and vector tables.
The generated project's `docs/oci-generated.md` explains exact runtime steps and limits.

## Local state and credentials

- `.state/jobs.sqlite3`: job metadata, timeline, diffs and encrypted per-job credentials.
- `.state/vault.key`: local encryption key. Keep this directory private; encryption does not protect
  against someone who can read both this key and the database.
- `.workspaces/<job-id>/source`: pinned repository snapshot.
- `.workspaces/<job-id>/output`: generated OCI source, never live credentials.
- `.workspaces/<job-id>/validation.log`: isolated test output.

AWS `.env` uploads are parsed as data. Only allowlisted resource settings are retained; AWS credentials
and source DATABASE_URL are discarded. Actual target IDs, endpoints and credentials are not sent to
Astra. Target credentials are encrypted in SQLite, and appear only in the private configuration download.
The private ZIP contains `.env` and, if supplied, `config/oci/config` plus its PEM key. Do not commit it.

Jobs and downloaded configurations are accessible only through this loopback UI. No user login, remote
hosting or multi-tenant isolation is provided. Bind to 127.0.0.1 only. Browser cross-origin requests are
blocked. Do not expose this service through a tunnel or public reverse proxy.

Job data and workspaces expire after 24 hours by default while the worker is running; cleanup resumes
on startup. Interrupted running jobs fail visibly and are not automatically replayed. Queued jobs are
persistent. If interruption occurred around publication, check the recorded commit/branch on GitHub
before retrying. Cancellation is cooperative between operations; a GitHub ref request already sent
cannot be undone. Nothing automatically deletes a published branch.

## Tests

```powershell
cd backend
python -m pytest -q
python -m ruff check app
cd ../frontend
npm test
npm run build
```

Converter tests use fake GitHub/model clients. They do not push a branch or invoke a paid model.
A developer-only trusted-local smoke test is available:
`python scripts/verify-local-recipe.py ../aws_rag` (requires the trusted RAG dependencies listed in
`scripts/validation/backend.lock.txt`). Remote/model-generated code must use Docker validation instead.

## Delivery status

See `docs/validation.md` for actual checks and remaining live verification. A generated branch is not
called deployed or live-verified. Astra access, real GitHub publishing and OCI RAG acceptance must be
checked after the endpoint and credentials are supplied.

## Autonomous Database target

The OCI target now uses Autonomous AI Database Serverless for both metadata/history and native vector
search. Enter the database DSN, application username and password in step 05; wallet directory and
password are optional for mTLS. These credentials remain in the encrypted job payload and private
configuration download. The converter does not create the database or upload wallet files.

Rebuild the isolated validator after this update: `./scripts/prepare-validation.ps1` (Docker-compatible
engine required). The new image is `aws-oci-validator:oracle-v1` and includes python-oracledb 26.0.1.
The AWS checkout and core workflow are unchanged. See the generated `docs/oci-generated.md` for
initialization and the rollback-only database check command. Existing AWS data is not migrated.
