# Architecture and boundaries

React UI -> local FastAPI API -> SQLite durable queue -> single worker -> versioned recipe + OCI Astra
-> isolated Docker validation -> GitHub Git Data API -> new branch + review artifacts.

The converter has its own virtual environment and repository. `aws_rag` remains the source project;
its working directory is not edited by conversion jobs. New adapters are created only in job snapshots.

## Model roles

- Converter: server-configured Astra through OCI native Generic Chat (default), or optional OCI Responses/Chat Completions.
- Generated RAG LLM: user-configured model using OCI native Generic/Cohere or compatible APIs.
- Generated RAG embeddings: user-configured OCI native EmbedText model. Vector dimensions are verified
  against every returned embedding. Requested output dimensions are optional and model-dependent.

The Oracle AI Vector Search implementation uses exact cosine search, filtered by document, owner and index identity.
The Oracle adapter uses variable-dimension VECTOR columns, Oracle-specific metadata models and CLOB JSON serialization.
The source PostgreSQL models and migrations remain protected; Oracle setup is separate.
Scaling to ANN indexes is a separate change. Core source paths are protected by the patch allowlist.

## Job lifecycle

queued_inspection -> running -> ready -> queued -> running -> completed / failed / cancelled.
Any retained job can eventually expire. There is no automatic cloud resource creation or data migration.
The source SHA is immutable for a job. A failed check never yields a success badge or a published branch.
An interrupted publication can have an uncertain outcome; the commit is stored before branch creation.
GitHub publication uses a unique branch and never updates an existing ref.

Recipe generation is deterministic. Astra reviews and minimally adapts the OCI adapter implementation;
it is not allowed to redesign the application or claim tests passed. Independent validator exit codes
control publication. Source files and model output are untrusted: no generated code executes on the
converter host. Tests execute in a container without network, secrets, Docker socket or writable host mount.

## Supported scope

This is a project-specific converter, not a general arbitrary AWS migration service. Source scaffolding
must match the versioned recipe. Provider semantics may differ; acceptance requires source-grounded
answers, valid citations, readiness behavior and document isolation, not identical AWS/OCI text.
