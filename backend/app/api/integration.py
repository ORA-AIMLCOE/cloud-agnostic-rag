from collections import defaultdict, deque
from contextlib import contextmanager
from secrets import compare_digest
from threading import BoundedSemaphore, Lock
from time import monotonic
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, StringConstraints

from app.core.dependencies import Container, get_container
from app.domain.errors import AppError
from app.domain.models import QuestionAnswer
from app.observability.logging import request_id
from app.services.knowledge import answer_question

router = APIRouter(prefix="/api/v1", tags=["Distributor integration"])
bearer = HTTPBearer(auto_error=False)


class AnswerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]


class AnswerResponse(QuestionAnswer):
    knowledge_version: str
    demo_data: bool
    answer_status: Literal["answered", "insufficient_information"]
    request_id: str


class IntegrationLimiter:
    """Per-process limit; run one worker or use a distributed gateway when scaling."""
    def __init__(self, rate, concurrent):
        self.rate = rate
        self.requests = defaultdict(deque)
        self.lock = Lock()
        self.slots = BoundedSemaphore(concurrent)

    @contextmanager
    def admit(self, client):
        with self.lock:
            now = monotonic()
            queue = self.requests[client]
            while queue and queue[0] <= now - 60:
                queue.popleft()
            if len(queue) >= self.rate:
                raise AppError("Request limit reached. Try again later.", "rate_limited", 429)
            if not self.slots.acquire(blocking=False):
                raise AppError("The answer service is busy. Try again later.", "rate_limited", 429)
            queue.append(now)
        try:
            yield
        finally:
            self.slots.release()


def authenticate(request: Request, credentials: Annotated[HTTPAuthorizationCredentials | None, Security(bearer)]):
    config = request.app.state.container.settings
    supplied = credentials.credentials if credentials and credentials.scheme.lower() == "bearer" else ""
    for name, secret in config.integration_api_keys.items():
        expected = secret.get_secret_value()
        if expected and supplied and compare_digest(supplied.encode(), expected.encode()):
            return name
    raise AppError("A valid integration API key is required.", "unauthorized", 401)


@router.post("/answers", response_model=AnswerResponse,
             responses={401: {"description": "Invalid API key"}, 429: {"description": "Rate limited"},
                        503: {"description": "Knowledge or AWS service unavailable"}})
def answer(body: AnswerRequest, request: Request,
           c: Annotated[Container, Depends(get_container)], client: Annotated[str, Depends(authenticate)]):
    with request.app.state.integration_limiter.admit(client):
        return {**answer_question(c, body.question), "request_id": request_id.get()}
