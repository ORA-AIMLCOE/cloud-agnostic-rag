# PDF retrieval investigation — 2026-10-13

The reported full-name lookup failed even though the name was present in the uploaded resume.
The original PDF is an unusually tall, dense single page. Native extraction found 23,701 characters,
including the requested name and education details. The Managed Knowledge Base's original indexed content
was mostly image descriptions and garbled fragments rather than the readable PDF text. Retrieving more
results did not repair that underlying representation; a raw model call also declined to answer from it.

The fix extracts native text with pypdf for managed PDF ingestion, stores it as an encrypted text companion,
and indexes that companion under the application's existing document ID. The original PDF is retained but
its image-derived captions use a different metadata ID, keeping them out of document-filtered answers.
The app checks the companion's INDEXED status and filtered retrieval before marking the document ready.
Unreadable or encrypted PDFs fail explicitly with an actionable status instead of starting a poor-quality sync.

The affected existing resume was re-indexed in place. Its document identity and previous history were preserved.
No name was hardcoded, no model upgrade was made, and the grounding/citation rules were not relaxed.
The prompt now explicitly directs factual lookup from a relevant passage even when other passages are
unrelated. Safe diagnostics distinguish empty retrieval from missing or unknown citations without logging
document contents. The local backend was restarted with these changes.

Validation:

- 51 backend tests passed, 3 opt-in integration tests skipped; lint passed.
- Live API full-name question returned the expected full name with a source citation.
- Live API education question returned both BCA and MCA qualifications with citations.
- Final live evaluation passed all five checks: three repeated full-name requests, one education request,
  and one unsupported question that correctly declined to invent an answer.
- Some name attempts still declined after clean re-indexing, whereas direct traced model calls answered
  correctly. The exact cause of that intermittent behavior was not isolated to the citation validator or
  index propagation. Direct-lookup prompt guidance was added and verified with repeated live requests.

Limitations: this is native PDF text extraction, not OCR. PDFs without a text layer on every page need OCR
or a TXT/Markdown replacement. Native font mappings and complex reading order can still require inspection.
Ready status confirms indexing/searchability, not the accuracy of every extracted fact. The original early
cloud smoke test used plain text and therefore did not cover this PDF parsing failure; regression tests now
include extraction from an extremely tall PDF page and isolation of original-image captions.
