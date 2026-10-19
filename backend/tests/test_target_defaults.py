from fastapi.testclient import TestClient
from app.main import create_app
from app.settings import Settings


def test_private_defaults_require_api_guard_and_are_not_cached(tmp_path):
    config = Settings(
        _env_file=None, state_dir=tmp_path / "state", workspace_dir=tmp_path / "work",
        cloudshift_default_db_password="test-db-secret",
        cloudshift_default_wallet_password="test-wallet-secret",
        cloudshift_default_github_token="test-github-secret",
        cloudshift_default_repository_url="https://github.com/team/repo",
    )
    assert "test-db-secret" not in repr(config)
    with TestClient(create_app(config, start_worker=False)) as client:
        assert client.get("/api/target-defaults").status_code == 403
        headers = {"X-Converter-Request": "1"}
        assert client.get("/api/target-defaults", headers={
            **headers, "Origin": "https://untrusted.example",
        }).status_code == 403
        response = client.get("/api/target-defaults", headers=headers)
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert response.json() == {
            "db_password": "test-db-secret",
            "db_wallet_password": "test-wallet-secret",
            "repository_url": "https://github.com/team/repo",
            "github_token_configured": True,
        }
        for route in ("/api/status", "/api/jobs"):
            response = client.get(route, headers=headers)
            assert "test-db-secret" not in response.text
            assert "test-wallet-secret" not in response.text


def test_private_defaults_are_blank_unless_configured(tmp_path):
    config = Settings(_env_file=None, state_dir=tmp_path / "state",
                      workspace_dir=tmp_path / "work",
                      cloudshift_default_db_password="",
                      cloudshift_default_wallet_password="",
                      cloudshift_default_github_token="",
                      cloudshift_default_repository_url="")
    with TestClient(create_app(config, start_worker=False)) as client:
        assert client.get("/api/target-defaults", headers={
            "X-Converter-Request": "1",
        }).json() == {"db_password": "", "db_wallet_password": "", "repository_url": "", "github_token_configured": False}

def test_saved_github_token_stays_server_side_and_is_bound_to_repository(tmp_path):
    config = Settings(_env_file=None, state_dir=tmp_path / "state",
                      workspace_dir=tmp_path / "work",
                      cloudshift_default_repository_url="https://github.com/team/repo",
                      cloudshift_default_github_token="server-only-test-token")
    assert "server-only-test-token" not in repr(config)
    headers = {"X-Converter-Request": "1"}
    with TestClient(create_app(config, start_worker=False)) as client:
        for path in ("/api/target-defaults", "/api/status", "/api/jobs"):
            assert "server-only-test-token" not in client.get(path, headers=headers).text
        response = client.post("/api/jobs", headers=headers,
                               json={"repository_url": "https://github.com/team/repo.git"})
        assert response.status_code == 202
        assert "server-only-test-token" not in response.text
        assert client.app.state.store.secrets(response.json()["id"])["github_token"] == "server-only-test-token"
        assert client.post("/api/jobs", headers=headers,
                           json={"repository_url": "https://github.com/team/other"}).status_code == 400
        response = client.post("/api/jobs", headers=headers,
                               json={"repository_url": "https://github.com/team/other",
                                     "github_token": "manual-test-token"})
        assert response.status_code == 202
        assert client.app.state.store.secrets(response.json()["id"])["github_token"] == "manual-test-token"
        for path in ("/api/status", "/api/jobs", "/api/jobs/" + response.json()["id"]):
            text = client.get(path, headers=headers).text
            assert "server-only-test-token" not in text
            assert "manual-test-token" not in text
