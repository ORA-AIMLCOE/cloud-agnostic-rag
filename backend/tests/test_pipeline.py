import json
from pathlib import Path
import pytest
from app.settings import Settings
from app.store import Store
from app.worker import Worker


class FakeGitHub:
    published = []
    prepared = []

    def __init__(self, *args):
        pass

    def snapshot(self, branch):
        return "source-sha", "tree-sha", {"README.md": b"original"}

    def prepare_commit(self, sha, tree, changes):
        self.prepared.append((sha, tree, changes))
        return "new-commit"

    def publish(self, branch, commit):
        self.published.append((branch, commit))
        return "https://github.com/owner/repo/tree/" + branch

    def close(self):
        pass


class FakeAstra:
    def __init__(self, settings):
        pass

    def describe_changes(self, report):
        assert "private-db-secret" not in json.dumps(report)
        assert report[0]["diff"].endswith("+class OCIStorageProvider: pass")
        return {entry["path"]: "Added the OCIStorageProvider class for object storage integration." for entry in report}, {"total_tokens": 10}

    def refine(self, context):
        assert "private-db-secret" not in json.dumps(context)
        return {"files": [], "summary": "Review complete"}, {"input_tokens": 5}


@pytest.mark.parametrize("passes", [True, False])
def test_pipeline_only_publishes_after_success(monkeypatch, tmp_path, passes):
    FakeGitHub.published, FakeGitHub.prepared = [], []
    config = Settings(
        _env_file=None, state_dir=tmp_path / "state", workspace_dir=tmp_path / "work", astra_max_attempts=1
    )
    store = Store(config.state_dir)
    identifier = store.create(
        {"repository_url": "https://github.com/owner/repo", "source_branch": "main"},
        {"github_token": "private"},
    )
    monkeypatch.setattr("app.worker.inspect_source", lambda files: {"protected_files": 15})
    monkeypatch.setattr(
        "app.worker.generate_recipe",
        lambda files: {"backend/app/providers/oci/storage.py": "class OCIStorageProvider: pass"},
    )
    monkeypatch.setattr("app.worker.model_context", lambda *args: {"implementation": "safe"})
    worker = Worker(
        store,
        config,
        FakeGitHub,
        FakeAstra,
        lambda *args: (passes, "Tests passed" if passes else "Tests failed"),
    )
    worker.process(identifier, "queued_inspection")
    assert store.get(identifier)["status"] == "ready"
    payload = store.secrets(identifier)
    payload.update(target={"db_password": "private-db-secret"}, publish=True)
    store.queue_conversion(identifier, payload)
    worker.process(identifier, "queued")
    job = store.get(identifier)
    assert job["status"] == ("completed" if passes else "failed")
    assert bool(FakeGitHub.published) == passes
    assert "private-db-secret" not in json.dumps(job)
    assert job["checks"][-1]["status"] == "not_run"
    if passes:
        assert all(entry["reason_source"] == "astra" for entry in job["files"])
        assert job["files"][0]["reason"].startswith("Added the OCIStorageProvider")
        assert job["description_usage"] == {"total_tokens": 10}
        assert FakeGitHub.prepared[0][:2] == ("source-sha", "tree-sha")
        assert FakeGitHub.published[0][0].startswith("migration/oci-")


def test_cancelled_job_never_calls_model_or_publishes(tmp_path):
    FakeGitHub.published = []
    config = Settings(_env_file=None, state_dir=tmp_path / "state", workspace_dir=tmp_path / "work")
    store = Store(config.state_dir)
    identifier = store.create(
        {"repository_url": "https://github.com/owner/repo", "source_branch": "main"},
        {"github_token": "private"},
    )
    store.cancel(identifier)
    worker = Worker(store, config, FakeGitHub, FakeAstra)
    worker.process(identifier, "queued")
    assert store.get(identifier)["status"] == "cancelled"
    assert not FakeGitHub.published


def test_summary_failure_does_not_publish(monkeypatch, tmp_path):
    from app.security import SafeError
    def fail_summary(self, report):
        raise SafeError("Astra did not return a valid development summary for every changed file.")
    monkeypatch.setattr(FakeAstra, "describe_changes", fail_summary)
    FakeGitHub.published, FakeGitHub.prepared = [], []
    config = Settings(_env_file=None, state_dir=tmp_path / "state", workspace_dir=tmp_path / "work")
    store = Store(config.state_dir)
    identifier = store.create({"repository_url": "https://github.com/owner/repo", "source_branch": "main"}, {"github_token": "private"})
    monkeypatch.setattr("app.worker.inspect_source", lambda files: {"protected_files": 15})
    monkeypatch.setattr("app.worker.generate_recipe", lambda files: {"backend/app/providers/oci/storage.py": "class OCIStorageProvider: pass"})
    monkeypatch.setattr("app.worker.model_context", lambda *args: {"implementation": "safe"})
    worker = Worker(store, config, FakeGitHub, FakeAstra, lambda *args: (True, "Passed"))
    worker.process(identifier, "queued_inspection")
    store.queue_conversion(identifier, {"github_token": "private", "target": {}, "publish": True})
    worker.process(identifier, "queued")
    assert store.get(identifier)["status"] == "failed"
    assert not FakeGitHub.prepared and not FakeGitHub.published
