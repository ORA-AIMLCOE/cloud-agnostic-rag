from contextlib import contextmanager
from threading import RLock

from sqlalchemy import select, text
from sqlalchemy.orm import sessionmaker

from app.database.models import DocumentRow, IngestionLockRow, QuestionAnswerRow
from app.domain.errors import AppError
from app.domain.models import Document, QuestionAnswer, Status, utcnow


class SQLAlchemyRepository:
    def __init__(self, sessions: sessionmaker):
        self.sessions = sessions
        self.local_lock = RLock()

    def save_document_metadata(self, document: Document) -> Document:
        with self.sessions.begin() as session:
            session.add(DocumentRow(**document.model_dump()))
        return document

    def get_document(self, document_id: str) -> Document:
        with self.sessions() as session:
            row = session.get(DocumentRow, document_id)
            if row is None:
                raise AppError("Document not found.", "not_found", 404)
            return Document.model_validate(row)

    def update_document_status(
        self, document_id: str, status: Status, message: str, job_id: str | None = None
    ) -> Document:
        with self.sessions.begin() as session:
            row = session.get(DocumentRow, document_id)
            if row is None:
                raise AppError("Document not found.", "not_found", 404)
            row.ingestion_status, row.status_message, row.updated_at = status, message, utcnow()
            if job_id is not None:
                row.ingestion_job_id = job_id
            session.flush()
            return Document.model_validate(row)

    def list_uploaded_documents(self, limit: int = 100, offset: int = 0) -> list[Document]:
        with self.sessions() as session:
            return [
                Document.model_validate(row)
                for row in session.scalars(
                    select(DocumentRow)
                    .order_by(DocumentRow.created_at.desc(), DocumentRow.id)
                    .limit(limit)
                    .offset(offset)
                )
            ]

    def save_question_answer(self, answer: QuestionAnswer) -> QuestionAnswer:
        data = answer.model_dump(exclude={"sources"})
        with self.sessions.begin() as session:
            session.add(QuestionAnswerRow(**data, source_references=[s.model_dump() for s in answer.sources]))
        return answer

    def get_question_answer_history(
        self, document_id: str | None = None, limit: int = 50, offset: int = 0
    ) -> list[QuestionAnswer]:
        query = select(QuestionAnswerRow).order_by(QuestionAnswerRow.created_at.desc(), QuestionAnswerRow.id)
        if document_id is not None:
            query = query.where(QuestionAnswerRow.document_id == document_id)
        with self.sessions() as session:
            return [
                QuestionAnswer(
                    id=r.id,
                    document_id=r.document_id,
                    question=r.question,
                    answer=r.answer,
                    sources=r.source_references,
                    model_id=r.model_id,
                    latency_ms=r.latency_ms,
                    created_at=r.created_at,
                )
                for r in session.scalars(query.limit(limit).offset(offset))
            ]

    @contextmanager
    def ingestion_lock(self):
        # PostgreSQL SELECT FOR UPDATE serializes app workers. Local lock also supports SQLite tests.
        with self.local_lock, self.sessions.begin() as session:
            session.execute(
                select(IngestionLockRow).where(IngestionLockRow.id == 1).with_for_update()
            ).scalar_one()
            yield

    def healthcheck(self) -> None:
        with self.sessions() as session:
            session.execute(text("SELECT 1"))
            session.execute(select(DocumentRow.id).limit(1))
            session.execute(select(QuestionAnswerRow.id).limit(1))
            session.execute(select(IngestionLockRow).where(IngestionLockRow.id == 1)).scalar_one()
