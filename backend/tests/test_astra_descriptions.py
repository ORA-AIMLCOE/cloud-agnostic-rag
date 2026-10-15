import json
from unittest.mock import MagicMock
import pytest
from app.astra import Astra, DESCRIPTION_SYSTEM
from app.security import SafeError
from app.settings import Settings

REPORT = [
    {"path": ".env.oci.example", "kind": "added", "diff": "@@ -0,0 +1 @@\n+OCI_REGION='<region>'", "reason": "OLD TEMPLATE"},
    {"path": "backend/app/core/config.py", "kind": "modified", "diff": "@@ -1 +1 @@\n-old\n+new"},
]

def model(monkeypatch, result):
    astra = Astra(Settings(_env_file=None))
    request = MagicMock(return_value=(json.dumps(result), {"total_tokens": 12}))
    monkeypatch.setattr(astra, "_request", request)
    return astra, request


def test_summaries_cover_every_final_diff_and_exclude_unrelated_data(monkeypatch):
    result = {"files": [{"path": entry["path"], "description": "Added OCI region configuration for the application."} for entry in REPORT]}
    astra, request = model(monkeypatch, result)
    descriptions, usage = astra.describe_changes(REPORT)
    assert set(descriptions) == {entry["path"] for entry in REPORT}
    context, instructions = request.call_args.args
    assert instructions == DESCRIPTION_SYSTEM
    assert context == {"files": [{key: entry[key] for key in ("path", "kind", "diff")} for entry in REPORT]}
    assert "OLD TEMPLATE" not in json.dumps(context)
    assert usage == {"total_tokens": 12}


@pytest.mark.parametrize("result", [
    {"files": []},
    {"files": [{"path": ".env.oci.example", "description": "Added OCI region configuration."}]},
    {"files": [{"path": "other.py", "description": "Added OCI region configuration."}]},
    {"files": [{"path": ".env.oci.example", "description": "Added OCI region configuration."}] * 2},
    {"files": [{"path": [], "description": "Added OCI region configuration."}]},
    {"files": [{"path": ".env.oci.example", "content": "execute code"}]},
    {"files": [{"path": ".env.oci.example", "description": None}]},
    {"files": [{"path": ".env.oci.example", "description": "x" * 1201}]},
    {"files": [{"path": ".env.oci.example", "description": "OCI_DB_PASSWORD=private-password"}]},
    {"files": [{"path": ".env.oci.example", "description": "Added OCI configuration.\nRun instructions."}]},
    {"files": "invalid"},
])
def test_invalid_or_partial_summaries_are_rejected(monkeypatch, result):
    astra, _ = model(monkeypatch, result)
    with pytest.raises(SafeError, match="summary for every changed file"):
        astra.describe_changes(REPORT)


def test_diff_credentials_block_model_request(monkeypatch):
    astra, request = model(monkeypatch, {"files": []})
    with pytest.raises(SafeError, match="credentials"):
        astra.describe_changes([{"path": ".env", "kind": "added", "diff": "+AWS_SECRET_ACCESS_KEY=private-value"}])
    request.assert_not_called()


def test_empty_report_needs_no_model_call(monkeypatch):
    astra, request = model(monkeypatch, {"files": []})
    assert astra.describe_changes([]) == ({}, {})
    request.assert_not_called()
