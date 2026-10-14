from app.domain.models import Document, StoredObject
from app.providers.aws.common import aws_operation, client


class AWSS3StorageProvider:
    def __init__(self, region: str, bucket: str, prefix: str, s3=None):
        self.s3 = s3 or client("s3", region)
        self.bucket, self.prefix = bucket, prefix

    def upload_document(self, document: Document, content: bytes) -> StoredObject:
        with aws_operation("storage_upload"):
            self.s3.put_object(
                Bucket=self.bucket,
                Key=document.storage_key,
                Body=content,
                ContentType=document.content_type,
                ServerSideEncryption="AES256",
                Metadata={"document_id": document.id},
            )
        return StoredObject(key=document.storage_key, reference=f"s3://{self.bucket}/{document.storage_key}")

    def get_document(self, key: str) -> bytes:
        with aws_operation("storage_get"):
            body = self.s3.get_object(Bucket=self.bucket, Key=key)["Body"]
            try:
                return body.read()
            finally:
                body.close()

    def delete_document(self, key: str) -> None:
        with aws_operation("storage_delete"):
            self.s3.delete_object(Bucket=self.bucket, Key=key)
            self.s3.delete_object(Bucket=self.bucket, Key=key + ".metadata.json")
            if key.lower().endswith(".pdf"):
                self.s3.delete_object(Bucket=self.bucket, Key=key + ".extracted.txt")
                self.s3.delete_object(Bucket=self.bucket, Key=key + ".extracted.txt.metadata.json")

    def list_documents(self) -> list[StoredObject]:
        with aws_operation("storage_list"):
            return [
                StoredObject(key=obj["Key"], reference=f"s3://{self.bucket}/{obj['Key']}")
                for page in self.s3.get_paginator("list_objects_v2").paginate(
                    Bucket=self.bucket, Prefix=self.prefix
                )
                for obj in page.get("Contents", [])
                if not obj["Key"].endswith((".metadata.json", ".pdf.extracted.txt"))
            ]
