import json
from io import BytesIO
from unittest.mock import MagicMock

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.domain.models import Document, Status
from app.providers.aws.ingestion import AWSKnowledgeBaseIngestionProvider
from app.services.pdf_text import PDFTextError, extract_pdf_text


def pdf_bytes(text="Avery Morgan - Education: Bachelor of Computer Science"):
    writer = PdfWriter()
    page = writer.add_blank_page(width=600, height=10000)
    if text:
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
        )
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 20 9960 Td ({text}) Tj ET".encode())
        page[NameObject("/Contents")] = writer._add_object(stream)
    result = BytesIO()
    writer.write(result)
    return result.getvalue()


def test_native_text_survives_extremely_tall_page():
    text = extract_pdf_text(pdf_bytes())
    assert "Avery Morgan" in text and "Bachelor of Computer Science" in text
    assert text.startswith("[Page 1]")


@pytest.mark.parametrize("content", [b"%PDF-not-valid", pdf_bytes("")])
def test_unreadable_pdf_has_actionable_error(content):
    with pytest.raises(PDFTextError, match="searchable PDF"):
        extract_pdf_text(content)


def managed_adapter(content):
    agent, s3 = MagicMock(), MagicMock()
    agent.list_ingestion_jobs.return_value = {"ingestionJobSummaries": []}
    agent.start_ingestion_job.return_value = {"ingestionJob": {"ingestionJobId": "NEWJOB1234"}}
    s3.get_object.return_value = {"Body": BytesIO(content)}
    doc = Document(
        id="b549909a-9bd2-40e4-bbb1-c879b8e9f460",
        original_filename="resume.pdf",
        content_type="application/pdf",
        storage_key="documents/resume.pdf",
    )
    adapter = AWSKnowledgeBaseIngestionProvider(
        "unused", "KB12345678", "DS12345678", "bucket", "documents/", agent, s3, mode="managed"
    )
    return adapter, agent, s3, doc


def test_managed_pdf_indexes_text_and_isolates_original_captions():
    adapter, agent, s3, doc = managed_adapter(pdf_bytes())
    assert adapter.start_ingestion(doc).status == Status.PROCESSING
    writes = {call.kwargs["Key"]: call.kwargs for call in s3.put_object.call_args_list}
    assert doc.storage_key not in writes  # Original PDF bytes never overwritten.
    derived = doc.storage_key + ".extracted.txt"
    assert b"Avery Morgan" in writes[derived]["Body"]
    original_meta = json.loads(writes[doc.storage_key + ".metadata.json"]["Body"])
    canonical_meta = json.loads(writes[derived + ".metadata.json"]["Body"])
    assert original_meta["metadataAttributes"]["document_id"] != doc.id
    assert canonical_meta["metadataAttributes"] == {"document_id": doc.id, "owner_id": doc.owner_id}
    assert agent.start_ingestion_job.call_args.kwargs["clientToken"].endswith("-text-v1")

    doc.ingestion_job_id = "NEWJOB1234"
    agent.get_ingestion_job.return_value = {"ingestionJob": {"status": "COMPLETE"}}
    agent.get_knowledge_base_documents.return_value = {"documentDetails": [{"status": "INDEXED"}]}
    assert adapter.get_ingestion_status(doc).sync_complete
    identifiers = agent.get_knowledge_base_documents.call_args.kwargs["documentIdentifiers"]
    assert identifiers[0]["s3"]["uri"] == "s3://bucket/" + derived


def test_empty_text_fails_without_starting_ingestion():
    adapter, agent, s3, doc = managed_adapter(pdf_bytes(""))
    state = adapter.start_ingestion(doc)
    assert state.status == Status.FAILED and "OCR" in state.message
    agent.start_ingestion_job.assert_not_called()
    s3.put_object.assert_not_called()
