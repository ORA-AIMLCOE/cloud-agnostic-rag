import hashlib

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.admin import ingest
from app.core.dependencies import build_container
from app.domain.errors import AppError
from app.domain.models import Document, KnowledgeRelease, QuestionAnswer, SearchChunk, Status
from app.main import create_app
from app.services.distributors import retrieval_queries


def release(repository, name="demo.md", status=Status.READY):
    doc = repository.save_document_metadata(Document(original_filename=name, storage_key=name,
        content_type="text/markdown", ingestion_status=status))
    repository.register_release(KnowledgeRelease(document_id=doc.id, version=name,
        content_sha256=hashlib.sha256(name.encode()).hexdigest(), demo_data=True))
    return doc


@pytest.fixture
def distributor(container, providers):
    container.settings.distributor_mode = True
    container.settings.integration_api_keys = {"test-client": SecretStr("integration-test-key")}
    return build_container(container.settings, providers, container.repository)


def test_active_source_isolation_and_upload_restriction(distributor):
    repo = distributor.repository
    old, active = release(repo, "personal.md"), release(repo)
    repo.activate_release(active.id)
    for doc in (old, active):
        repo.save_question_answer(QuestionAnswer(document_id=doc.id, question="q", answer="Fictional demo data (not actual company policies):\n\na", model_id="test", latency_ms=1))
    with TestClient(create_app(distributor.settings, distributor)) as client:
        assert client.get("/api/knowledge").json()["demo_data"] is True
        assert [d["id"] for d in client.get("/api/documents").json()] == [active.id]
        assert [a["document_id"] for a in client.get("/api/questions/history").json()] == [active.id]
        assert client.get("/api/questions/history").json()[0]["answer"] == "a"
        assert client.get(f"/api/questions/history?document_id={old.id}").status_code == 404
        assert client.get(f"/api/documents/{old.id}/status").status_code == 404
        assert client.post("/api/documents/upload", files={"file": ("other.txt", b"private")}).status_code == 403
        assert client.post("/api/questions/ask", json={"document_id": old.id, "question": "q"}).status_code == 400
        response = client.post("/api/questions/ask", json={"question": "What does Blue Dart offer?"})
        assert response.status_code == 200
        assert response.json()["document_id"] == active.id
        assert response.json()["demo_data"] is True


def test_integration_auth_contract_rate_and_validation(distributor):
    repo = distributor.repository
    repo.activate_release(release(repo).id)
    distributor.settings.integration_requests_per_minute = 2
    headers = {"Authorization": "Bearer integration-test-key"}
    with TestClient(create_app(distributor.settings, distributor)) as client:
        for auth in ({}, {"Authorization": "Bearer wrong"}):
            response = client.post("/api/v1/answers", headers=auth, json={"question": "BlueDart?"})
            assert response.status_code == 401
        assert client.post("/api/v1/answers", headers=headers, json={"question": " "}).status_code == 422
        assert client.post("/api/v1/answers", headers=headers, json={"question": "q", "document_id": "other"}).status_code == 422
        response = client.post("/api/v1/answers", headers=headers, json={"question": "Compare BlueDart and DTDC"})
        assert response.status_code == 200
        body = response.json()
        assert body["answer_status"] == "answered" and body["demo_data"]
        assert not body["answer"].startswith("Fictional demo data (not actual company policies):")
        history = client.get("/api/questions/history").json()
        assert history[0]["demo_data"] and history[0]["knowledge_version"] == "demo.md"
        assert body["knowledge_version"] == "demo.md"
        assert body["request_id"] == response.headers["x-request-id"]
        assert "integration-test-key" not in response.text
        distributor.providers.vector.empty = True
        body = client.post("/api/v1/answers", headers=headers, json={"question": "Unknown information"}).json()
        assert body["answer_status"] == "insufficient_information" and not body["sources"]
        response = client.post("/api/v1/answers", headers=headers, json={"question": "q"})
        assert response.status_code == 429 and response.headers["retry-after"] == "60"


def test_no_default_source_no_fallback_to_personal_document(distributor):
    release(distributor.repository, "personal.md")
    with TestClient(create_app(distributor.settings, distributor)) as client:
        assert client.get("/api/knowledge").json()["ready"] is False
        assert client.get("/api/readiness").status_code == 503
        assert client.post("/api/questions/ask", json={"question": "q"}).status_code == 503


def test_activation_requires_ready_and_supports_rollback(repository):
    first = release(repository)
    repository.activate_release(first.id)
    second = release(repository, "new.md", Status.PROCESSING)
    with pytest.raises(AppError):
        repository.activate_release(second.id)
    assert repository.get_active_release().document_id == first.id
    repository.update_document_status(second.id, Status.READY, "Ready")
    repository.activate_release(second.id)
    repository.activate_release(first.id)
    assert repository.get_active_release().document_id == first.id


def test_balanced_comparison_queries_and_context(distributor, monkeypatch):
    doc = release(distributor.repository)
    distributor.repository.activate_release(doc.id)
    calls = []
    def search(query, filters, top_k):
        name = query.split(":")[0]
        calls.append((name, filters.document_id))
        return [SearchChunk(source_id=name, document_id=filters.document_id, text=name + " offers demo delivery.")]
    monkeypatch.setattr(distributor.providers.vector, "retrieve_documents", search)
    with TestClient(create_app(distributor.settings, distributor)) as client:
        assert client.post("/api/questions/ask", json={"question": "Compare all distributors"}).status_code == 200
    assert [c[0] for c in calls] == ["BlueDart", "Delhivery", "Ekart", "DTDC"]
    assert all(c[1] == doc.id for c in calls)
    system, _, context, _ = distributor.providers.llm.calls[0]
    assert "fictional demo" in system
    assert all(name in context for name in ["BlueDart", "Delhivery", "Ekart", "DTDC"])
    assert retrieval_queries("Blue Dart returns")[0].startswith("BlueDart:")
    assert retrieval_queries("E-kart returns")[0].startswith("Ekart:")
    queries = retrieval_queries("Compare BlueDart and DTDC reverse pickup windows")
    assert "DTDC" not in queries[0] and "BlueDart" not in queries[1]
    assert all("reverse pickup windows" in query for query in queries)


def test_admin_ingestion_is_idempotent_and_validates_topics(distributor, tmp_path, monkeypatch):
    path = tmp_path / "demo.md"
    path.write_text("BlueDart Delhivery Ekart DTDC fictional demo.")
    def search(query, filters, top_k):
        return [SearchChunk(source_id="chunk", document_id=filters.document_id, text=path.read_text())]
    monkeypatch.setattr(distributor.providers.vector, "retrieve_documents", search)
    first = ingest(distributor, path, "v1", True, poll_seconds=0)
    second = ingest(distributor, path, "v1", True, poll_seconds=0)
    assert first == second
    assert len(distributor.providers.storage.objects) == 1
    assert distributor.repository.get_active_release().document_id == first.document_id
    with pytest.raises(AppError):
        ingest(distributor, path, "v1", False, poll_seconds=0)


def test_integration_disabled_without_keys(distributor):
    distributor.settings.integration_api_keys = {}
    with TestClient(create_app(distributor.settings, distributor)) as client:
        assert client.post("/api/v1/answers", json={"question": "q"}, headers={"Authorization": "Bearer any"}).status_code == 401


def test_grouped_citations_preserve_all_sources_and_reject_unknown(distributor, monkeypatch):
    doc = release(distributor.repository)
    distributor.repository.activate_release(doc.id)
    def search(query, filters, top_k):
        return [SearchChunk(source_id=str(i), document_id=filters.document_id,
                            text=f"BlueDart demo fact {i}.") for i in (1, 2)]
    monkeypatch.setattr(distributor.providers.vector, "retrieve_documents", search)
    distributor.providers.llm.answer = "Demo facts [source-1, source-2]."
    with TestClient(create_app(distributor.settings, distributor)) as client:
        body = client.post("/api/questions/ask", json={"question": "BlueDart?"}).json()
        assert {s["source_id"] for s in body["sources"]} == {"source-1", "source-2"}
        assert "[source-1] [source-2]" in body["answer"]
        distributor.providers.llm.answer = "Demo facts [source-1, source-99]."
        body = client.post("/api/questions/ask", json={"question": "BlueDart?"}).json()
        assert not body["sources"] and body["answer_status"] == "insufficient_information"
