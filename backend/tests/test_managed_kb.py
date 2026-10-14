import json
from unittest.mock import MagicMock

import pytest

from app.domain.errors import ProviderError
from app.domain.models import SearchFilter
from app.providers.aws.ingestion import AWSKnowledgeBaseIngestionProvider
from app.providers.aws.knowledge_base import AWSKnowledgeBaseVectorProvider


@pytest.mark.parametrize("serialized", [True, False])
def test_managed_connector_validates_bucket_and_prefix(serialized):
    agent = MagicMock()
    agent.get_knowledge_base.return_value = {
        "knowledgeBase": {"status": "ACTIVE", "knowledgeBaseConfiguration": {"type": "MANAGED"}}
    }
    connector = {
        "type": "S3",
        "connectionConfiguration": {"bucketName": "test-bucket"},
        "filterConfiguration": {"inclusionPrefixes": ["documents/"]},
    }
    config = {"connectorParameters": json.dumps(connector) if serialized else connector}
    agent.get_data_source.return_value = {
        "dataSource": {
            "status": "AVAILABLE",
            "dataSourceConfiguration": {
                "type": "MANAGED_KNOWLEDGE_BASE_CONNECTOR",
                "managedKnowledgeBaseConnectorConfiguration": config,
            },
        }
    }
    provider = AWSKnowledgeBaseIngestionProvider(
        "unused", "kb", "ds", "test-bucket", "documents/", agent, MagicMock(), mode="managed"
    )
    provider.validate_configuration()
    provider.bucket = "wrong-bucket"
    with pytest.raises(ProviderError, match="bucket and prefix"):
        provider.validate_configuration()


def test_managed_retrieval_disables_reranking_and_preserves_filters():
    runtime = MagicMock()
    runtime.retrieve.return_value = {"retrievalResults": []}
    provider = AWSKnowledgeBaseVectorProvider("unused", "kb", runtime, mode="managed")
    provider.retrieve_documents("question", SearchFilter(document_id="doc", owner_id="owner"), 3)
    config = runtime.retrieve.call_args.kwargs["retrievalConfiguration"]
    assert config == {
        "managedSearchConfiguration": {
            "numberOfResults": 3,
            "rerankingModelType": "NONE",
            "filter": {
                "andAll": [
                    {"equals": {"key": "document_id", "value": "doc"}},
                    {"equals": {"key": "owner_id", "value": "owner"}},
                ]
            },
        }
    }
