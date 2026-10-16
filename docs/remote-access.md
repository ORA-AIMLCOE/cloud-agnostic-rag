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
