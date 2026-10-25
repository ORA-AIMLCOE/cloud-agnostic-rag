import ast
import inspect
from pathlib import Path

import pytest

from app.core.config import Settings
from app.domain.models import (
    Document,
    Generation,
    InferenceConfig,
    IngestionState,
    SearchChunk,
    SearchFilter,
    StoredObject,
)
from app.interfaces.ingestion import DocumentIngestionProvider
from app.interfaces.llm import LLMProvider
from app.interfaces.storage import ObjectStorageProvider
from app.interfaces.vector_search import VectorSearchProvider
from app.providers.aws.bedrock_llm import AWSBedrockLLMProvider
from app.providers.aws.ingestion import AWSKnowledgeBaseIngestionProvider
from app.providers.aws.knowledge_base import AWSKnowledgeBaseVectorProvider
from app.providers.aws.s3_storage import AWSS3StorageProvider
from app.providers.factory import create_providers


@pytest.mark.parametrize(
    "port,adapter",
    [
        (LLMProvider, AWSBedrockLLMProvider),
        (ObjectStorageProvider, AWSS3StorageProvider),
        (VectorSearchProvider, AWSKnowledgeBaseVectorProvider),
        (DocumentIngestionProvider, AWSKnowledgeBaseIngestionProvider),
    ],
)
def test_adapter_signatures(port, adapter):
    for name, method in inspect.getmembers(port, inspect.isfunction):
        if name.startswith("_"):
            continue
        assert list(inspect.signature(method).parameters) == list(
            inspect.signature(getattr(adapter, name)).parameters
        )


def assert_provider_contract(providers):
    """Reusable behavior contract: supply future OCI providers in an explicitly enabled fixture."""
    doc = Document(original_filename="contract.txt", storage_key="contract.txt", content_type="text/plain")
    stored = providers.storage.upload_document(doc, b"The launch is in October.")
    assert isinstance(stored, StoredObject)
    assert providers.storage.get_document(stored.key) == b"The launch is in October."
    assert all(isinstance(item, StoredObject) for item in providers.storage.list_documents())
    state = providers.ingestion.start_ingestion(doc)
    assert isinstance(state, IngestionState)
    assert isinstance(providers.ingestion.get_ingestion_status(doc), IngestionState)
    chunks = providers.vector.retrieve_documents(
        "launch", SearchFilter(document_id=doc.id, owner_id=doc.owner_id), 1
    )
    assert all(isinstance(c, SearchChunk) and c.document_id == doc.id for c in chunks)
    assert isinstance(
        providers.llm.generate_response("Answer from context", "When?", "October", InferenceConfig()),
        Generation,
    )
    providers.storage.delete_document(stored.key)


def test_neutral_behavior_contract(providers):
    assert_provider_contract(providers)


def test_sdk_boundary():
    root = Path(__file__).parents[1] / "app"
    for folder in ("api", "domain", "services", "workflows", "interfaces", "repositories", "database"):
        for path in (root / folder).rglob("*.py"):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [x.name for x in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""]
                else:
                    continue
                assert not any(n.startswith(("boto3", "botocore", "oci", "app.providers")) for n in names), (
                    path
                )


def test_factory_oci_fails_explicitly():
    with pytest.raises(ValueError):
        create_providers(Settings(_env_file=None, cloud_provider="oci"))


def test_factory_aws_configuration_missing():
    with pytest.raises(ValueError, match="AWS_REGION"):
        create_providers(Settings(_env_file=None, aws_region="", aws_bedrock_model_id=""))


def test_factory_aws(monkeypatch):
    from unittest.mock import MagicMock

    monkeypatch.setattr("app.providers.aws.common.boto3.client", MagicMock())
    providers = create_providers(
        Settings(
            _env_file=None,
            aws_region="test-region",
            aws_bedrock_model_id="model",
            aws_s3_bucket="bucket",
            aws_knowledge_base_id="kb",
            aws_kb_data_source_id="ds",
        )
    )
    assert isinstance(providers.llm, AWSBedrockLLMProvider)
