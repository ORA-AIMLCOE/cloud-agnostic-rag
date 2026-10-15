# Running the generated OCI version

This branch adds OCI providers while keeping the RAG workflow, prompts, UI intact. Oracle persistence adapters replace the target PostgreSQL database.
No cloud infrastructure was provisioned, no production data was copied, and no live OCI test is implied.

1. Prepare OCI Object Storage, model access, and Autonomous AI Database Serverless with AI Vector Search
   (26ai, or a compatible 23ai database). The database must be reachable from the app machine.
2. Have the database administrator create a dedicated application schema, for example `RAG_APP`, with
   `CREATE SESSION`, `CREATE TABLE`, and a bounded tablespace quota (for example 1 GB on DATA for this demo).
   Use a secure administrator session to set its password. Do not run the app as ADMIN.
3. Download the converter's private configuration bundle and extract it into the project root. Keep `.env`
   and wallets out of Git. Alternatively complete `.env.oci.example`.
4. Set `OCI_DB_USER`, `OCI_DB_PASSWORD`, and `OCI_DB_DSN` using OCI's Database connection panel.
   TLS: use its TCPS descriptor or `tcps://host:1521/service`. TLS must be enabled on the database.
   mTLS: download/extract the wallet locally, set `OCI_DB_WALLET_DIR` and optional `OCI_DB_WALLET_PASSWORD`,
   and set the DSN to a TNS alias such as `database_low`. Use the `_low` service for this small app.
   The wallet directory is resolved on the machine running the converted app, not the converter.
   Native Thin mode requires no Oracle Instant Client. Keep server identity verification enabled.
   Private endpoints require your VPN/Bastion routing; public endpoints should allow only your client IP.
5. Install in a separate environment: `python -m pip install -r backend/requirements-oci.lock.txt`.
6. From the project root run `python scripts/init_oci_vectors.py`. It checks native vector capability and
   initializes metadata, history, the ingestion lock, and two vector tables. Oracle DDL commits implicitly;
   the setup is repeatable after a partial failure. Run one initializer at a time in a fresh app schema.
   Existing tables are preserved, not upgraded or repaired. Do not run the source PostgreSQL Alembic
   migrations against Oracle. Future Oracle schema changes need explicit Oracle migrations.
7. From `backend`, run `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`.
8. From `frontend`, run `npm ci` and `npm run dev`. Upload a fresh document and test grounded answers.

## Verify the database

Run `python scripts/check_oci_database.py` from the project root after initialization. It checks the
history repository and uses rolled-back vector writes to verify native binding, cosine search and mixed
embedding dimensions. Run the opt-in live tests only against a dedicated test schema (see the test file).
Offline conversion checks cannot establish live database access or validate OCI quotas.

## Models and retrieval

The converter's Astra model is independent of both runtime models. The answer model supports OCI native
GENERIC or COHERE chat, or an OCI OpenAI-compatible Responses/chat endpoint.
For Astra, select OCI native - Generic (Astra) in the converter (OCI_LLM_FORMAT=generic_astra).
This preset uses max_completion_tokens and verbosity MEDIUM, without max_tokens or temperature.
The answer token limit also budgets reasoning tokens; increase the runtime generation token limit
if the model returns an incomplete answer. Native endpoints use the
regional service root; compatible endpoints use the full API base URL, without the final action path.
Embeddings use OCI's native EmbedText API. The model must support text embeddings and retrieval input
modes. Configure actual dimensions; enable OCI_EMBEDDING_SET_DIMENSIONS only for models supporting
requested output dimensions. Unknown API formats require an adapter update, not merely a model ID.

Documents and queries use the same embedding model configuration. Its identity, endpoint, dimensions,
and chunking settings form an index identifier. Changing any creates a separate index namespace;
existing documents must be reindexed (re-upload for this version). Vectors from different models are
never mixed. Retrieval uses exact cosine distance with document and owner SQL filters. This is suitable
for this small demo; large corpora require a separately planned approximate index.

PDFs reuse native text extraction. Scanned PDFs need OCR first. Original files stay in Object Storage.
Indexing is synchronous during the first status refresh, in bounded embedding batches, then the existing
status flow verifies searchability. Large uploads can outlast an HTTP request; rechecking status retries
idempotently. There is no independent durable ingestion worker in the generated RAG app.
No identical chunking or verbatim answer parity with AWS is expected. Validate factual grounding and
citations instead. Page references are omitted when native extraction does not preserve page metadata.

History and vectors share the Oracle application schema. JSON source references use CLOB serialization
inside the persistence adapter. Existing AWS history and vectors are not migrated by this tool. AWS providers remain available and inactive with CLOUD_PROVIDER=oci.
The default Docker Compose overrides DATABASE_URL with a local database: use the documented Python
startup for the target OCI database. This converter does not modify or deploy AWS infrastructure.

## Connection and vector references

- [Oracle Python TLS/mTLS connections](https://docs.oracle.com/en-us/iaas/autonomous-database-serverless/doc/connecting-python.html)
- [Native vector binding with python-oracledb](https://python-oracledb.readthedocs.io/en/latest/user_guide/vector_data_type.html)
- [Oracle VECTOR_DISTANCE](https://docs.oracle.com/en/database/oracle/oracle-database/26/sqlrf/vector_distance.html)
