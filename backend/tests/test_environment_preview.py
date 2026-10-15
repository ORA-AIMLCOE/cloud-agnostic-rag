import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.settings import Settings
from app.recipe import env_values

HEADERS = {"X-Converter-Request": "1"}

@pytest.fixture
def local_app(tmp_path):
    config = Settings(_env_file=None, state_dir=tmp_path / "state", workspace_dir=tmp_path / "work")
    app = create_app(config, start_worker=False)
    with TestClient(app) as client:
        yield client, app.state.store


def test_preview_masks_secrets_and_matches_runtime_settings(local_app):
    client, store = local_app
    response = client.post("/api/jobs", headers=HEADERS, json={
        "repository_url": "https://github.com/team/repo", "github_token": "github-private-token",
        "aws_env": "AWS_REGION=ap-southeast-2\nAWS_SECRET_ACCESS_KEY=aws-private-key\nDATABASE_URL=database-private-url"
    })
    identifier = response.json()["id"]
    target = {"db_user": "RAG_APP", "db_password": "oracle-private-password", "db_wallet_password": "wallet-private-password",
              "private_key": "signing-private-key", "region": "us-chicago-1", "db_dsn": "sandbox_low"}
    store.save_secrets(identifier, {"github_token": "github-private-token", "target": target})
    store.update(identifier, status="completed")
    response = client.get(f"/api/jobs/{identifier}/environment", headers=HEADERS)
    assert response.status_code == 200
    assert "private-password" not in response.text and "private-key" not in response.text
    assert "private-token" not in response.text and "private-url" not in response.text
    preview = response.json()
    assert preview["aws"] == {"AWS_REGION": "ap-southeast-2"} and preview["aws_ignored"] == 2
    assert preview["oci"]["OCI_DB_PASSWORD"] == "[REDACTED]"
    assert preview["oci"]["OCI_DB_WALLET_PASSWORD"] == "[REDACTED]"
    assert preview["oci"]["OCI_CONFIG_FILE"] == "config/oci/config"
    for key, value in env_values(target).items():
        if key not in preview["masked"]:
            assert preview["oci"][key] == value
    assert store.secrets(identifier)["target"]["db_password"] == "oracle-private-password"
    assert client.get(f"/api/jobs/{identifier}/environment").status_code == 403


def test_preview_handles_missing_target_and_expired_configuration(local_app):
    client, store = local_app
    identifier = store.create({}, {})
    response = client.get(f"/api/jobs/{identifier}/environment", headers=HEADERS)
    assert response.json()["oci"] is None and response.json()["aws"] == {}
    store.expire(1e20)
    response = client.get(f"/api/jobs/{identifier}/environment", headers=HEADERS)
    assert response.status_code == 200 and response.json()["oci"] is None
    assert response.json()["status"] == "expired"
    assert client.get("/api/jobs/missing/environment", headers=HEADERS).status_code == 404


def test_optional_wallet_password_is_empty_in_preview(local_app):
    client, store = local_app
    identifier = store.create({}, {"target": {"db_password": "secret", "db_wallet_password": ""}})
    preview = client.get(f"/api/jobs/{identifier}/environment", headers=HEADERS).json()
    assert preview["oci"]["OCI_DB_WALLET_PASSWORD"] == ""
    assert preview["masked"] == ["OCI_DB_PASSWORD"]
    assert preview["oci"]["OCI_CONFIG_FILE"] == "~/.oci/config"
