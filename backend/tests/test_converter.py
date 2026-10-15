import io
import json
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
import httpx
import pytest
from fastapi.testclient import TestClient
from app.security import SafeError, parse_aws_env, has_secret, validate_oci_endpoint
from app.github import unpack_archive, publishing_safe, GitHub
from app.store import Store
from app.models import TargetConfig, ConvertRequest
from app.settings import Settings
from app.validation import apply_model_patch, diff_report
from app.main import create_app
from app.astra import Astra
from app.recipe import env_text


def test_env_import_discards_credentials_and_never_interpolates():
    result, ignored = parse_aws_env(
        "AWS_REGION=us-test-1\nAWS_SECRET_ACCESS_KEY=do-not-store\nDATABASE_URL=private\nAWS_S3_BUCKET=${PRIVATE_VALUE}"
    )
    assert result == {"AWS_REGION": "us-test-1", "AWS_S3_BUCKET": "${PRIVATE_VALUE}"}
    assert ignored == 2 and "do-not-store" not in json.dumps(result)


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost",
        "https://evil.example/",
        "https://oci.oraclecloud.com.evil.example",
        "https://user:pass@inference.generativeai.test.oci.oraclecloud.com",
    ],
)
def test_endpoint_rejects_untrusted_destinations(url):
    with pytest.raises(ValueError):
        validate_oci_endpoint(url)


def test_secret_scanner():
    assert has_secret("AWS_SECRET_ACCESS_KEY=real-secret-value")
    assert has_secret("-----BEGIN PRIVATE KEY-----")
    assert not has_secret("DATABASE_URL=postgresql+psycopg://<user>:<password>@<host>/db")


def archive(path, content=b"text"):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr(path, content)
    return buffer.getvalue()


def test_archive_traversal_and_committed_secrets():
    for name in ("root/../outside", "root/.env", "root/node_modules/file"):
        with pytest.raises(SafeError):
            unpack_archive(archive(name))
    assert unpack_archive(archive("root/backend/test.py")) == {"backend/test.py": b"text"}


def test_workflows_do_not_trigger_accidental_deployment():
    assert publishing_safe({".github/workflows/check.yml": b"on:\n  push:\n    branches: [main]\n"})
    assert not publishing_safe({".github/workflows/check.yml": b"on: [push]"})
    assert not publishing_safe({".github/workflows/check.yml": b"on: create"})


def test_vault_and_durable_claim(tmp_path):
    store = Store(tmp_path)
    job = store.create({"repository_url": "url"}, {"github_token": "sensitive-token"})
    assert b"sensitive-token" not in (tmp_path / "jobs.sqlite3").read_bytes()
    assert "sensitive-token" not in json.dumps(store.get(job))
    assert Store(tmp_path).secrets(job)["github_token"] == "sensitive-token"
    assert store.claim() == (job, "queued_inspection")
    assert store.claim() is None
    store.recover()
    assert store.get(job)["status"] == "failed"
    store.expire(1e20)
    with pytest.raises(ValueError):
        store.secrets(job)


def test_queue_cannot_run_twice(tmp_path):
    store = Store(tmp_path)
    job = store.create({}, {})
    store.update(job, status="ready")
    store.queue_conversion(job)
    with pytest.raises(ValueError):
        store.queue_conversion(job)


def test_generated_patch_cannot_edit_core_or_execute_commands():
    for path, content in [
        ("backend/app/workflows/rag_graph.py", "pass"),
        ("backend/app/providers/oci/storage.py", "import subprocess"),
        ("backend/app/providers/oci/storage.py", "exec('anything')"),
    ]:
        with pytest.raises(SafeError):
            apply_model_patch({}, {"files": [{"path": path, "content": content}]})
    assert apply_model_patch({}, {"files": []}) == {}


def test_diff_reports_real_line_changes():
    report = diff_report({"file.py": b"a\nb\n"}, {"file.py": "a\nc\n"})
    assert report[0]["added"] == 1 and report[0]["removed"] == 1


def test_astra_calls_oci_and_parses_response(monkeypatch):
    config = Settings(
        _env_file=None,
        astra_base_url="https://inference.generativeai.test.oci.oraclecloud.com/openai/v1",
        astra_api_key="sensitive",
        astra_api_format="responses",
        astra_auth_mode="api_key",
        astra_model_id="test-model",
    )
    response = MagicMock(status_code=200)
    response.json.return_value = {
        "output": [{"content": [{"type": "output_text", "text": '{"files": [], "summary": "Reviewed"}'}]}],
        "usage": {"input_tokens": 12},
    }
    post = MagicMock(return_value=response)
    monkeypatch.setattr("app.astra.requests.post", post)
    patch, usage = Astra(config).refine({"implementation": "test"})
    assert patch["files"] == [] and usage["input_tokens"] == 12
    assert post.call_args.args[0].startswith(config.astra_base_url)
    assert "sensitive" not in json.dumps(post.call_args.kwargs["json"])


def test_github_push_creates_new_ref_without_updating_main():
    calls = []

    def handler(request):
        calls.append((request.method, request.url.path, json.loads(request.content)))
        return httpx.Response(201, json={"ref": "refs/heads/migration/oci-test"})

    client = GitHub("https://github.com/owner/repo", "token", httpx.MockTransport(handler))
    client.publish("migration/oci-test", "abc")
    assert calls == [
        ("POST", "/repos/owner/repo/git/refs", {"ref": "refs/heads/migration/oci-test", "sha": "abc"})
    ]


def test_api_rejects_cross_origin_and_redacts_validation(tmp_path):
    config = Settings(_env_file=None, state_dir=tmp_path / "state", workspace_dir=tmp_path / "work")
    with TestClient(create_app(config, start_worker=False)) as client:
        assert client.get("/api/status").status_code == 403
        assert (
            client.get(
                "/api/status", headers={"X-Converter-Request": "1", "Origin": "https://evil.example"}
            ).status_code
            == 403
        )
        result = client.post(
            "/api/jobs",
            headers={"X-Converter-Request": "1"},
            json={"repository_url": "invalid", "github_token": "do-not-echo"},
        )
        assert result.status_code == 422 and "do-not-echo" not in result.text
        result = client.post(
            "/api/jobs",
            headers={"X-Converter-Request": "1"},
            json={
                "repository_url": "https://github.com/owner/repo",
                "github_token": "do-not-echo",
                "aws_env": "AWS_SECRET_ACCESS_KEY=not-persisted",
            },
        )
        assert result.status_code == 202 and "do-not-echo" not in result.text
        secret = client.app.state.store.secrets(result.json()["id"])
        assert "not-persisted" not in json.dumps(secret)


def test_env_download_serialization_rejects_injection():
    with pytest.raises(SafeError):
        env_text({"region": "x\nEVIL=value"})
    assert "CLOUD_PROVIDER='oci'" in env_text({})
