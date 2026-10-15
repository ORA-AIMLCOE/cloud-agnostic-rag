from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import Settings

HEADERS = {"X-Converter-Request": "1"}


@pytest.fixture
def local_app(tmp_path):
    config = Settings(_env_file=None, state_dir=tmp_path / "state", workspace_dir=tmp_path / "work")
    app = create_app(config, start_worker=False)
    with TestClient(app) as client:
        yield client, app.state.store, app.state.worker


@pytest.mark.parametrize("status", ["completed", "failed", "cancelled", "expired"])
def test_delete_removes_history_credentials_and_only_job_workspace(local_app, status):
    client, store, worker = local_app
    identifier = store.create({"repository_url": "https://github.com/team/repo"}, {"github_token": "secret"})
    store.update(identifier, status=status, branch_url="https://github.com/team/repo/tree/migration/test")
    directory = worker.directory(identifier)
    directory.mkdir(parents=True)
    (directory / "source.txt").write_text("source")
    sibling = directory.parent / "unrelated.txt"
    sibling.write_text("keep")
    with patch("app.github.GitHub", side_effect=AssertionError("Deletion must stay local")):
        response = client.delete(f"/api/jobs/{identifier}", headers=HEADERS)
    assert response.status_code == 200
    assert not directory.exists() and sibling.read_text() == "keep"
    assert client.get("/api/jobs", headers=HEADERS).json() == []
    assert client.get(f"/api/jobs/{identifier}", headers=HEADERS).status_code == 404
    assert client.get(f"/api/jobs/{identifier}/configuration", headers=HEADERS).status_code == 404
    with pytest.raises(ValueError):
        store.secrets(identifier)
    assert client.delete(f"/api/jobs/{identifier}", headers=HEADERS).status_code == 404


@pytest.mark.parametrize("status", ["ready", "running", "queued", "queued_inspection"])
def test_delete_rejects_unfinished_jobs(local_app, status):
    client, store, worker = local_app
    identifier = store.create({}, {"github_token": "secret"})
    store.update(identifier, status=status)
    directory = worker.directory(identifier)
    directory.mkdir(parents=True)
    assert client.delete(f"/api/jobs/{identifier}", headers=HEADERS).status_code == 409
    assert store.get(identifier)["status"] == status and directory.exists()
    assert store.secrets(identifier)["github_token"] == "secret"


def test_delete_requires_local_request_and_reports_cleanup_failure(local_app):
    client, store, worker = local_app
    identifier = store.create({}, {})
    store.update(identifier, status="failed")
    worker.directory(identifier).mkdir(parents=True)
    assert client.delete(f"/api/jobs/{identifier}").status_code == 403
    assert client.delete(f"/api/jobs/{identifier}", headers={**HEADERS, "Origin": "https://evil.example"}).status_code == 403
    with patch("app.main.shutil.rmtree", side_effect=PermissionError("private-path")):
        response = client.delete(f"/api/jobs/{identifier}", headers=HEADERS)
    assert response.status_code == 409 and "private-path" not in response.text
    assert store.get(identifier)["status"] == "failed"
    assert client.delete("/api/jobs/not-a-valid-id", headers=HEADERS).status_code == 400
