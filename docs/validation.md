# Validation - 14 October 2026

## Completed offline checks

- Converter backend: **47 tests passed** (credential handling, request boundaries, safe archives,
  durable queue, cancellation, source SHA preservation, failed-test publication blocking, OCI model
  routing and GitHub branch creation with fake clients).
- Native OCI Astra tests use installed OCI SDK request/response models with a mocked client.
  They verify profile authentication, Generic Chat fields, token usage, missing configuration,
  endpoint prefix rejection, sanitized errors, and blocking truncated/invalid patches.
- Converter frontend: **3 tests passed**; TypeScript and production build passed.
- Backend Ruff checks passed.
- Headless Edge: real local UI and status endpoint verified; mocked repository inspection, independent
  LLM/embedding form inputs, conversion progress, results, diff and mobile navigation passed with no
  page errors or horizontal page overflow. Desktop/mobile screenshots are in ignored `.validation/`.
- Trusted local recipe smoke test against AWS commit `02f02974b0938249c5330cdb936174ab482f6460`:
  **59 tests passed, 3 live integration tests skipped** in the generated RAG backend.
- Recipe diff: **9 existing files modified, 10 added, 0 protected core files changed**.
  Existing modifications include four OCI placeholders, provider factory, configuration/wiring,
  the obsolete OCI-not-implemented test assertion and .gitignore. New files include embedding/auth
  helpers, additional vector-schema setup, tests, dependencies and documentation.
- The source `aws_rag` working tree remained unchanged.

## Not yet verified

- Full Astra conversion with repository code and isolated validation (the bounded connectivity check passed).
- Real GitHub publishing and branch-rule enforcement (read-only inspection now passed).
- OCI storage, native embedding, answer-model access, database connectivity and live RAG grounding.
- Docker validation image build/container execution: Docker CLI is installed, but the container engine
  is stopped/unavailable. The converter blocks publication if isolated validation cannot run.

The trusted-local smoke test executes only our deterministic recipe against the user's known local
source. It is not a substitute for Docker isolation for remotely downloaded or model-generated code.
The offline checks above did not invoke cloud models. The later bounded live Astra check is recorded below.
No branch was pushed and no infrastructure was deployed.

## Live Astra connectivity check - 14 October 2026

- Native OCI Generic Chat succeeded using the configured local OCI profile and supplied model OCID.
- The production Astra client parsed a valid JSON patch with an empty files list.
- One small request used 255 prompt tokens and 91 completion tokens (346 total), taking 8.4 seconds.
- The request contained only a connectivity instruction, no repository code or target credentials.
- This verifies access and response parsing, not end-to-end conversion or generated RAG behavior.
- Resource values were moved from .env.example into ignored .env; the example fields are blank.

## Acceptance after credentials arrive

1. Verify Astra API format with a bounded request, then inspect the intended GitHub branch.
2. Start Docker and build the validation image with `scripts/prepare-validation.ps1`.
3. Run a complete conversion and verify the diff and new branch parent commit.
4. Run the generated app against existing OCI test resources. Upload a known PDF/TXT/MD fixture.
5. Confirm an answerable question produces a supported answer and valid source citation; an unrelated
   question abstains; two documents with different facts do not leak into one another's answers.
6. Change embedding model/configuration using a new index/re-upload, and verify dimension checking.
   Different chunk boundaries and wording from AWS are acceptable.

## GitHub inspection diagnosis - 14 October 2026

Three user attempts failed before conversion: connection timeout, HTTP 404, then HTTP 403.
Read-only checks with the latest submitted token succeeded for identity and repository metadata,
but the source commit endpoint returned Resource not accessible by personal access token with
a required Contents read permission. Token Contents access/organization approval needs correction.
Added tested guidance for permission, authentication, SSO, rate-limit, 404 and connection failures.
No repository changes or model calls were made during this diagnosis.

## GitHub inspection verified - 14 October 2026

After the token permissions changed, main could be read. Full inspection then exposed a scanner
false positive: Terraform manage_master_user_password = true was treated as a password.
The scanner now exempts that exact boolean setting; regression tests retain credential detection.
A fresh real inspection passed project structure, source credential scan and branch workflow checks
for 101 files, including 39 protected core files. Job status is ready for OCI target settings.
This verifies read access and source compatibility, not GitHub write permission or conversion.
No branch was published and no Astra call was made during inspection.

## Astra answer-model preset - 14 October 2026

Added generic_astra to the UI, target schema and generated OCI settings. It uses native Generic Chat
with max_completion_tokens and verbosity MEDIUM, omitting max_tokens and temperature.
Mocked generated-adapter tests verify grounded prompt preservation, the SDK request contract,
ordinary Generic compatibility and incomplete-response rejection. Converter: 47 tests passed;
generated backend: 59 passed, 3 live tests skipped; frontend: 3 passed and build passed.
The answer-model preset has not yet been tested live with retrieved documents.

## Autonomous Database target - 14 October 2026

Replaced the OCI target's PostgreSQL/pgvector configuration with Autonomous AI Database Serverless.
Added native VECTOR bindings, exact cosine retrieval with document/owner/model isolation, Oracle
persistence adapters, TLS/mTLS settings, explicit schema initialization and a rollback-only live check.
The converter form and encrypted private configuration export use OCI_DB_* settings.

Validation completed:
- Converter backend: 56 tests passed; converter frontend: 3 tests passed and production build passed.
- Generated app in the restricted Docker validator: 70 backend tests passed; 4 live tests skipped.
- Generated frontend: 3 tests passed, TypeScript and Vite production build passed.
- Generated diff: 25 added/modified files, no protected core source file changes; secret scan passed.
- Oracle validator image aws-oci-validator:oracle-v1 built successfully (python-oracledb 26.0.1).
- Local service serves the new database DSN/user/password and optional wallet fields.

No Autonomous Database was provisioned or connected during this code change. Native Oracle SQL, TLS
and end-to-end RAG still require live verification with the target database and models. The offline
repository test uses SQLite only to exercise serialization/contracts; it is not Oracle SQL evidence.
The recipe was generated from the trusted local AWS checkout; no Astra call or GitHub publication was
performed during this change. Live checks are available through scripts/check_oci_database.py and the
opt-in OCI_RUN_DB_TESTS=1 generated test after the target application schema is initialized.


## Distributor Aggregator compatibility - 19 October 2026

Validated against aws_rag commit 7e06be006e06e9466fc1630556e77a8a9ddcde2e.

- Converter backend: 103 tests passed, including source feature detection, incomplete-contract rejection,
  per-conversion integration key generation, encrypted persistence, masked preview and private download.
- Converter frontend: 14 tests passed; TypeScript and production build passed.
- Deterministic generated application: 80 backend tests passed, four optional live tests skipped.
  Added Oracle repository release activation/rollback and pre-ingestion/API/isolation contract checks.
- The real Docker sandbox (aws-oci-validator:oracle-v1) passed the generated backend suite, TypeScript,
  frontend build and all six source UI tests, with network disabled and no runtime credentials mounted.
- 26 generated file changes; zero protected source changes. The latest distributor UI cleanup, admin
  ingestion workflow, comparison retrieval and authenticated integration API remain unchanged.
- Target credentials and the generated integration key are excluded from model context, source templates
  and Git output. Source integration keys are discarded during environment import.
- Updated generated runtime instructions for Oracle initialization, CLI pre-ingestion and API clients.

These checks establish offline compatibility, not current live model permissions or OCI resource access.
No converter commit was pushed, no OCI branch was published and no VM deployment was performed for this update.
The OCI SDK successfully loaded the laptop's DEFAULT profile and found its signing key. A small live
request to the configured Chicago conversion model passed authentication and JSON response parsing.
The profile's region is Hyderabad; the converter explicitly uses its separately configured Chicago endpoint.

With explicit user approval, the configured Chicago model reviewed only source provider interfaces
and generated OCI adapter files. It returned no changes. The reviewed adapters matched the
Docker-tested output, and live development summaries validated for all 13 OCI adapter files.
This did not exercise a GitHub-backed UI job or connect the generated app to live target resources.

## Local conversion summary fix - 19 October 2026

A generated offline test used a literal dummy integration key in a Python keyword argument.
The credential scanner treated that line as a malformed dotenv assignment and correctly stopped
before sending the diff, after the application tests had passed. The fixture now generates an
ephemeral key at runtime. Credential scanning was not relaxed. Regression tests cover the actual
generated fixture's summary request and continued blocking of real integration-key assignments.

Converter backend: 105 tests passed. A replacement UI/API job using the failed job's saved target
and publish setting passed Docker validation (80 backend tests, four live tests skipped; six UI
tests and frontend build passed). GPT summaries completed for all 26 changed files. Job
6a1e1a9e1b434f6788dc39d048528ecf published migration/oci-6a1e1a9e1b43 at
8450d855965cbd20a05fc336e88cee61931365c5; the remote branch reference was independently verified.
No VM deployment or live target-resource verification was performed. The earlier failed job is
retained as history; the replacement job contains the validated output and private configuration.
