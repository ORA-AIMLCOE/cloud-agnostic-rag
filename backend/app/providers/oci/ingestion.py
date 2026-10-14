from app.domain.models import Document, IngestionState


class OCIIngestionProvider:
    def validate_configuration(self) -> None:
        raise NotImplementedError("Validate the selected OCI index and data source configuration.")

    def start_ingestion(self, document: Document) -> IngestionState:
        raise NotImplementedError("Implement idempotent asynchronous ingestion with document metadata.")

    def get_ingestion_status(self, document: Document) -> IngestionState:
        raise NotImplementedError(
            "Normalize job state and distinguish indexed documents from completed jobs."
        )
