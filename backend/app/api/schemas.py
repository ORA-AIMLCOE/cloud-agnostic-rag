from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

from app.domain.models import Status


class AskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_id: Annotated[str, StringConstraints(min_length=1, max_length=36)]
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    original_filename: str
    content_type: str
    ingestion_status: Status
    status_message: str
    created_at: datetime
    updated_at: datetime


class ErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str


class ErrorResponse(BaseModel):
    error: ErrorDetail
