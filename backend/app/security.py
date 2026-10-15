import re
from urllib.parse import urlsplit


class SafeError(Exception):
    """A deliberately non-sensitive, user-visible failure."""


def validate_oci_endpoint(value):
    p = urlsplit(value.strip())
    host = p.hostname or ""
    if (
        p.scheme != "https"
        or p.username
        or p.password
        or p.query
        or p.fragment
        or p.port not in (None, 443)
        or not host.endswith(".oci.oraclecloud.com")
    ):
        raise ValueError("Use an HTTPS OCI service endpoint ending in .oci.oraclecloud.com.")
    return value.strip().rstrip("/")


# Parse as data only. Never interpolate dotenv values or pass source credentials to a process.
def parse_aws_env(text):
    allowed = {
        "AWS_REGION",
        "AWS_DEFAULT_REGION",
        "AWS_S3_BUCKET",
        "AWS_S3_PREFIX",
        "AWS_BEDROCK_MODEL_ID",
        "AWS_KNOWLEDGE_BASE_ID",
        "AWS_KB_DATA_SOURCE_ID",
        "AWS_KB_MODE",
        "CLOUD_PROVIDER",
        "TOP_K",
        "MAX_UPLOAD_BYTES",
    }
    result = {}
    ignored = 0
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.removeprefix("export ").split("=", 1)
        key = key.strip()
        if key in allowed:
            value = value.strip().strip("\"'")
            if len(value) > 512 or any(c in value for c in ("\n", "\r", "\x00")):
                raise SafeError("An AWS configuration value is too long or invalid.")
            result[key] = value
        else:
            ignored += 1
    return result, ignored


def has_secret(text):
    if re.search(
        r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|(?:gh[pousr]_[A-Za-z0-9]{20,})|(?:AKIA|ASIA)[A-Z0-9]{16}",
        text,
    ):
        return True
    # Known assignments and credential-bearing URLs. Template/default development values are allowed.
    # Terraform's RDS password-management switch is a boolean, not a password.
    assignment_text = re.sub(
        r"(?m)^[ \t]*manage_master_user_password[ \t]*=[ \t]*(?:true|false)[ \t]*\r?$",
        "",
        text,
    )
    values = re.findall(
        r"(?im)^\s*(?:AWS_SECRET_ACCESS_KEY|AWS_SESSION_TOKEN|GITHUB_TOKEN|ASTRA_API_KEY|OCI_API_KEY|[A-Z_]*PASSWORD)\s*=\s*([^\r\n]+)",
        assignment_text,
    )
    values += re.findall(r"postgres(?:ql)?(?:\+psycopg)?://[^:/\s]+:([^@\s]+)@", text)
    for value in values:
        v = value.strip(" \"'").lower()
        if (
            v
            and v not in {"rag", "postgres", "password", "test", "secret", "changeme"}
            and not any(x in v for x in ("<", "${", "replace", "example", "your_", "url-encoded"))
        ):
            return True
    return False


def check_source_secrets(files):
    flagged = [path for path, text in files.items() if has_secret(text)]
    if flagged:
        raise SafeError(
            "Possible committed credentials detected. Sanitize the source before conversion. Files: "
            + ", ".join(flagged[:8])
        )


def reveal_target(target):
    data = target.model_dump(mode="json")
    for key in ("db_password", "db_wallet_password", "private_key"):
        value = getattr(target, key)
        data[key] = value.get_secret_value() if value is not None else ""
    return data
