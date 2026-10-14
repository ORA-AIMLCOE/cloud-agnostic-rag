"""These tests use real infrastructure only with --run-integration. See docs/testing.md."""

import os
import time
from uuid import uuid4

import boto3
import httpx
import pytest
from sqlalchemy import text

from app.core.config import Settings
from app.database.session import create_database
from app.providers.factory import create_providers

pytestmark = pytest.mark.integration


def test_aws_end_to_end():
    base_url = os.getenv("INTEGRATION_BASE_URL")
    if not base_url:
        pytest.skip("Set INTEGRATION_BASE_URL to the running backend (for example http://localhost:8000).")
    settings = Settings()
    providers = create_providers(settings)
    marker = str(uuid4())
    content = f"The integration project {marker} launches in October. Its codeword is periwinkle.".encode()
    with httpx.Client(base_url=base_url, timeout=240) as client:
        assert client.get("/api/readiness").status_code == 200
        response = client.post(
            "/api/documents/upload", files={"file": (f"integration-{marker}.txt", content, "text/plain")}
        )
        response.raise_for_status()
        doc = response.json()
        key = settings.aws_s3_prefix + doc["id"] + ".txt"
        assert providers.storage.get_document(key) == content
        deadline = time.monotonic() + 900
        while doc["ingestion_status"] not in {"ready", "failed"} and time.monotonic() < deadline:
            time.sleep(10)
            status = client.get(f"/api/documents/{doc['id']}/status")
            status.raise_for_status()
            doc = status.json()
        assert doc["ingestion_status"] == "ready", doc
        response = client.post(
            "/api/questions/ask",
            json={"document_id": doc["id"], "question": "What is the launch month and codeword?"},
        )
        response.raise_for_status()
        answer = response.json()
        assert answer["sources"] and "periwinkle" in answer["answer"].lower()
        history = client.get("/api/questions/history", params={"document_id": doc["id"]}).json()
        assert history[0]["id"] == answer["id"]
        # Keep fixture objects and history for inspection; cleanup is documented, not hidden destructive SQL.


def test_postgresql_persistence():
    url = os.getenv("INTEGRATION_DATABASE_URL")
    if not url:
        pytest.skip("Set INTEGRATION_DATABASE_URL to an isolated, migrated PostgreSQL database.")
    engine, _ = create_database(url)
    try:
        assert engine.dialect.name == "postgresql"
        with engine.connect() as connection:
            transaction = connection.begin()
            doc_id, answer_id = str(uuid4()), str(uuid4())
            connection.execute(
                text(
                    "INSERT INTO documents (id, owner_id, original_filename, storage_key, content_type, ingestion_status, status_message, created_at, updated_at) VALUES (:id, 'single-user', 'test.txt', :key, 'text/plain', 'ready', 'test', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ),
                {"id": doc_id, "key": doc_id},
            )
            connection.execute(
                text(
                    "INSERT INTO question_answers (id, document_id, question, answer, source_references, model_id, latency_ms, created_at) VALUES (:id, :doc, 'q', 'a', '[]', 'test', 1, CURRENT_TIMESTAMP)"
                ),
                {"id": answer_id, "doc": doc_id},
            )
            assert (
                connection.execute(
                    text("SELECT answer FROM question_answers WHERE id = :id"), {"id": answer_id}
                ).scalar_one()
                == "a"
            )
            transaction.rollback()
    finally:
        engine.dispose()


def test_cloudwatch_shipping():
    group, base_url = os.getenv("INTEGRATION_LOG_GROUP"), os.getenv("INTEGRATION_BASE_URL")
    if not group or not base_url:
        pytest.skip("Set INTEGRATION_LOG_GROUP and INTEGRATION_BASE_URL for a deployed, log-shipped backend.")
    start_ms = int(time.time() * 1000)
    response = httpx.get(base_url + "/api/health", timeout=30)
    response.raise_for_status()
    request_id = response.headers["x-request-id"]
    logs = boto3.client("logs", region_name=Settings().aws_region)
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        result = logs.filter_log_events(
            logGroupName=group, startTime=start_ms, filterPattern='{ $.request_id = "' + request_id + '" }'
        )
        if result.get("events"):
            return
        time.sleep(5)
    pytest.fail("The request's JSON log did not arrive in CloudWatch within 120 seconds.")
