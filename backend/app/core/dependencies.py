from dataclasses import dataclass
from typing import Any

from fastapi import Request

from app.core.config import Settings
from app.database.session import create_database
from app.domain.models import InferenceConfig
from app.interfaces.repository import Repository
from app.providers.factory import Providers, create_providers
from app.repositories.sqlalchemy_repository import SQLAlchemyRepository
from app.services.documents import DocumentService
from app.workflows.rag_graph import build_rag_graph


@dataclass
class Container:
    settings: Settings
    providers: Providers
    repository: Repository
    documents: DocumentService
    graph: Any
    engine: Any = None


def build_container(
    settings: Settings, providers: Providers | None = None, repository: Repository | None = None
) -> Container:
    if providers is None:
        providers = create_providers(settings)
        providers.ingestion.validate_configuration()
    engine = None
    if repository is None:
        engine, sessions = create_database(settings.database_url)
        repository = SQLAlchemyRepository(sessions)
    documents = DocumentService(
        providers.storage,
        providers.ingestion,
        providers.vector,
        repository,
        settings.aws_s3_prefix,
        settings.max_upload_bytes,
        settings.ingestion_timeout_seconds,
    )
    graph = build_rag_graph(
        providers.llm,
        providers.vector,
        repository,
        InferenceConfig(max_tokens=settings.llm_max_tokens, temperature=settings.llm_temperature),
        settings.top_k,
        settings.context_max_chars,
        settings.max_question_chars,
        settings.distributor_mode,
    )
    return Container(settings, providers, repository, documents, graph, engine)


def get_container(request: Request) -> Container:
    return request.app.state.container
