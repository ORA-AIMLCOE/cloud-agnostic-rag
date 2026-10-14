from app.domain.models import Document, StoredObject


class OCIStorageProvider:
    def upload_document(self, document: Document, content: bytes) -> StoredObject:
        raise NotImplementedError("Implement OCI Object Storage upload.")

    def get_document(self, key: str) -> bytes:
        raise NotImplementedError("Implement OCI Object Storage read.")

    def delete_document(self, key: str) -> None:
        raise NotImplementedError("Implement OCI Object Storage deletion and metadata cleanup.")

    def list_documents(self) -> list[StoredObject]:
        raise NotImplementedError("Implement paginated OCI Object Storage listing.")
