# AWS setup and deployment

## Supported configuration

This implementation supports **Managed Knowledge Bases with an S3 managed connector** (`AWS_KB_MODE=managed`)
and **conventional VECTOR Knowledge Bases with an S3 data source** (`AWS_KB_MODE=conventional`).
Both use separate Retrieve and Converse calls and document metadata equality filters. Bootstrap validates
the selected type, source bucket, and prefix coverage. Managed retrieval uses `managedSearchConfiguration`
with reranking disabled, supporting the current custom Titan embedding configuration.
For managed PDF uploads, the app preserves the original PDF and extracts its native text into
`<original-key>.extracted.txt`. That text object carries the document's retrieval metadata; the original PDF
is assigned a separate metadata identity so visual captions cannot contaminate answers. Readiness checks
the extracted text object's indexing status. Image-only, encrypted, or partly non-searchable PDFs fail
with instructions to supply OCR/searchable text. Existing ready PDFs must be re-indexed to use this path.
KENDRA and SQL types remain unsupported. See [your configured Sydney resources](your-aws-setup.md),
the current [GetKnowledgeBase schema](https://docs.aws.amazon.com/boto3/latest/reference/services/bedrock-agent/client/get_knowledge_base.html)
and [Retrieve schema](https://docs.aws.amazon.com/boto3/latest/reference/services/bedrock-agent-runtime/client/retrieve.html).

Choose a region that supports the selected model, Knowledge Bases, and vector backend. Choose a model or
inference profile supporting Converse, system messages, and the configured inference settings. Complete any
model-provider access requirements in your AWS account. No particular region or model is built into the app.

## Foundation infrastructure

`infrastructure/aws` provisions a private, encrypted RDS PostgreSQL instance with a Secrets Manager-managed
admin password; two private subnets; application/database security groups; an encrypted, versioned private S3
bucket; a CloudWatch log group; and ECS task/execution roles. It does **not** create compute, a load balancer,
NAT/endpoints, ECR repositories, the Bedrock Knowledge Base, or its vector store. These are explicit setup steps
below. This scope avoids pretending that account-specific Bedrock/vector permissions are provisioned.

Install Terraform 1.6+ and configure AWS CLI/profile credentials. Never commit `terraform.tfvars`, credentials,
or state. Use a protected encrypted remote state backend for shared deployments.

```powershell
cd infrastructure/aws
Copy-Item terraform.tfvars.example terraform.tfvars
# Set region, globally unique bucket name, and an available PostgreSQL 16 minor version.
# For the first apply, set knowledge_base_arn = null and inference_resource_arns = [].
terraform init
terraform fmt -check
terraform validate
terraform plan -out=foundation.plan
terraform apply foundation.plan
terraform output
```

Inspect the plan before applying: RDS and other persistent infrastructure incur costs. If you already have
equivalent resources, configure `.env` to use them; do not create duplicates. RDS passwords are managed by
Secrets Manager, not a Terraform input. The default `db.t4g.micro` is a POC sizing choice, not a production recommendation.

## Create an alternative conventional vector Knowledge Base

Your configured account already has a working Managed Knowledge Base. Skip this alternative setup for it.

Use the Bedrock console in the configured region:

1. Create a Knowledge Base with a **vector store** and Amazon S3 data source. Avoid the managed KB option.
   Set the S3 URI to the Terraform bucket and inclusion prefix to exactly `documents/` (or your configured prefix).
2. Create or select a dedicated Bedrock service role. Allow `s3:ListBucket` on the bucket, `s3:GetObject` on the
   document prefix, and `bedrock:InvokeModel` on your chosen embedding model. This is separate from the application role.
3. Select a supported **text embedding model**. Its output dimensions must match the vector index. Choose
   default parsing with a sensible fixed-size chunking configuration, such as 300 tokens and 20% overlap.
   Text-only PDFs are the initial target; configure a supported parser separately for OCR needs.
4. Use the console's quick-create **Amazon OpenSearch Serverless vector collection/index** path if available.
   Ensure the collection is VECTORSEARCH and the index uses **FAISS**. If supplying an existing index, create a
   `knn_vector` field with the embedding dimension and FAISS engine, a text field, and the Bedrock metadata field;
   map these exact names in the Knowledge Base configuration. Follow AWS's [vector-store prerequisites](https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base-setup.html).
5. Verify the collection's encryption, data-access and network policies. Grant the Bedrock service role
   `aoss:APIAccessAll` on the collection ARN and data access for describing indexes and reading/writing documents.
   The vector collection network policy must permit the Bedrock service (`bedrock.amazonaws.com`); private
   administration additionally needs an OpenSearch Serverless VPC endpoint and its network-policy entry.
   Use least-privilege index/collection resources and inspect any broad console-generated policy before use.
6. Save the Knowledge Base ID, ARN, S3 data-source ID, collection ID/ARN and vector index name. Wait for ACTIVE
   Knowledge Base and AVAILABLE data source. Put IDs into `.env`; put the KB ARN and inference resource ARNs
   into `terraform.tfvars`. Apply a second plan to attach the scoped application IAM policy.

S3 metadata sidecars are written automatically as `<key>.metadata.json`, using `metadataAttributes` for
`document_id` and `owner_id`. Do not exclude sidecars from the data-source prefix. The index must preserve
these fields for equality filtering. See [S3 data-source metadata and synchronization](https://docs.aws.amazon.com/bedrock/latest/userguide/s3-data-source-connector.html).
Use a dedicated bucket prefix/data source: the service synchronizes the whole source, not just the newest file.
Do not put untrusted external writers on the same prefix.

After sync COMPLETE, the app checks [GetKnowledgeBaseDocuments](https://docs.aws.amazon.com/boto3/latest/reference/services/bedrock-agent/client/get_knowledge_base_documents.html)
for INDEXED and probes filtered retrieval. Partial/ignored indexing fails. A zero-result probe remains Processing
until the timeout rather than offering Q&A prematurely.

## Required permissions

The Terraform task policy specifies:

| Principal | Operations | Scope |
|---|---|---|
| Application task | S3 ListBucket, GetObject, PutObject, DeleteObject | One bucket/prefix, including sidecars |
| Application task | Bedrock Retrieve, GetKnowledgeBase, GetDataSource, StartIngestionJob, GetIngestionJob, ListIngestionJobs, GetKnowledgeBaseDocuments | Configured KB ARN |
| Application task | Bedrock InvokeModel (used by Converse) | Configured model/profile and any required backing model ARNs |
| Bedrock service role | Read S3, invoke embedding model, access vector index | Dedicated ingestion/index resources |
| ECS execution role | Pull ECR images and write log streams/events | Standard execution policy plus deployment restrictions |
| ECS execution role | Secrets Manager GetSecretValue, and KMS Decrypt if customer key used | Exact DATABASE_URL secret/key |
| Integration test runner | CloudWatch FilterLogEvents | Exact application log group |

Cross-region inference profiles may require permissions for model ARNs in each destination region; verify the
selected profile's requirements. Resource policies, SCPs and quotas can still deny calls despite these IAM actions.
SSE-S3 encryption is used for document objects; if your bucket requires SSE-KMS, extend the storage/ingestion
adapter configuration and KMS grants consistently before deploying.

## Local AWS run

```powershell
aws sso login --profile <your-profile>
$env:AWS_PROFILE = '<your-profile>'
Copy-Item .env.example .env
# Fill AWS identifiers and your DATABASE_URL.
docker compose up -d postgres
cd backend
python -m alembic upgrade head
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --no-access-log
```

In another terminal, `cd frontend; npm ci; npm run dev`. Open http://localhost:5173 and
http://localhost:8000/api/readiness. The selected profile uses the normal boto3 credential chain; the app
does not read a separate credentials file or expose credentials to the browser. For a complete Docker run:

```powershell
docker compose -f docker-compose.yml -f docker-compose.profile.yml up --build
```

The profile override mounts the host `.aws` folder read-only at the nonroot container user's home. Refresh
SSO credentials on the host when they expire. On Linux, replace `USERPROFILE` with `HOME` in this optional file.
For deployed IAM roles, omit this profile override. Compose's `rag:rag` database is strictly a local option.

## RDS and deployment networking

The RDS instance is not reachable from the public internet. Run migrations and application containers in
the VPC, or connect through your organization's VPN/SSM tunnel. Attach the application security group to
compute; RDS accepts 5432 only from that group. Never solve local connectivity by opening RDS to `0.0.0.0/0`.

The supplied private subnets have no internet egress by default. Before launching containers, either add
controlled NAT routing or the necessary VPC endpoints: ECR API/Docker plus S3 for image pulls, CloudWatch Logs,
Secrets Manager, Bedrock Runtime, Bedrock Agent and Bedrock Agent Runtime where supported. Endpoint security
groups must accept TLS from the application group; enable private DNS. Other selected services may require
additional endpoints. The vector backend is accessed by Bedrock using its service role/network policy.

Use an administrator/migration identity to apply schema migrations, then create a separate `rag_app` login
with SELECT/INSERT/UPDATE/DELETE on application tables and the required sequence privileges. Keep DDL/admin
privileges out of the long-running task. Rotate credentials through Secrets Manager and redeploy tasks to
refresh injected environment secrets. The existing managed master secret is for bootstrap administration,
not automatically the runtime DATABASE_URL secret.

Download the official RDS CA bundle into `infrastructure/aws/rds-ca.pem`, build the base backend image, then
build the deployment extension image with `infrastructure/aws/Dockerfile.backend`. Use
`sslmode=verify-full&sslrootcert=/app/certs/rds-ca.pem` in the database URL and the actual RDS DNS hostname.
Percent-encode special characters in credentials. See [RDS PostgreSQL TLS](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/PostgreSQL.Concepts.General.SSL.html).

## ECS Fargate deployment

1. Create two private ECR repositories and authenticate Docker using `aws ecr get-login-password` for your region.
   Build and tag `backend/` and `frontend/` images; push them to the repositories. For RDS, extend the backend
   image as described above. Never bake `.env` or credentials into images.
2. Create a Secrets Manager secret holding the full runtime DATABASE_URL string. Add GetSecretValue on this
   exact ARN to the execution role (and KMS Decrypt if applicable). Use a separate migration secret with DDL rights.
3. Copy `ecs-task-definition.json.example`, replace every `REPLACE_...` value and register it with
   `aws ecs register-task-definition --cli-input-json file://ecs-task-definition.json`. The example contains
   frontend and backend in one task; Nginx proxies to `127.0.0.1:8000`. Compose uses `backend:8000` instead.
4. Create an ECS cluster. Before the application service, run a one-off task from the same network configuration,
   overriding the backend command with `["alembic","upgrade","head"]` and using migration credentials.
   Confirm backend exit code 0 and inspect logs. Do not run migrations concurrently in every web worker.
5. Create an **internal** Application Load Balancer with an IP target group on port 8080 and health check `/`.
   Allow its security group to reach port 8080 on the application group. Set an idle timeout longer than the
   inference timeout (for example 420 seconds), use an HTTPS listener/certificate, and put an authenticated
   gateway/VPN in front. No authentication is implemented by this POC.
6. Create a Fargate service with desired count 1, private subnets, the application group, no public IP, and the
   target group mapped to frontend:8080. Confirm task health, frontend routing, and backend readiness through
   the application URL. Scale only after testing ingestion serialization and database pool capacity.
7. Check the CloudWatch group for JSON events with `request_id`; verify an upload, ingestion completion, retrieval,
   inference and history interaction. The ECS execution role ships stdout through `awslogs`, as described in
   [ECS IAM roles](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-iam-role-overview.html).

## Costs and cleanup

Persistent costs include RDS compute/storage/backups, vector-store capacity/storage, any NAT gateway or
interface endpoints, load balancer, and Fargate. Bedrock embedding and inference are usage-based; S3,
CloudWatch and Secrets Manager have storage/request charges. OpenSearch Serverless can retain a capacity
cost while idle. Check region/model-specific AWS pricing before applying; no fixed cost estimate is assumed.

Stop/delete the ECS service and ALB, remove test documents and sidecars, synchronize/delete the data source,
delete the Knowledge Base, and separately delete its OpenSearch collection and policies if dedicated.
Console-created vector resources are **not** removed by Terraform. Export needed history, disable RDS deletion
protection deliberately, ensure the final snapshot name is unique, and review `terraform destroy`.
The versioned bucket is not force-deleted: explicitly empty object versions/delete markers only after backup.
Final RDS snapshots, retained secrets/logs, ECR images and networking created outside Terraform can continue
to incur costs; review them separately. Never run cleanup against shared resources.
