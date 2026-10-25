"""Distributor contracts against the generated Oracle repository (offline SQLite harness)."""
import hashlib
from secrets import token_urlsafe

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.dialects import oracle
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.schema import CreateTable

from app.admin import ingest
from app.core.config import Settings
from app.core.dependencies import build_container
from app.domain.errors import AppError
from app.domain.models import Document, KnowledgeRelease, SearchChunk, Status
from app.main import create_app
from app.providers.factory import Providers
from app.providers.oci.database_models import Base, IngestionLockRow
from app.providers.oci.repository import OracleRepository
from tests.fakes import FakeIngestion, FakeLLM, FakeVector, MemoryStorage


@pytest.fixture
def oracle_distributor(monkeypatch):
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    with sessions.begin() as session:
        session.add(IngestionLockRow(id=1))
    repository = OracleRepository(sessions)
    monkeypatch.setattr("app.providers.oci.database.create_oracle_repository", lambda: (engine, repository))
    def no_postgres(*args):
        raise AssertionError("OCI runtime must not open PostgreSQL")
    monkeypatch.setattr("app.core.dependencies.create_database", no_postgres)
    providers = Providers(storage=MemoryStorage(), vector=FakeVector(), ingestion=FakeIngestion(), llm=FakeLLM())
    providers.llm.answer = "BlueDart takes 1-2 business days. [source-1]"
    calls = []
    def retrieve(query, filters, top_k):
        calls.append(filters.document_id)
        return [SearchChunk(source_id="chunk", document_id=filters.document_id,
                            text="BlueDart takes 1-2 business days. Delhivery Ekart DTDC are also documented.")]
    monkeypatch.setattr(providers.vector, "retrieve_documents", retrieve)
    cfg = Settings(_env_file=None, cloud_provider="oci", distributor_mode=True)
    cfg.integration_api_keys = {"client": SecretStr(token_urlsafe(32))}
    container = build_container(cfg, providers=providers)
    assert container.repository is repository
    yield container, calls
    engine.dispose()


def test_oracle_release_ddl_activation_and_rollback(oracle_distributor):
    container, _ = oracle_distributor
    repo = container.repository
    ddl = "\n".join(str(CreateTable(table).compile(dialect=oracle.dialect())) for table in Base.metadata.sorted_tables)
    assert "knowledge_releases" in ddl and "active_knowledge" in ddl
    assert "ON DELETE RESTRICT" not in ddl
    documents = []
    for number in (1, 2):
        doc = repo.save_document_metadata(Document(original_filename=f"release-{number}.md",
            storage_key=f"documents/{number}.md", content_type="text/markdown",
            ingestion_status=Status.READY if number == 1 else Status.PROCESSING))
        release = KnowledgeRelease(document_id=doc.id, content_sha256=hashlib.sha256(str(number).encode()).hexdigest(),
                                   version=f"v{number}", demo_data=True)
        repo.register_release(release)
        assert repo.get_release_by_hash(release.content_sha256).demo_data is True
        documents.append(doc)
    repo.activate_release(documents[0].id)
    with pytest.raises(AppError):
        repo.activate_release(documents[1].id)
    assert repo.get_active_release().document_id == documents[0].id
    repo.update_document_status(documents[1].id, Status.READY, "Ready")
    repo.activate_release(documents[1].id)
    repo.activate_release(documents[0].id)
    assert repo.get_active_release().version == "v1"


def test_oracle_preingestion_and_authenticated_distributor_answers(oracle_distributor, tmp_path):
    container, calls = oracle_distributor
    old = container.repository.save_document_metadata(Document(original_filename="old-personal.txt",
        storage_key="documents/old.txt", content_type="text/plain", ingestion_status=Status.READY))
    path = tmp_path / "distributors.md"
    path.write_text("BlueDart Delhivery Ekart DTDC. Fictional demo facts.", encoding="utf-8")
    first = ingest(container, path, "demo-v1", True, timeout=10, poll_seconds=0)
    second = ingest(container, path, "demo-v1", True, timeout=10, poll_seconds=0)
    assert first.document_id == second.document_id
    assert len(container.providers.storage.objects) == 1
    with TestClient(create_app(container.settings, container)) as client:
        assert client.get("/api/knowledge").json()["version"] == "demo-v1"
        assert [item["id"] for item in client.get("/api/documents").json()] == [first.document_id]
        assert client.post("/api/v1/answers", json={"question": "BlueDart?"}).status_code == 401
        response = client.post("/api/v1/answers", json={"question": "BlueDart delivery?"},
                               headers={"Authorization": "Bearer " + container.settings.integration_api_keys["client"].get_secret_value()})
        assert response.status_code == 200
        answer = response.json()
        assert answer["document_id"] == first.document_id and answer["knowledge_version"] == "demo-v1"
        assert answer["sources"] and answer["demo_data"] is True
        assert answer["answer"] == "BlueDart takes 1-2 business days. [source-1]"
        assert client.get("/api/questions/history").json()[0]["answer"] == answer["answer"]
        assert client.post("/api/questions/ask", json={"document_id": old.id, "question": "Old data?"}).status_code == 400
        assert client.post("/api/documents/upload", files={"file": ("new.txt", b"text")}).status_code == 403
    assert calls and set(calls) == {first.document_id}
