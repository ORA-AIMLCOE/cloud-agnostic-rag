import re
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, SecretStr, field_validator


class InspectRequest(BaseModel):
    repository_url: str
    source_branch: str = "aws_app"
    github_token: SecretStr = SecretStr("")
    aws_env: str = Field(default="", max_length=65536)

    @field_validator("repository_url")
    @classmethod
    def repository(cls, value):
        p = urlsplit(value.strip())
        if p.scheme != "https" or p.netloc != "github.com" or p.query or p.fragment:
            raise ValueError("Use an HTTPS github.com repository URL.")
        path = p.path.rstrip("/").removesuffix(".git")
        if not re.fullmatch(r"/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", path):
            raise ValueError("Use https://github.com/owner/repository without a branch path.")
        return "https://github.com" + path

    @field_validator("source_branch")
    @classmethod
    def branch(cls, value):
        if not re.fullmatch(r"[A-Za-z0-9_./-]{1,200}", value) or ".." in value or "//" in value:
            raise ValueError("Enter a valid source branch.")
        return value


class TargetConfig(BaseModel):
    region: str = Field(min_length=3, max_length=80)
    compartment_id: str = Field(min_length=5, max_length=255)
    namespace: str = Field(min_length=1, max_length=255)
    bucket: str = Field(min_length=1, max_length=255)
    object_prefix: str = "documents/"
    llm_model_id: str = Field(min_length=1, max_length=255)
    llm_endpoint: str
    llm_format: Literal["generic", "generic_astra", "cohere", "responses", "chat_completions"] = "generic"
    llm_serving_mode: Literal["on_demand", "dedicated"] = "on_demand"
    embedding_model_id: str = Field(min_length=1, max_length=255)
    embedding_endpoint: str
    embedding_serving_mode: Literal["on_demand", "dedicated"] = "on_demand"
    embedding_dimensions: int = Field(ge=1, le=16000)
    embedding_set_dimensions: bool = False
    chunk_chars: int = Field(default=1800, ge=200, le=12000)
    chunk_overlap: int = Field(default=200, ge=0, le=2000)
    db_user: str = Field(min_length=1, max_length=128)
    db_password: SecretStr
    db_dsn: str = Field(min_length=1, max_length=8192)
    db_wallet_dir: str = Field(default="", max_length=2048)
    db_wallet_password: SecretStr = SecretStr("")
    oci_profile: str = Field(default="DEFAULT", pattern=r"^[A-Za-z0-9_-]{1,80}$")
    tenancy_id: str = ""
    user_id: str = ""
    fingerprint: str = ""
    private_key: SecretStr = SecretStr("")

    @field_validator("llm_endpoint", "embedding_endpoint")
    @classmethod
    def endpoint(cls, value):
        from app.security import validate_oci_endpoint

        return validate_oci_endpoint(value)

    @field_validator("object_prefix")
    @classmethod
    def prefix(cls, value):
        value = value.strip("/")
        if not value or ".." in value or "\\" in value:
            raise ValueError("Use a nonempty relative object prefix.")
        return value + "/"


class ConvertRequest(BaseModel):
    target: TargetConfig
    publish: bool = True
    acknowledge_source_transfer: bool

    def validate_request(self):
        if not self.acknowledge_source_transfer:
            raise ValueError("Confirm sending relevant source code to your configured OCI model.")
        if self.target.chunk_overlap >= self.target.chunk_chars:
            raise ValueError("Chunk overlap must be smaller than chunk size.")
        if self.target.private_key.get_secret_value():
            if not all((self.target.tenancy_id, self.target.user_id, self.target.fingerprint)):
                raise ValueError("Provide tenancy, user and fingerprint when including an OCI signing key.")
            from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
            from cryptography.hazmat.primitives.serialization import load_pem_private_key

            try:
                key = load_pem_private_key(self.target.private_key.get_secret_value().encode(), password=None)
                if not isinstance(key, RSAPrivateKey):
                    raise TypeError()
            except (ValueError, TypeError) as exc:
                raise ValueError(
                    "Use a valid unencrypted RSA OCI signing key, or leave it blank and configure a local OCI profile."
                ) from exc
        if not self.target.db_password.get_secret_value():
            raise ValueError("Provide the Autonomous Database application user password.")
        dsn = self.target.db_dsn.strip()
        alias = bool(re.fullmatch(r"[A-Za-z0-9_.-]+", dsn))
        if alias:
            if not self.target.db_wallet_dir:
                raise ValueError("A TNS alias requires a wallet directory on the runtime machine.")
        elif not (dsn.lower().startswith("tcps://") or
                  (dsn.startswith("(") and re.search(r"protocol\s*=\s*tcps\s*\)", dsn, re.IGNORECASE))):
            raise ValueError("Use the Autonomous Database TCPS connection string or a wallet TNS alias.")
        if re.search(r"protocol\s*=\s*tcp\s*\)|ssl_server_dn_match\s*=\s*(no|false|off)", dsn, re.IGNORECASE):
            raise ValueError("TLS and server identity verification are required.")
