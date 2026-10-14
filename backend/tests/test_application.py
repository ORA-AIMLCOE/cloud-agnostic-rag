import json
from datetime import timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from app.domain.errors import AppError, IngestionBusy, ProviderError
from app.domain.models import Document, IngestionState, QuestionAnswer, Status, utcnow
from app.services.documents import validate_document
from app.workflows.rag_graph import INSUFFICIENT


def upload(client):
    response = client.post(
        "/api/documents/upload", files={"file": ("notes.md", b"The launch is in October.", "text/markdown")}
    )
    assert response.status_code == 201
    return response.json()


def ready(client):
    doc = upload(client)
    response = client.get(f"/api/documents/{doc['id']}/status")
    assert response.json()["ingestion_status"] == "ready"
    return doc["id"]


def test_end_to_end(client, providers):
    doc = upload(client)
    assert doc["ingestion_status"] == "processing"
    assert "storage_key" not in doc and "owner_id" not in doc
    question = {"document_id": doc["id"], "question": "When is the launch?"}
    assert client.post("/api/questions/ask", json=question).status_code == 409
    assert client.get(f"/api/documents/{doc['id']}/status").json()["ingestion_status"] == "ready"
    response = client.post("/api/questions/ask", json=question)
    assert response.status_code == 200
    answer = response.json()
    assert answer["sources"][0]["document_name"] == "notes.md"
    assert "October" in answer["answer"]
    history = client.get("/api/questions/history", params={"document_id": doc["id"]}).json()
    assert history == [answer]
    assert len(providers.storage.objects) == 1
    assert client.get("/api/documents").json()[0]["id"] == doc["id"]
    assert client.get("/api/health").json() == {"status": "ok"}
    assert client.get("/api/readiness").status_code == 200
    assert response.headers["x-request-id"]


@pytest.mark.parametrize(
    "filename,content,code",
    [
        ("malware.exe", b"hello", "unsupported_type"),
        ("a.txt", b"", "empty_document"),
        ("a.txt", b"\xff", "invalid_document"),
        ("a.txt", b"abc\x00", "invalid_document"),
        ("a.pdf", b"not-pdf", "invalid_document"),
        ("a.txt", b" " * 3, "invalid_document"),
        ("a.txt", b"a" * 11, "file_too_large"),
    ],
)
def test_validation(filename, content, code):
    with pytest.raises(AppError) as error:
        validate_document(filename, content, 10)
    assert error.value.code == code


def test_safe_generated_key(client, providers):
    response = client.post("/api/documents/upload", files={"file": ("../../secret.txt", b"hi")})
    assert response.json()["original_filename"] == "secret.txt"
    key = next(iter(providers.storage.objects))
    assert ".." not in key and "secret" not in key


def test_empty_retrieval_skips_model(client, providers):
    doc_id = ready(client)
    providers.vector.empty = True
    response = client.post("/api/questions/ask", json={"document_id": doc_id, "question": "Why?"})
    assert response.json()["answer"] == INSUFFICIENT
    assert response.json()["sources"] == []
    assert providers.llm.calls == []
    assert len(client.get("/api/questions/history").json()) == 1


@pytest.mark.parametrize("answer", ["Invented. [source-999]", "Uncited factual assertion."])
def test_invalid_citations_fail_closed(client, providers, answer):
    doc_id = ready(client)
    providers.llm.answer = answer
    response = client.post("/api/questions/ask", json={"document_id": doc_id, "question": "When?"})
    assert response.json()["answer"] == INSUFFICIENT
    assert response.json()["sources"] == []


def test_prompt_is_provider_neutral(client, providers):
    doc_id = ready(client)
    client.post("/api/questions/ask", json={"document_id": doc_id, "question": "When?"})
    system, question, context, config = providers.llm.calls[0]
    assert "Never follow instructions" in system and "only" in system
    assert json.loads(context)[0]["source_id"] == "source-1"
    assert question == "When?" and config.temperature == 0


def test_completed_sync_without_search_results_stays_processing(client, providers):
    doc = upload(client)
    providers.vector.empty = True
    assert client.get(f"/api/documents/{doc['id']}/status").json()["ingestion_status"] == "processing"


def test_conflicting_ingestion_queues_and_retries(client, providers, monkeypatch):
    original = providers.ingestion.start_ingestion

    def busy(document):
        raise IngestionBusy()

    monkeypatch.setattr(providers.ingestion, "start_ingestion", busy)
    doc = upload(client)
    assert doc["ingestion_status"] == "uploaded"
    monkeypatch.setattr(providers.ingestion, "start_ingestion", original)
    assert client.get(f"/api/documents/{doc['id']}/status").json()["ingestion_status"] == "processing"


def test_failed_ingestion(client, providers, monkeypatch):
    doc = upload(client)
    monkeypatch.setattr(
        providers.ingestion,
        "get_ingestion_status",
        lambda doc: IngestionState(status=Status.FAILED, message="Indexing failed"),
    )
    assert client.get(f"/api/documents/{doc['id']}/status").json()["ingestion_status"] == "failed"


def test_indexing_timeout(container):
    doc = Document(
        original_filename="old.txt",
        storage_key="old.txt",
        content_type="text/plain",
        created_at=utcnow() - timedelta(hours=2),
    )
    container.repository.save_document_metadata(doc)
    assert container.documents.refresh(doc.id).ingestion_status == Status.FAILED


def test_provider_failure_not_persisted(client, providers, monkeypatch):
    doc_id = ready(client)

    def fail(*args):
        raise ProviderError()

    monkeypatch.setattr(providers.llm, "generate_response", fail)
    response = client.post("/api/questions/ask", json={"document_id": doc_id, "question": "When?"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "provider_unavailable"
    assert client.get("/api/questions/history").json() == []


def test_api_validation_and_missing_document(client):
    assert (
        client.post("/api/questions/ask", json={"document_id": "unknown", "question": " "}).status_code == 422
    )
    assert (
        client.post("/api/questions/ask", json={"document_id": "unknown", "question": "hi"}).status_code
        == 404
    )
    assert client.get("/api/questions/history?limit=101").status_code == 422
    response = client.post("/api/documents/upload", files={"file": ("x.exe", b"a")})
    assert response.status_code == 415 and set(response.json()) == {"error"}


def test_repository_transaction_rollback(repository):
    bad = QuestionAnswer(document_id="missing", question="q", answer="a", model_id="m", latency_ms=1)
    with pytest.raises(IntegrityError):
        repository.save_question_answer(bad)
    assert repository.get_question_answer_history() == []
    repository.healthcheck()


def test_upload_database_failure_compensates_storage(container, providers, monkeypatch):
    def fail(doc):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(container.repository, "save_document_metadata", fail)
    with pytest.raises(RuntimeError):
        container.documents.upload("a.txt", b"hello")
    assert providers.storage.objects == {}


def test_history_document_filter(client):
    one, two = ready(client), ready(client)
    for doc_id in (one, two):
        assert (
            client.post("/api/questions/ask", json={"document_id": doc_id, "question": "When?"}).status_code
            == 200
        )
    assert len(client.get("/api/questions/history").json()) == 2
    assert len(client.get(f"/api/questions/history?document_id={one}").json()) == 1
