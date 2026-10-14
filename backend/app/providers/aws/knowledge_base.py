from hashlib import sha256

from app.domain.errors import ProviderError
from app.domain.models import SearchChunk, SearchFilter
from app.providers.aws.common import aws_operation, client


class AWSKnowledgeBaseVectorProvider:
    def __init__(self, region: str, knowledge_base_id: str, runtime=None, mode="conventional"):
        self.runtime = runtime or client("bedrock-agent-runtime", region)
        self.knowledge_base_id = knowledge_base_id
        self.mode = mode

    def retrieve_documents(self, query: str, filters: SearchFilter, top_k: int) -> list[SearchChunk]:
        search = {
            "numberOfResults": top_k,
            "filter": {
                "andAll": [
                    {"equals": {"key": "document_id", "value": filters.document_id}},
                    {"equals": {"key": "owner_id", "value": filters.owner_id}},
                ]
            },
        }
        config_key = "vectorSearchConfiguration"
        if self.mode == "managed":
            config_key = "managedSearchConfiguration"
            # Custom Titan embeddings cannot use the default managed reranker.
            search["rerankingModelType"] = "NONE"
        with aws_operation("retrieval"):
            result = self.runtime.retrieve(
                knowledgeBaseId=self.knowledge_base_id,
                retrievalQuery={"text": query},
                retrievalConfiguration={config_key: search},
            )
        chunks = []
        for item in result.get("retrievalResults", []):
            metadata = item.get("metadata", {})
            if (
                metadata.get("document_id") != filters.document_id
                or metadata.get("owner_id") != filters.owner_id
            ):
                raise ProviderError("The search index returned inconsistent document metadata.")
            text = item.get("content", {}).get("text", "")
            if not text.strip():
                continue
            source_id = sha256((filters.document_id + text).encode()).hexdigest()[:20]
            page = metadata.get("x-amz-bedrock-kb-document-page-number")
            chunks.append(
                SearchChunk(
                    source_id=source_id,
                    document_id=filters.document_id,
                    text=text,
                    score=item.get("score"),
                    metadata={"page": int(page)} if page is not None else {},
                )
            )
        return chunks
