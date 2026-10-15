"""Database-only connectivity and vector checks. Probe inserts are always rolled back."""
import sys
from pathlib import Path
from array import array
from contextlib import nullcontext
from types import SimpleNamespace
from uuid import uuid4
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from sqlalchemy import text, bindparam, Text
from sqlalchemy.orm import sessionmaker
from app.domain.models import SearchFilter
from app.providers.oci.database import create_oracle_engine
from app.providers.oci.repository import OracleRepository
from app.providers.oci.vector_search import OCIVectorSearchProvider


def check_database(engine):
    OracleRepository(sessionmaker(engine)).healthcheck()
    token = uuid4().hex
    # Synthetic vectors test the database only; they are never used by the RAG application.
    settings = SimpleNamespace(oci_embedding_model_id="probe", oci_embedding_endpoint="probe",
        oci_embedding_serving_mode="on_demand", oci_embedding_dimensions=3,
        oci_chunk_chars=200, oci_chunk_overlap=20)
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            provider = OCIVectorSearchProvider(SimpleNamespace(connect=lambda: nullcontext(connection)),
                SimpleNamespace(embed=lambda *args: [[1., 0., 0.]]), settings)
            provider.index_id = token
            insert = text("""INSERT INTO rag_oci_chunks
                (index_id, document_id, owner_id, chunk_id, content, embedding)
                VALUES (:idx, :doc, :owner, :chunk, :content, :vector)""").bindparams(bindparam("content", type_=Text()))
            for idx, doc, owner, chunk, vector in [
                (token, token, token, "match", [1, 0, 0]),
                (token, token, token, "orthogonal", [0, 1, 0]),
                (token, token, "other-owner", "excluded-owner", [1, 0, 0]),
                (token, "other-document", token, "excluded-doc", [1, 0, 0]),
                (token + "x", token, token, "excluded-dimensions", [1, 0, 0, 0]),
            ]:
                connection.execute(insert, dict(idx=idx, doc=doc, owner=owner, chunk=chunk,
                    content="Oracle vector probe " + "text " * 1000, vector=array("f", vector)))
            results = provider.retrieve_documents("probe", SearchFilter(document_id=token, owner_id=token), 10)
            assert [r.source_id for r in results] == ["match", "orthogonal"]
            assert abs(results[0].score - 1) < 0.0001 and abs(results[1].score) < 0.0001
            assert len(results[0].text) > 4000
        finally:
            transaction.rollback()


if __name__ == "__main__":
    engine = create_oracle_engine()
    try:
        check_database(engine)
    except Exception:
        print("Oracle checks failed. Verify schema setup, database version, network access and credentials.", file=sys.stderr)
        raise SystemExit(1) from None
    finally:
        engine.dispose()
    print("Oracle repository, native vectors, CLOB reads, cosine ranking and isolation checks passed. Probe writes rolled back.")
