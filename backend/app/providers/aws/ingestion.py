import json

from app.domain.errors import IngestionBusy, ProviderError
from app.domain.models import Document, IngestionState, Status
from app.providers.aws.common import aws_operation, client
from app.services.pdf_text import PDFTextError, extract_pdf_text


class AWSKnowledgeBaseIngestionProvider:
    def __init__(
        self,
        region: str,
        knowledge_base_id: str,
        data_source_id: str,
        bucket: str,
        prefix: str,
        agent=None,
        s3=None,
        mode="conventional",
    ):
        self.agent = agent or client("bedrock-agent", region)
        self.s3 = s3 or client("s3", region)
        self.kb, self.ds, self.bucket, self.prefix = knowledge_base_id, data_source_id, bucket, prefix
        self.mode = mode

    def index_key(self, document: Document) -> str:
        if self.mode == "managed" and document.content_type == "application/pdf":
            return document.storage_key + ".extracted.txt"
        return document.storage_key

    def _write_metadata(self, key: str, document_id: str, owner_id: str) -> None:
        self.s3.put_object(
            Bucket=self.bucket,
            Key=key + ".metadata.json",
            Body=json.dumps(
                {"metadataAttributes": {"document_id": document_id, "owner_id": owner_id}}
            ).encode(),
            ContentType="application/json",
            ServerSideEncryption="AES256",
        )

    def validate_configuration(self) -> None:
        with aws_operation("ingestion_configuration"):
            kb = self.agent.get_knowledge_base(knowledgeBaseId=self.kb)["knowledgeBase"]
            ds = self.agent.get_data_source(knowledgeBaseId=self.kb, dataSourceId=self.ds)["dataSource"]
        expected = "MANAGED" if self.mode == "managed" else "VECTOR"
        if kb["knowledgeBaseConfiguration"]["type"] != expected:
            raise ProviderError(f"Configure a {self.mode} {expected} Knowledge Base matching AWS_KB_MODE.")
        if kb.get("status") != "ACTIVE" or ds.get("status") != "AVAILABLE":
            raise ProviderError("The knowledge index or data source is not available.")
        config = ds["dataSourceConfiguration"]
        if self.mode == "managed":
            raw = config.get("managedKnowledgeBaseConnectorConfiguration", {}).get("connectorParameters", {})
            try:
                connector = json.loads(raw) if isinstance(raw, str) else raw
            except (ValueError, TypeError) as exc:
                raise ProviderError("The managed S3 connector configuration is invalid.") from exc
            connection = connector.get("connectionConfiguration", {})
            prefixes = connector.get("filterConfiguration", {}).get("inclusionPrefixes", [])
            if (
                config["type"] != "MANAGED_KNOWLEDGE_BASE_CONNECTOR"
                or connector.get("type") != "S3"
                or connection.get("bucketName") != self.bucket
                or (prefixes and not any(self.prefix.startswith(p) for p in prefixes))
            ):
                raise ProviderError(
                    "The managed data source does not include the document bucket and prefix."
                )
            return
        s3 = config.get("s3Configuration", {})
        prefixes = s3.get("inclusionPrefixes", [])
        if (
            config["type"] != "S3"
            or not s3.get("bucketArn", "").endswith(":" + self.bucket)
            or (prefixes and not any(self.prefix.startswith(p) for p in prefixes))
        ):
            raise ProviderError("The configured data source does not include the document bucket and prefix.")

    def start_ingestion(self, document: Document) -> IngestionState:
        with aws_operation("ingestion_start", conflict_is_busy=True):
            for state in ("STARTING", "IN_PROGRESS", "STOPPING"):
                jobs = self.agent.list_ingestion_jobs(
                    knowledgeBaseId=self.kb,
                    dataSourceId=self.ds,
                    filters=[{"attribute": "STATUS", "operator": "EQ", "values": [state]}],
                    maxResults=1,
                )
                if jobs.get("ingestionJobSummaries"):
                    raise IngestionBusy()
            index_key = self.index_key(document)
            if index_key != document.storage_key:
                with self.s3.get_object(Bucket=self.bucket, Key=document.storage_key)["Body"] as body:
                    content = body.read()
                try:
                    extracted = extract_pdf_text(content)
                except PDFTextError as exc:
                    return IngestionState(status=Status.FAILED, message=str(exc))
                # Preserve the PDF, but isolate its image-derived captions from answer retrieval.
                self._write_metadata(document.storage_key, "original-" + document.id, document.owner_id)
                self.s3.put_object(
                    Bucket=self.bucket,
                    Key=index_key,
                    Body=extracted.encode("utf-8"),
                    ContentType="text/plain; charset=utf-8",
                    ServerSideEncryption="AES256",
                )
            self._write_metadata(index_key, document.id, document.owner_id)
            job = self.agent.start_ingestion_job(
                knowledgeBaseId=self.kb,
                dataSourceId=self.ds,
                clientToken=document.id + ("-text-v1" if index_key != document.storage_key else ""),
                description="Document " + document.id,
            )["ingestionJob"]
        return IngestionState(
            job_id=job["ingestionJobId"], status=Status.PROCESSING, message="Indexing document."
        )

    def get_ingestion_status(self, document: Document) -> IngestionState:
        with aws_operation("ingestion_status"):
            job = self.agent.get_ingestion_job(
                knowledgeBaseId=self.kb, dataSourceId=self.ds, ingestionJobId=document.ingestion_job_id
            )["ingestionJob"]
        status = job["status"]
        if status in {"FAILED", "STOPPED"}:
            return IngestionState(
                job_id=document.ingestion_job_id,
                status=Status.FAILED,
                message="Indexing failed or was stopped. Check the ingestion job in your cloud console.",
            )
        if status != "COMPLETE":
            return IngestionState(
                job_id=document.ingestion_job_id, status=Status.PROCESSING, message="Indexing document."
            )
        with aws_operation("document_index_status"):
            details = self.agent.get_knowledge_base_documents(
                knowledgeBaseId=self.kb,
                dataSourceId=self.ds,
                documentIdentifiers=[
                    {"dataSourceType": "S3", "s3": {"uri": f"s3://{self.bucket}/{self.index_key(document)}"}}
                ],
            ).get("documentDetails", [])
        doc_status = details[0]["status"] if details else "NOT_FOUND"
        if doc_status in {
            "FAILED",
            "PARTIALLY_INDEXED",
            "METADATA_PARTIALLY_INDEXED",
            "METADATA_UPDATE_FAILED",
            "IGNORED",
        }:
            return IngestionState(
                job_id=document.ingestion_job_id,
                status=Status.FAILED,
                message="Document indexing is incomplete. Inspect document status in the cloud console.",
            )
        return IngestionState(
            job_id=document.ingestion_job_id,
            status=Status.PROCESSING,
            sync_complete=doc_status == "INDEXED",
            message="Sync completed; verifying document searchability.",
        )
