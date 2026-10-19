# Remote access

Cloudshift can serve one shared workspace through an authenticated HTTPS reverse proxy.
Everyone with proxy credentials can inspect jobs, run conversions, delete jobs, and download
private environment configuration. This is not a tenant-isolated multi-user deployment.

Keep uvicorn on `127.0.0.1:8011`. Configure an exact external origin in the converter `.env`:

```dotenv
CLOUDSHIFT_PUBLIC_ORIGIN=https://150.230.130.251:8081
```

The default blank value preserves local SSH-tunnel access. Wildcard origins, plain HTTP,
credentials embedded in URLs, and URL paths are rejected. Local port 8011 remains supported.

The reverse proxy must enforce authentication for every path, including the frontend,
API, and private downloads. Use TLS, a protected password file, and a separate nginx server
block so existing applications are unaffected. Forward the original Host and Origin headers;
do not strip Origin or bypass application request checks. Set client_max_body_size to 256k.

IP-address certificates from Let's Encrypt require the shortlived profile and automated
renewal. With Certbot 5.4 or newer, use webroot verification on port 80 and --ip-address.
Expose only /.well-known/acme-challenge/ on the HTTP listener; return 404 for other paths.
Serve the application on its HTTPS listener and reload nginx after certificate renewal.
A stopped VM cannot renew its certificate: after a long stop, renew it before sharing the URL.

For the deployed VM, the dedicated nginx site is /etc/nginx/sites-available/cloudshift.
The private access details are /home/ubuntu/.config/cloudshift/access.txt (mode 0600).
The cloudshift-cert-renew.timer renews certificates and reloads cloudshift-proxy when needed.
The dedicated proxy uses /etc/nginx/cloudshift-nginx.conf and cloudshift-proxy.service;
it does not enable or reload the pre-existing nginx.service or Docker proxy.
Keep OCI ingress restricted to required ports; port 8011 must stay private.


### Shared password autofill

The conversion form defaults to the Hyderabad Cloudshift RAG resources.
Set `CLOUDSHIFT_DEFAULT_DB_PASSWORD` and `CLOUDSHIFT_DEFAULT_WALLET_PASSWORD`
in the private root `.env` and restart Cloudshift to autofill password inputs.
Every user authenticated to the shared workspace can retrieve these passwords.
The defaults are sent through `/api/target-defaults` with `Cache-Control: no-store`;
they are not included in frontend assets, status responses, or browser storage.
Keep the backend on loopback behind the authenticated HTTPS proxy.

The target OCI profile must be installed on the generated application's runtime
machine and belong to the target tenancy. Converter code-review credentials are
configured separately and are not replaced by changing these form defaults.

## Saved GitHub token

Set CLOUDSHIFT_DEFAULT_REPOSITORY_URL and CLOUDSHIFT_DEFAULT_GITHUB_TOKEN in the VM private .env. The repository URL autofills; the token field shows Saved token on server. Leaving the field blank uses the saved token only for that repository. Entering a token overrides it. All authenticated workspace users can use this credential to inspect and publish conversions; the API returns only a configured flag, never the saved token. Restart cloudshift after changing these values. Keep the .env readable only by its service owner.
