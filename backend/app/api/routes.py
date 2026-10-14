from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, UploadFile
from starlette.concurrency import run_in_threadpool

from app.api.schemas import AskRequest, DocumentResponse, ErrorResponse
from app.core.dependencies import Container, get_container
from app.domain.errors import AppError
from app.domain.models import QuestionAnswer

router = APIRouter(
    prefix="/api", responses={code: {"model": ErrorResponse} for code in (400, 404, 409, 413, 415, 422, 503)}
)
Dependencies = Annotated[Container, Depends(get_container)]


@router.post("/documents/upload", response_model=DocumentResponse, status_code=201)
async def upload(c: Dependencies, file: UploadFile = File(...)):
    try:
        content = await file.read(c.settings.max_upload_bytes + 1)
        if len(content) > c.settings.max_upload_bytes:
            raise AppError("The document exceeds the upload size limit.", "file_too_large", 413)
        return await run_in_threadpool(c.documents.upload, file.filename or "", content)
    finally:
        await file.close()


@router.get("/documents", response_model=list[DocumentResponse])
def documents(c: Dependencies, limit: int = Query(100, ge=1, le=100), offset: int = Query(0, ge=0)):
    return c.repository.list_uploaded_documents(limit, offset)


@router.get("/documents/{document_id}/status", response_model=DocumentResponse)
def document_status(document_id: str, c: Dependencies):
    return c.documents.refresh(document_id)


@router.post("/questions/ask", response_model=QuestionAnswer)
def ask(body: AskRequest, c: Dependencies):
    return c.graph.invoke(body.model_dump())["result"]


@router.get("/questions/history", response_model=list[QuestionAnswer])
def history(
    c: Dependencies,
    document_id: str | None = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    if document_id:
        c.repository.get_document(document_id)
    return c.repository.get_question_answer_history(document_id, limit, offset)


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/readiness")
def readiness(c: Dependencies):
    c.repository.healthcheck()
    c.providers.ingestion.validate_configuration()
    return {"status": "ready"}
