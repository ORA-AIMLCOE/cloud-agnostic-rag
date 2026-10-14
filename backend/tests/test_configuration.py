from pathlib import Path
from unittest.mock import MagicMock

from app.core.config import ROOT, Settings
from app.providers.factory import create_providers


def test_default_env_file_is_in_project_root():
    assert ROOT == Path(__file__).resolve().parents[2]
    assert Settings.model_config["env_file"] == ROOT / ".env"


def test_factory_uses_profile_loaded_from_env_file(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("AWS_PROFILE=limited-role\nAWS_KB_MODE=managed\n")
    settings = Settings(
        _env_file=env,
        aws_region="ap-southeast-2",
        aws_s3_bucket="test-bucket",
        aws_bedrock_model_id="test-model",
        aws_knowledge_base_id="KB12345678",
        aws_kb_data_source_id="DS12345678",
    )
    session = MagicMock()
    session_factory = MagicMock(return_value=session)
    monkeypatch.setattr("boto3.Session", session_factory)
    providers = create_providers(settings)
    session_factory.assert_called_once_with(profile_name="limited-role")
    assert providers.ingestion.mode == "managed"
    assert providers.vector.mode == "managed"
    assert providers.storage.s3 is providers.ingestion.s3
