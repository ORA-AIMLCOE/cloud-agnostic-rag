# Distributor Aggregator on the shared OCI VM

URL: **https://150.230.130.251:8081/aws-app/**, behind the existing Cloudshift
HTTPS login. All users with that login share documents and question history.
The application still uses AWS account 649901308226 in Sydney: S3, Bedrock Nova
Lite, the managed Knowledge Base, and private RDS PostgreSQL. Hosting on OCI
does not change its cloud provider.

The installation is /home/ubuntu/apps/aws-rag. Uvicorn listens only on
127.0.0.1:8012. The aws-rag-tunnel service forwards 127.0.0.1:15432 through the
existing SSM bridge to RDS. PostgreSQL TLS verifies the RDS hostname using
infrastructure/aws/rds-ca.pem; hostaddr=127.0.0.1 selects the tunnel.
The private project .env contains the database URL and is not committed.

## Start and stop

Run inside the VM:

```bash
sudo systemctl start aws-rag-tunnel aws-rag
sudo systemctl status aws-rag-tunnel aws-rag --no-pager
```

Stop only AWS RAG:

```bash
sudo systemctl stop aws-rag aws-rag-tunnel
```

Both units start at boot. Stopping the entire shared VM stops the other projects
too. Stopping these services does not stop AWS RDS or the EC2 SSM bridge.

## Renew AWS login

This demo uses browser-assisted AWS login, valid for up to 12 hours. The API
uses the limited aws-rag-app role; the tunnel uses aws-rag-provision.
Automatic VM startup cannot renew an expired browser login. In the VM terminal:

```bash
/home/ubuntu/.local/bin/aws login --remote --profile aws-rag-provision --region ap-southeast-2
sudo systemctl restart aws-rag-tunnel aws-rag
```

Follow the sign-in URL and paste the authorization code into that terminal.
Unattended operation requires a separately designed renewable workload identity.

## Updates

Build with `npm run build -- --base=/aws-app/` and copy frontend/dist contents
into /var/www/aws-app. API and upload URLs use Vite's base path, while normal
local development continues to use /. The Nginx locations in
scripts/deployment/aws-rag.nginx.locations are included inside the existing
authenticated server. After changing the proxy:

```bash
sudo nginx -t -c /etc/nginx/cloudshift-nginx.conf
sudo systemctl reload cloudshift-proxy
```

Do not replace the shared proxy configuration or change the colleague's port
8080. No new public port is required. Verify the authenticated
/aws-app/api/readiness endpoint after any update.

## Deployment verification

Verified on 16 October 2026: authenticated UI/assets and API returned 200;
unauthenticated UI/API requests returned 401. Database/schema readiness, S3
access under documents/, Knowledge Base retrieval and Nova Lite inference passed.
An existing question returned a grounded answer with one source citation.
The broad bucket-level HeadBucket probe was denied; the app uses permitted
prefix-scoped object access, which passed. Backend tests: 51 passed, 3 optional
integration tests skipped. Frontend tests: 5 passed; production build passed.
Both AWS RAG service units are enabled for boot; no VM reboot was performed.
Two Q&A verification entries were added to the existing history.

## Source branch and public routes - 19 October 2026

Deploy source from the aws_app branch. The public UI is /aws-app/ and machine clients POST to
/aws-app/api/v1/answers with an integration Bearer key. The old /aws-rag/ URLs redirect with
HTTP 308 to preserve request methods. Existing service names and the private installation path
remain unchanged. Browser access continues to use the shared HTTPS login.
