import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.dependencies import build_container
from app.database.models import Base, IngestionLockRow
from app.database.session import create_database
from app.main import create_app
from app.providers.factory import Providers
from app.repositories.sqlalchemy_repository import SQLAlchemyRepository
from tests.fakes import FakeIngestion, FakeLLM, FakeVector, MemoryStorage


def pytest_addoption(parser):
    parser.addoption(
        "--run-integration",
        action="store_true",
        default=False,
        help="Opt in to real AWS and database calls, which may incur costs.",
    )


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--run-integration"):
        for item in items:
            if "integration" in item.keywords:
                item.add_marker(
                    pytest.mark.skip(reason="Use --run-integration to enable real infrastructure tests.")
                )


@pytest.fixture
def repository(tmp_path):
    engine, sessions = create_database(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    with sessions.begin() as session:
        session.add(IngestionLockRow(id=1))
    yield SQLAlchemyRepository(sessions)
    engine.dispose()


@pytest.fixture
def providers():
    return Providers(FakeLLM(), MemoryStorage(), FakeVector(), FakeIngestion())


@pytest.fixture
def container(repository, providers):
    return build_container(Settings(_env_file=None), providers, repository)


@pytest.fixture
def client(container):
    with TestClient(create_app(container.settings, container)) as client:
        yield client
