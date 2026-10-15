import io
import json
import zipfile

import pytest
from dotenv import dotenv_values
from fastapi.testclient import TestClient

from app.main import create_app
from app.models import ConvertRequest, TargetConfig
from app.recipe import env_text, model_context
from app.security import reveal_target
from app.settings import Settings


def target_values():
    return {"region": "us-chicago-1", "compartment_id": "compartment", "namespace": "namespace", "bucket": "bucket",
        "llm_model_id": "astra", "llm_endpoint": "https://inference.generativeai.us-chicago-1.oci.oraclecloud.com",
        "embedding_model_id": "embedding", "embedding_endpoint": "https://inference.generativeai.us-chicago-1.oci.oraclecloud.com",
        "embedding_dimensions": 1536, "db_user": "RAG_APP", "db_password": "not-a-real-password",
        "db_dsn": "tcps://db.example:1521/service"}


def test_oracle_env_preserves_password_and_windows_wallet_path():
    data = target_values()
    data.update(db_password="quote'back\\slash$!", db_wallet_dir=r"C:\Users\demo\wallet", db_wallet_password="wallet-secret")
    target = TargetConfig(**data)
    assert data["db_password"] not in target.model_dump_json()
    plain = reveal_target(target)
    values = dotenv_values(stream=io.StringIO(env_text(plain)), interpolate=False)
    assert values["OCI_DB_PASSWORD"] == data["db_password"]
    assert values["OCI_DB_WALLET_DIR"] == data["db_wallet_dir"]
    assert values["OCI_DB_WALLET_PASSWORD"] == "wallet-secret"
    assert "DATABASE_URL" not in values and "VECTOR_DATABASE_URL" not in values
    placeholder = env_text(plain, placeholders=True)
    assert "wallet-secret" not in placeholder and "not-a-real-password" not in placeholder


@pytest.mark.parametrize("dsn,wallet,allowed", [
    ("tcps://db.example:1521/service", "", True),
    ("(description=(address=(protocol=tcps)(host=db.example)(port=1521))(connect_data=(service_name=service)))", "", True),
    ("app_low", "config/wallet", True),
    ("app_low", "", False),
    ("tcp://db.example:1521/service", "", False),
    ("postgresql+psycopg://user:password@host/db", "", False),
    ("tcps://db.example:1521/service?ssl_server_dn_match=no", "", False),
])
def test_oracle_target_validation(dsn, wallet, allowed):
    values = target_values(); values.update(db_dsn=dsn, db_wallet_dir=wallet)
    request = ConvertRequest(target=TargetConfig(**values), publish=False, acknowledge_source_transfer=True)
    if allowed:
        request.validate_request()
    else:
        with pytest.raises(ValueError):
            request.validate_request()


def test_database_credentials_only_in_encrypted_payload_and_private_download(tmp_path):
    config = Settings(_env_file=None, state_dir=tmp_path / "state", workspace_dir=tmp_path / "work",
        astra_base_url="https://inference.generativeai.us-chicago-1.oci.oraclecloud.com", astra_model_id="astra",
        astra_compartment_id="compartment")
    values = target_values(); values["db_wallet_password"] = "private-wallet-secret"
    with TestClient(create_app(config, start_worker=False)) as client:
        store = client.app.state.store
        job = store.create({"publish_allowed": True}, {"github_token": "test-token"})
        store.update(job, status="ready")
        headers = {"X-Converter-Request": "1"}
        result = client.post(f"/api/jobs/{job}/convert", headers=headers,
            json={"target": values, "publish": False, "acknowledge_source_transfer": True})
        assert result.status_code == 202
        for secret in [values["db_password"], values["db_wallet_password"]]:
            assert secret not in result.text
            assert secret.encode() not in (config.state_dir / "jobs.sqlite3").read_bytes()
        saved = store.secrets(job)["target"]
        context = model_context({}, {}, saved)
        assert values["db_password"] not in json.dumps(context)
        assert values["db_dsn"] not in json.dumps(context)
        assert "Oracle Autonomous" in context["database_contract"]
        store.update(job, status="completed")
        download = client.get(f"/api/jobs/{job}/configuration", headers=headers)
        with zipfile.ZipFile(io.BytesIO(download.content)) as archive:
            env = dotenv_values(stream=io.StringIO(archive.read(".env").decode()), interpolate=False)
            assert env["OCI_DB_PASSWORD"] == values["db_password"]
            assert env["OCI_DB_WALLET_PASSWORD"] == values["db_wallet_password"]
            assert archive.namelist() == [".env"]
