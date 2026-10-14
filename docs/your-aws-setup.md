# Your AWS configuration

Configured on 2026-10-13 in account `649901308226`, Sydney (`ap-southeast-2`).
AWS reported an active Free Plan and USD 120 remaining credits at audit time. No account upgrade or payment-method change was made.

## Start the project

From the project directory, activate your existing environment and copy the prepared configuration:

```powershell
& 'C:\Users\adarshmi\Desktop\EXPLORE\0_virtual_environment\aws_rag_env\Scripts\Activate.ps1'
Copy-Item .env.example .env
```

If the AWS session has expired, refresh the source login:

```powershell
& "$env:LOCALAPPDATA\Programs\Amazon\AWSCLIV2\aws.exe" login --profile aws-rag-provision --region ap-southeast-2
```

Terminal 1, from the project directory:

```powershell
.\scripts\start-db-tunnel.ps1
```

Keep the tunnel terminal open. It forwards local port 15432 through EC2 Session Manager to private RDS port 5432.
The database URL retains the RDS hostname for TLS verification and uses `hostaddr=127.0.0.1` for the tunnel.
The official Session Manager plugin is in `.tools/session-manager`, and the RDS CA bundle is in
`infrastructure/aws/rds-ca.pem`. Retain these files when running locally.
Do not start a second tunnel on the same local port.

Terminal 2, with `aws_rag_env` active:

```powershell
cd backend
python -m alembic upgrade head
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

Terminal 3:

```powershell
cd frontend
npm run dev
```

Open http://localhost:5173. Readiness: http://localhost:8000/api/readiness.
The schema is already migrated; repeating `alembic upgrade head` is safe.
Do not run the local Docker PostgreSQL setup for this configuration.

## Verified resource mapping

| Setting/resource | Configuration |
|---|---|
| `AWS_PROFILE` | `aws-rag-app`, assumes the dedicated limited app role using `aws-rag-provision` |
| `AWS_REGION` | `ap-southeast-2` |
| `AWS_BEDROCK_MODEL_ID` | `amazon.nova-lite-v1:0`, live invocation verified |
| `AWS_S3_BUCKET` | `aws-rag-documents-adarsh-20261013`, Sydney, SSE-S3, all public-access blocks enabled |
| `AWS_S3_PREFIX` | `documents/`, matches the managed connector |
| `AWS_KNOWLEDGE_BASE_ID` | `YNZKTQSGBJ`, existing Managed Knowledge Base retained |
| `AWS_KB_DATA_SOURCE_ID` | `TSRBHBQ9IN`, managed S3 connector |
| `AWS_KB_MODE` | `managed` |
| Embedding model | Titan Text Embeddings V2, 1024 float dimensions |
| `DATABASE_URL` | Populated with generated `rag` credentials, private RDS endpoint, local tunnel and TLS CA path |
| PostgreSQL | `aws-rag-postgres`, PostgreSQL 16.15, `db.t4g.micro`, Single-AZ, encrypted 20 GiB gp3 |
| Connectivity | Isolated database subnets; PostgreSQL inbound only from bridge security group |
| SSM bridge | `i-0bed6e1f2728db3fd`, `t3.micro`, encrypted 8 GiB disk, IMDSv2, no inbound ports |

`APP_NAME`, `CLOUD_PROVIDER`, upload limits, retrieval/token settings, logging, CORS and tracing are app settings;
they do not each require an AWS component. `LANGSMITH_TRACING=false` needs no LangSmith account.
Local JSON logs go to the terminal. This local deployment does not ship app logs to CloudWatch.

The IAM policy's incorrect account `929394210168` was replaced with `649901308226`, validated by Access Analyzer,
and deployed to `aws-rag-local-app`. It is attached to the dedicated `aws-rag-app` role. No access keys are
embedded in `.env.example`; AWS uses refreshable profile credentials. The database password is real, so
`.env.example` and `.env` are ignored by Git. Admin recovery credentials are in the ignored
`.validation/private-database-state.json`; keep this file private.

The app's `rag` PostgreSQL role owns only the application database and can run its migrations; it is not
the RDS administrator. A production deployment should separate migration and runtime database roles.

## Costs and stopping development resources

These are credit-consuming resources, not permanently free resources. Sydney RDS compute was quoted by the
AWS Pricing API at USD 0.025/hour (about USD 18.25 for 730 hours), excluding storage, backups, the EC2 bridge,
public IPv4, S3 and Bedrock usage. The bridge uses standard CPU credits to avoid unlimited-mode surplus charges.
The database has deletion protection and one-day backup retention. No NAT gateway or paid VPC endpoints were created.

When finished, stop the backend and tunnel. Stopping the tunnel does not stop EC2 or RDS. To stop those:

```powershell
$aws = "$env:LOCALAPPDATA\Programs\Amazon\AWSCLIV2\aws.exe"
& $aws ec2 stop-instances --instance-ids i-0bed6e1f2728db3fd --profile aws-rag-provision --region ap-southeast-2
& $aws rds stop-db-instance --db-instance-identifier aws-rag-postgres --profile aws-rag-provision --region ap-southeast-2
```

RDS automatically restarts after seven days stopped; storage remains billable while stopped.
Use the corresponding `start-instances` and `start-db-instance` commands before restarting the tunnel,
and wait for RDS `available` and the bridge SSM status `Online`.

Resource IDs are recorded in `infrastructure/aws/development-resources.json`. These development resources
were created directly through AWS APIs, not imported into the generic Terraform foundation. Do not apply
the whole foundation against this setup without an explicit import/reconciliation plan.

## References

IAM Policy Autopilot was run as a supplemental static audit. Its broad baseline was not deployed;
the existing resource-scoped app policy was corrected and validated with AWS Access Analyzer and live calls.
To reproduce the static audit:

```powershell
$sources = Get-ChildItem backend/app/providers/aws/*.py | Where-Object Name -ne '__init__.py' | ForEach-Object FullName
uvx iam-policy-autopilot@latest generate-policies @sources --region ap-southeast-2 --account 649901308226 --service-hints s3 bedrock --pretty
```

- [Managed S3 connectors](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-ds-s3.html)
- [Managed search and reranking](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-test-retrieve.html)
- [RDS PostgreSQL TLS](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/PostgreSQL.Concepts.General.SSL.html)
- [RDS stopping behavior](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_StopInstance.html)
- [AWS Free Plan](https://aws.amazon.com/free/free-tier-faqs/)
