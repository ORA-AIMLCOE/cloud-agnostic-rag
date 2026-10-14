# OCI migration playbook

OCI is **not implemented or tested**. Scaffolds fail explicitly. Setting `CLOUD_PROVIDER=oci` currently stops
startup instead of producing simulated answers. No OCI SDK or credentials are needed for the AWS application.

## Files that change

| File / path | Migration responsibility |
|---|---|
| `backend/app/providers/oci/llm.py` | Implement OCI inference, system/user/context mapping, model config, usage and errors |
| `backend/app/providers/oci/storage.py` | Implement private object upload/read/delete/list; preserve generated keys |
| `backend/app/providers/oci/vector_search.py` | Implement real document/owner filtering and normalized chunks |
| `backend/app/providers/oci/ingestion.py` | Implement metadata, idempotent indexing jobs, status and configuration validation |
| `backend/app/providers/factory.py` | Construct OCI adapters in the existing OCI branch |
| `backend/app/core/config.py` | Add the chosen OCI service/authentication configuration |
| `backend/app/core/dependencies.py` | Replace AWS-named storage-prefix wiring with selected provider configuration if needed |
| `backend/requirements.txt`, `backend/requirements.lock.txt` | Add and lock the OCI SDK and any selected vector client |
| `.env`, `.env.example` | Switch endpoints, model/index identifiers, credentials chain and database URL |
| `infrastructure/oci/`, deployment manifests | Provision OCI networking, compute, object storage, vector index, PostgreSQL and logs |
| `backend/tests/` | Add real OCI adapter tests and register adapters in the common contract suite |

The AWS adapter files can remain unused or be removed in the copied project. No changes should be needed in
`frontend/`, `api/`, `domain/`, `interfaces/`, `services/`, `workflows/`, `database/`, `repositories/`, or Alembic
schema revisions. Do not rewrite the graph to call a provider-specific managed RAG endpoint.

## Service selection and environment

Select OCI Generative AI for inference and Object Storage for files. Evaluate OCI Generative AI Vector Stores,
Agents Knowledge Bases, or an OCI-compatible vector database against the retrieval port before choosing one.
The selected service must return text, stable chunk identifiers, document metadata, and support strict filtering.
If it cannot enforce document filters, fail closed; do not substitute unrestricted retrieval followed by guesswork.

Illustrative settings (final names depend on the chosen services):

```dotenv
CLOUD_PROVIDER=oci
OCI_REGION=<region>
OCI_COMPARTMENT_ID=<compartment-ocid>
OCI_MODEL_ID=<model-id>
OCI_OBJECT_STORAGE_BUCKET=<bucket>
OCI_VECTOR_STORE_ID=<index-or-knowledge-base-id>
DATABASE_URL=postgresql+psycopg://<app-user>:<url-encoded-password>@<private-db>:5432/aws_rag?sslmode=verify-full
```

Use instance/resource principals in deployed OCI infrastructure or a supported local profile. Limit IAM policy
scope to the application compartment/bucket, selected model and vector service. Put PostgreSQL and compute in
private subnets, allow database ingress only from compute security groups, and establish private service access
or controlled egress. Never put private API keys in frontend assets or images.

## Data cutover

1. Freeze uploads and questions for a maintenance window, back up the database, and inventory objects by
   `documents.storage_key`. Record row counts and file checksums; keep the AWS copy for rollback.
2. Copy document bytes to OCI Object Storage with the **same relative keys**, preserving the `documents.id`
   values and original filenames. The database stores provider-neutral keys, so bucket URI rewriting is unnecessary.
   Use SDK streaming or an approved transfer tool; compare byte counts/checksums after copying.
3. Generate OCI-native metadata from database IDs/owners. AWS `.metadata.json` files are AWS adapter artifacts;
   translate them to the target ingestion format, not just their filenames.
4. Build a fresh vector index using the selected OCI embedding model and correct dimensionality/distance metric.
   Do not blindly copy vectors between different embedding models. Set text chunking and metadata filter indexes.
5. Migrate history/metadata with PostgreSQL `pg_dump --format=custom` and `pg_restore` using compatible client/server
   versions. Restore roles/ownership deliberately, apply `alembic upgrade head`, and compare row counts/foreign keys.
   For large databases choose an approved replication migration instead of assuming dump/restore downtime is acceptable.
6. Reset migrated document ingestion job IDs (AWS job IDs have no meaning in OCI), statuses to Uploaded,
   status messages to a migration notice, and `created_at`/timeout handling for reindexing. To preserve original
   creation dates, perform reindexing with a temporarily increased `INGESTION_TIMEOUT_SECONDS` rather than changing
   business logic. Keep timestamps unchanged, validate every document through the normal status service, then restore
   the normal timeout. Historical answers keep their original model identifiers and source excerpts for audit.
7. Switch the database URL and provider configuration, run the same unit/API/UI tests, then opt in to OCI-specific
   storage, ingestion, filtered retrieval, inference and persistence integration tests. Test two documents with
   different answers to prove document filtering is applied.
8. Verify log correlation in OCI Logging, model grounding and citations, indexing failures/timeouts, retries,
   upload limits, Q&A history and database TLS. Cut traffic over only after these pass.
9. Keep the source AWS deployment read-only for an agreed rollback period; export new OCI writes before any rollback.

Replace the ECS `awslogs` driver with an OCI-supported stdout collector. Keep the JSON formatter and logging
calls unchanged. Configure retention, least privilege and metrics/alarms in OCI deployment configuration.

The common behavior contract in `tests/test_contracts.py` provides model/signature checks and a minimal port exercise.
For real OCI tests, use unique object keys, wait for asynchronous indexing, and run the full `test_aws_end_to_end`
scenario adapted only in infrastructure setup and provider selection; never label the current fake-provider test
as an OCI integration pass.
