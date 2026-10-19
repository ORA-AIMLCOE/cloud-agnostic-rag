from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")
    cloudshift_public_origin: str = ""
    # Shared UI defaults supplied only through the protected, non-cached API.
    cloudshift_default_db_password: SecretStr = SecretStr("")
    cloudshift_default_wallet_password: SecretStr = SecretStr("")
    cloudshift_default_repository_url: str = ""
    # Used only on the server for the configured repository; never returned by the API.
    cloudshift_default_github_token: SecretStr = SecretStr("")
    astra_base_url: str = ""
    astra_model_id: str = ""
    astra_api_format: Literal["oci_generic", "responses", "chat_completions"] = "oci_generic"
    astra_auth_mode: Literal["api_key", "oci_profile"] = "oci_profile"
    astra_api_key: str = ""
    astra_compartment_id: str = ""
    astra_oci_config_file: str = "~/.oci/config"
    astra_oci_profile: str = "DEFAULT"
    astra_verbosity: Literal["LOW", "MEDIUM", "HIGH"] = "MEDIUM"
    astra_max_output_tokens: int = Field(default=24000, ge=1000, le=64000)
    astra_max_attempts: int = Field(default=2, ge=1, le=3)
    validator_image: str = "aws-oci-validator:oracle-v1"
    job_retention_hours: int = Field(default=24, ge=1, le=168)
    state_dir: Path = ROOT / ".state"
    workspace_dir: Path = ROOT / ".workspaces"

    @field_validator("cloudshift_public_origin")
    @classmethod
    def validate_public_origin(cls, value):
        value = value.strip().rstrip("/")
        if not value:
            return ""
        parsed = urlsplit(value)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
                or parsed.path or parsed.query or parsed.fragment or "*" in value
                or any(char.isspace() for char in value)):
            raise ValueError("Use an exact HTTPS origin behind an authenticated reverse proxy.")
        _ = parsed.port  # Validate an explicit port number.
        return value

    @property
    def astra_configured(self):
        if self.astra_api_format == "oci_generic":
            return bool(
                self.astra_base_url
                and self.astra_model_id
                and self.astra_compartment_id
                and self.astra_auth_mode == "oci_profile"
            )
        return bool(
            self.astra_base_url
            and self.astra_model_id
            and (self.astra_auth_mode == "oci_profile" or self.astra_api_key)
        )


@lru_cache
def settings():
    return Settings()
