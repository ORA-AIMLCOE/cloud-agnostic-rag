from app.domain.models import SearchChunk, SearchFilter


class OCIVectorSearchProvider:
    def retrieve_documents(self, query: str, filters: SearchFilter, top_k: int) -> list[SearchChunk]:
        raise NotImplementedError(
            "Select an OCI vector service, implement filters, and normalize SearchChunk."
        )
