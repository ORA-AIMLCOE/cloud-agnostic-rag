import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.settings import Settings


@pytest.mark.parametrize("origin", [
    "http://150.230.130.251:8081", "https://*.example.com", "https://user:pass@example.com",
    "https://example.com/path", "https://example.com?token=x", "https://example.com#fragment",
    "https://example.com:99999", "https://bad host",
])
def test_public_origin_rejects_unsafe_values(origin):
    with pytest.raises(ValueError):
        Settings(_env_file=None, cloudshift_public_origin=origin)


def test_proxy_origin_keeps_host_origin_and_header_checks(tmp_path):
    origin = "https://150.230.130.251:8081"
    config = Settings(_env_file=None, cloudshift_public_origin=origin + "/",
                      state_dir=tmp_path / "state", workspace_dir=tmp_path / "work")
    with TestClient(create_app(config, start_worker=False), base_url=origin) as client:
        headers = {"X-Converter-Request": "1", "Origin": origin}
        response = client.get("/api/status", headers=headers)
        assert response.status_code == 200
        assert response.json()["scope"] == "shared_workspace"
        assert client.get("/api/status", headers={"Origin": origin}).status_code == 403
        for other in ["https://evil.example", "http://150.230.130.251:8081", "https://150.230.130.251:8082"]:
            assert client.get("/api/status", headers={**headers, "Origin": other}).status_code == 403
        assert client.get("/api/status", headers={**headers, "Host": "evil.example"}).status_code == 400
        assert client.get("/api/status", headers={**headers, "Host": "127.0.0.1:8011",
                                                  "Origin": "http://127.0.0.1:8011"}).status_code == 200


def test_public_host_is_disabled_by_default(tmp_path):
    config = Settings(_env_file=None, cloudshift_public_origin="",
                      state_dir=tmp_path / "state", workspace_dir=tmp_path / "work")
    with TestClient(create_app(config, start_worker=False), base_url="https://150.230.130.251:8081") as client:
        assert client.get("/api/status", headers={"X-Converter-Request": "1"}).status_code == 400
