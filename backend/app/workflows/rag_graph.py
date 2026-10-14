import json
import logging
import re
from time import perf_counter
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.domain.errors import AppError, ProviderError
from app.domain.models import (
    Document,
    Generation,
    InferenceConfig,
    QuestionAnswer,
    SearchChunk,
    SearchFilter,
    Source,
    Status,
)
from app.interfaces.llm import LLMProvider
from app.interfaces.repository import Repository
from app.interfaces.vector_search import VectorSearchProvider
from app.workflows.prompts import SYSTEM_PROMPT

log = logging.getLogger(__name__)
INSUFFICIENT = "The document does not contain enough information to answer this question."


class RAGState(TypedDict, total=False):
    document_id: str
    question: str
    document: Document
    chunks: list[SearchChunk]
    sources: list[Source]
    context: str
    generation: Generation
    result: QuestionAnswer
    started: float


def build_rag_graph(
    llm: LLMProvider,
    vector: VectorSearchProvider,
    repository: Repository,
    config: InferenceConfig,
    top_k: int = 5,
    max_context_chars: int = 24000,
    max_question_chars: int = 4000,
):
    def validate(state: RAGState):
        question = state["question"].strip()
        if not question or len(question) > max_question_chars:
            raise AppError("Enter a nonempty question within the length limit.", "invalid_question", 422)
        document = repository.get_document(state["document_id"])
        if document.ingestion_status != Status.READY:
            raise AppError("Wait until the document is indexed and searchable.", "document_not_ready", 409)
        return {"document": document, "question": question, "started": perf_counter()}

    def retrieve(state: RAGState):
        doc = state["document"]
        chunks = vector.retrieve_documents(
            state["question"], SearchFilter(document_id=doc.id, owner_id=doc.owner_id), top_k
        )
        if any(chunk.document_id != doc.id for chunk in chunks):
            raise ProviderError("The search index returned inconsistent document metadata.")
        log.info("context_retrieved", extra={"document_id": doc.id, "count": len(chunks)})
        return {"chunks": chunks}

    def prompt(state: RAGState):
        remaining, references, sources = max_context_chars, [], []
        seen = set()
        for chunk in state["chunks"]:
            if remaining <= 0:
                break
            if chunk.source_id in seen or not chunk.text.strip():
                continue
            seen.add(chunk.source_id)
            excerpt = chunk.text[:remaining]
            remaining -= len(excerpt)
            source_id = f"source-{len(sources) + 1}"
            sources.append(
                Source(
                    source_id=source_id,
                    document_name=state["document"].original_filename,
                    excerpt=excerpt,
                    score=chunk.score,
                    page=chunk.metadata.get("page"),
                )
            )
            references.append({"source_id": source_id, "text": excerpt})
        return {"context": json.dumps(references, ensure_ascii=False), "sources": sources}

    def generate(state: RAGState):
        if not state["sources"]:
            log.info("answer_without_context", extra={"document_id": state["document_id"]})
            return {"generation": Generation(text=INSUFFICIENT, model_id="no-context")}
        result = llm.generate_response(SYSTEM_PROMPT, state["question"], state["context"], config)
        allowed = {source.source_id for source in state["sources"]}
        cited = set(re.findall(r"\[(source-[^\]\s]+)\]", result.text))
        # Fail closed on invented IDs and uncited assertions; citations never come from model-generated metadata.
        if not cited or not cited.issubset(allowed):
            log.warning(
                "answer_citation_validation_failed",
                extra={
                    "document_id": state["document_id"],
                    "error_type": "missing_citations" if not cited else "unknown_citation",
                    "count": len(state["sources"]),
                },
            )
            result = result.model_copy(update={"text": INSUFFICIENT})
            sources = []
        else:
            sources = [s for s in state["sources"] if s.source_id in cited]
        return {"generation": result, "sources": sources}

    def save(state: RAGState):
        result = repository.save_question_answer(
            QuestionAnswer(
                document_id=state["document_id"],
                question=state["question"],
                answer=state["generation"].text,
                sources=state["sources"],
                model_id=state["generation"].model_id,
                latency_ms=int((perf_counter() - state["started"]) * 1000),
            )
        )
        return {"result": result}

    graph = StateGraph(RAGState)
    for name, node in (
        ("validate", validate),
        ("retrieve", retrieve),
        ("build_prompt", prompt),
        ("generate", generate),
        ("save", save),
    ):
        graph.add_node(name, node)
    for before, after in zip(
        (START, "validate", "retrieve", "build_prompt", "generate", "save"),
        ("validate", "retrieve", "build_prompt", "generate", "save", END),
    ):
        graph.add_edge(before, after)
    return graph.compile()
