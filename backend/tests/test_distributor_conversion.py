import io
import json
import zipfile

import pytest
from dotenv import dotenv_values
from fastapi.testclient import TestClient

from app.main import create_app
from app.recipe import DISTRIBUTOR_REQUIRED, REQUIRED, env_text, inspect_source, model_context
from app.security import SafeError, has_secret, parse_aws_env
from app.settings import Settings
from test_oracle_target import target_values


def source_files(distributor=True):
    files = {name: b"" for name in REQUIRED}
    files["backend/app/providers/factory.py"] = b'if settings.cloud_provider == "oci": # extension points'
    files["frontend/package.json"] = b'{"dependencies":{"react":"19"}}'
    if distributor:
        files.update({name: b"" for name in DISTRIBUTOR_REQUIRED})
        files["backend/app/interfaces/repository.py"] = (
            b"def get_release_by_hash(): pass\ndef register_release(): pass\n"
            b"def get_active_release(): pass\ndef activate_release(): pass")
        files["backend/app/database/models.py"] = b"class KnowledgeReleaseRow(Base): pass\nclass ActiveKnowledgeRow(Base): pass"
    return files


def test_detects_distributor_contract_and_preserves_classic_support():
    assert inspect_source(source_files())["integration_api"]
    assert inspect_source(source_files())["application"] == "distributor_aggregator"
    assert not inspect_source(source_files(False))["prepared_knowledge"]
    incomplete = source_files()
    del incomplete["backend/app/admin.py"]
    with pytest.raises(SafeError, match="Incomplete Distributor"):
        inspect_source(incomplete)
    incomplete = source_files()
    incomplete["backend/app/database/models.py"] = b"class DocumentRow(Base): pass"
    with pytest.raises(SafeError, match="schema is incomplete"):
        inspect_source(incomplete)


def test_integration_key_is_generated_privately_and_never_sent_to_model(tmp_path):
    config = Settings(_env_file=None, state_dir=tmp_path / "state", workspace_dir=tmp_path / "work",
        astra_base_url="https://inference.generativeai.us-chicago-1.oci.oraclecloud.com",
        astra_model_id="model", astra_compartment_id="compartment")
    headers = {"X-Converter-Request": "1"}
    with TestClient(create_app(config, start_worker=False)) as client:
        store = client.app.state.store
        keys = []
        for _ in range(2):
            identifier = store.create({"analysis": {"integration_api": True}, "publish_allowed": True},
                                      {"github_token": "test-token"})
            store.update(identifier, status="ready")
            response = client.post(f"/api/jobs/{identifier}/convert", headers=headers,
                json={"target": target_values(), "publish": False, "acknowledge_source_transfer": True})
            assert response.status_code == 202
            target = store.secrets(identifier)["target"]
            key = target["integration_api_key"]
            keys.append(key)
            assert len(key) >= 40 and key not in response.text
            assert key.encode() not in (config.state_dir / "jobs.sqlite3").read_bytes()
            assert key not in json.dumps(model_context(source_files(), {}, target))
            assert key not in env_text(target, placeholders=True)
            preview = client.get(f"/api/jobs/{identifier}/environment", headers=headers).json()
            assert key not in json.dumps(preview)
            assert "INTEGRATION_API_KEYS" in preview["masked"]
            assert json.loads(preview["oci"]["INTEGRATION_API_KEYS"]) == {"cloudshift-client": "[REDACTED]"}
            store.update(identifier, status="completed")
            download = client.get(f"/api/jobs/{identifier}/configuration", headers=headers)
            with zipfile.ZipFile(io.BytesIO(download.content)) as archive:
                values = dotenv_values(stream=io.StringIO(archive.read(".env").decode()), interpolate=False)
            assert values["DISTRIBUTOR_MODE"] == "true"
            assert json.loads(values["INTEGRATION_API_KEYS"]) == {"cloudshift-client": key}
        assert keys[0] != keys[1]


def test_source_integration_keys_are_not_imported_or_committed():
    assert parse_aws_env('INTEGRATION_API_KEYS={"client":"source-key"}')[0] == {}
    assert has_secret('INTEGRATION_API_KEYS={"client":"a-real-runtime-secret"}')
    assert not has_secret('INTEGRATION_API_KEYS={}')
    assert not has_secret('INTEGRATION_API_KEYS={"client":"REPLACE_WITH_A_RANDOM_SECRET"}')
    assert not has_secret(env_text({"distributor_mode": True}, placeholders=True))
