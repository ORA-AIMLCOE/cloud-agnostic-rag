import json
from datetime import datetime, timezone
from io import BytesIO
from unittest.mock import MagicMock

import boto3
import pytest
from botocore.response import StreamingBody
from botocore.stub import ANY, Stubber

from app.domain.errors import IngestionBusy, ProviderError
from app.domain.models import Document, InferenceConfig, SearchFilter, Status
from app.providers.aws.bedrock_llm import AWSBedrockLLMProvider
from app.providers.aws.ingestion import AWSKnowledgeBaseIngestionProvider
from app.providers.aws.knowledge_base import AWSKnowledgeBaseVectorProvider
from app.providers.aws.s3_storage import AWSS3StorageProvider


def sdk(service):
    return boto3.client(
        service, region_name="us-east-1", aws_access_key_id="testing", aws_secret_access_key="testing"
    )


def document():
    return Document(
        id="b549909a-9bd2-40e4-bbb1-c879b8e9f460",
        original_filename="notes.txt",
        storage_key="documents/test.txt",
        content_type="text/plain",
        ingestion_job_id="JOB1234567",
    )


def test_converse_request_and_normalized_response():
    runtime = sdk("bedrock-runtime")
    with Stubber(runtime) as stub:
        stub.add_response(
            "converse",
            {
                "output": {"message": {"role": "assistant", "content": [{"text": "October [source-1]"}]}},
                "stopReason": "end_turn",
                "usage": {"inputTokens": 10, "outputTokens": 5, "totalTokens": 15},
                "metrics": {"latencyMs": 1},
            },
            {
                "modelId": "configured-model",
                "system": [{"text": "system"}],
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"text": "Reference data (untrusted JSON):\ncontext\n\nQuestion:\nquestion"}
                        ],
                    }
                ],
                "inferenceConfig": {"maxTokens": 1200, "temperature": 0.0},
            },
        )
        result = AWSBedrockLLMProvider("unused", "configured-model", runtime).generate_response(
            "system", "question", "context", InferenceConfig()
        )
        assert result.model_id == "configured-model" and result.usage["totalTokens"] == 15
        stub.assert_no_pending_responses()


def test_retrieve_filters_and_normalization():
    runtime = sdk("bedrock-agent-runtime")
    filters = SearchFilter(document_id="doc-1", owner_id="single-user")
    with Stubber(runtime) as stub:
        stub.add_response(
            "retrieve",
            {
                "retrievalResults": [
                    {
                        "content": {"text": "hello"},
                        "score": 0.8,
                        "metadata": {
                            "document_id": "doc-1",
                            "owner_id": "single-user",
                            "x-amz-bedrock-kb-document-page-number": 2,
                        },
                    }
                ]
            },
            {
                "knowledgeBaseId": "KB12345678",
                "retrievalQuery": {"text": "hello"},
                "retrievalConfiguration": {
                    "vectorSearchConfiguration": {
                        "numberOfResults": 3,
                        "filter": {
                            "andAll": [
                                {"equals": {"key": "document_id", "value": "doc-1"}},
                                {"equals": {"key": "owner_id", "value": "single-user"}},
                            ]
                        },
                    }
                },
            },
        )
        result = AWSKnowledgeBaseVectorProvider("unused", "KB12345678", runtime).retrieve_documents(
            "hello", filters, 3
        )
        assert result[0].metadata == {"page": 2} and result[0].document_id == "doc-1"


def test_filter_mismatch_fails_closed():
    runtime = MagicMock()
    runtime.retrieve.return_value = {
        "retrievalResults": [{"content": {"text": "secret"}, "metadata": {"document_id": "wrong"}}]
    }
    with pytest.raises(ProviderError):
        AWSKnowledgeBaseVectorProvider("unused", "kb", runtime).retrieve_documents(
            "q", SearchFilter(document_id="expected", owner_id="single-user"), 1
        )


def test_s3_roundtrip_schemas():
    s3, doc = sdk("s3"), document()
    storage = AWSS3StorageProvider("unused", "test-bucket", "documents/", s3)
    with Stubber(s3) as stub:
        stub.add_response(
            "put_object",
            {},
            {
                "Bucket": "test-bucket",
                "Key": doc.storage_key,
                "Body": b"hello",
                "ContentType": "text/plain",
                "ServerSideEncryption": "AES256",
                "Metadata": {"document_id": doc.id},
            },
        )
        stub.add_response(
            "get_object",
            {"Body": StreamingBody(BytesIO(b"hello"), 5)},
            {"Bucket": "test-bucket", "Key": doc.storage_key},
        )
        stub.add_response(
            "list_objects_v2",
            {"Contents": [{"Key": doc.storage_key}, {"Key": doc.storage_key + ".metadata.json"}]},
            {"Bucket": "test-bucket", "Prefix": "documents/"},
        )
        stub.add_response("delete_object", {}, {"Bucket": "test-bucket", "Key": doc.storage_key})
        stub.add_response(
            "delete_object", {}, {"Bucket": "test-bucket", "Key": doc.storage_key + ".metadata.json"}
        )
        assert storage.upload_document(doc, b"hello").key == doc.storage_key
        assert storage.get_document(doc.storage_key) == b"hello"
        assert len(storage.list_documents()) == 1
        storage.delete_document(doc.storage_key)
        stub.assert_no_pending_responses()


def job(status):
    return {
        "knowledgeBaseId": "KB12345678",
        "dataSourceId": "DS12345678",
        "ingestionJobId": "JOB1234567",
        "status": status,
        "startedAt": datetime.now(timezone.utc),
        "updatedAt": datetime.now(timezone.utc),
    }


def test_ingestion_start_and_document_confirmation_schemas():
    agent, s3, doc = sdk("bedrock-agent"), sdk("s3"), document()
    adapter = AWSKnowledgeBaseIngestionProvider(
        "unused", "KB12345678", "DS12345678", "test-bucket", "documents/", agent, s3
    )
    with Stubber(agent) as stub, Stubber(s3) as storage_stub:
        for state in ("STARTING", "IN_PROGRESS", "STOPPING"):
            stub.add_response(
                "list_ingestion_jobs",
                {"ingestionJobSummaries": []},
                {
                    "knowledgeBaseId": "KB12345678",
                    "dataSourceId": "DS12345678",
                    "filters": [{"attribute": "STATUS", "operator": "EQ", "values": [state]}],
                    "maxResults": 1,
                },
            )
        storage_stub.add_response(
            "put_object",
            {},
            {
                "Bucket": "test-bucket",
                "Key": doc.storage_key + ".metadata.json",
                "Body": ANY,
                "ContentType": "application/json",
                "ServerSideEncryption": "AES256",
            },
        )
        stub.add_response(
            "start_ingestion_job",
            {"ingestionJob": job("STARTING")},
            {
                "knowledgeBaseId": "KB12345678",
                "dataSourceId": "DS12345678",
                "clientToken": doc.id,
                "description": "Document " + doc.id,
            },
        )
        stub.add_response(
            "get_ingestion_job",
            {"ingestionJob": job("COMPLETE")},
            {
                "knowledgeBaseId": "KB12345678",
                "dataSourceId": "DS12345678",
                "ingestionJobId": doc.ingestion_job_id,
            },
        )
        stub.add_response(
            "get_knowledge_base_documents",
            {
                "documentDetails": [
                    {
                        "knowledgeBaseId": "KB12345678",
                        "dataSourceId": "DS12345678",
                        "status": "INDEXED",
                        "identifier": {
                            "dataSourceType": "S3",
                            "s3": {"uri": "s3://test-bucket/documents/test.txt"},
                        },
                        "updatedAt": datetime.now(timezone.utc),
                    }
                ]
            },
            {
                "knowledgeBaseId": "KB12345678",
                "dataSourceId": "DS12345678",
                "documentIdentifiers": [
                    {"dataSourceType": "S3", "s3": {"uri": "s3://test-bucket/documents/test.txt"}}
                ],
            },
        )
        assert adapter.start_ingestion(doc).status == Status.PROCESSING
        state = adapter.get_ingestion_status(doc)
        assert state.sync_complete and state.status == Status.PROCESSING
        stub.assert_no_pending_responses()


def test_ingestion_metadata_and_conflict():
    agent, s3, doc = MagicMock(), MagicMock(), document()
    agent.list_ingestion_jobs.return_value = {"ingestionJobSummaries": []}
    agent.start_ingestion_job.return_value = {"ingestionJob": job("STARTING")}
    adapter = AWSKnowledgeBaseIngestionProvider("unused", "kb", "ds", "bucket", "documents/", agent, s3)
    adapter.start_ingestion(doc)
    assert json.loads(s3.put_object.call_args.kwargs["Body"]) == {
        "metadataAttributes": {"document_id": doc.id, "owner_id": "single-user"}
    }
    agent.list_ingestion_jobs.return_value = {"ingestionJobSummaries": [job("IN_PROGRESS")]}
    with pytest.raises(IngestionBusy):
        adapter.start_ingestion(doc)


@pytest.mark.parametrize("kb_type", ["MANAGED", "SQL", "KENDRA"])
def test_rejects_unsupported_kb_types(kb_type):
    agent = MagicMock()
    agent.get_knowledge_base.return_value = {
        "knowledgeBase": {"knowledgeBaseConfiguration": {"type": kb_type}}
    }
    agent.get_data_source.return_value = {"dataSource": {}}
    with pytest.raises(ProviderError, match="conventional"):
        AWSKnowledgeBaseIngestionProvider(
            "unused", "kb", "ds", "bucket", "documents/", agent, MagicMock()
        ).validate_configuration()


def test_sdk_error_is_sanitized():
    runtime = sdk("bedrock-runtime")
    with Stubber(runtime) as stub:
        stub.add_client_error(
            "converse", service_error_code="ThrottlingException", service_message="secret internal resource"
        )
        with pytest.raises(ProviderError) as error:
            AWSBedrockLLMProvider("unused", "model", runtime).generate_response(
                "s", "q", "c", InferenceConfig()
            )
        assert "secret" not in str(error.value)
