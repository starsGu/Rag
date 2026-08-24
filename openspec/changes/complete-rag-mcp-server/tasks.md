## 1. Path Mapping and Existing Behavior

- [x] 1.1 Verify the exact `plan/rag_mcp_server.txt` ↔ `rag_mcp_server.py` ↔ `specs/rag_mcp_server/spec.md` correspondence before editing source.
- [x] 1.2 Verify the exact `plan/HybridRetriever/Retriever.txt` ↔ `HybridRetriever/Retriever.py` ↔ `specs/HybridRetriever/Retriever/spec.md` correspondence before editing source.
- [x] 1.3 Preserve `get_RAG_result`, `TOP_K = 5`, server address, and transport settings.

## 2. Same-Model Filename-Stem Deduplication

- [x] 2.1 Add path validation, `Path(...).stem.casefold()` source-key normalization, and current-model `source_name` lookup without changing database schemas or chunk IDs.
- [x] 2.2 Guard validation-followed-by-lookup-through-update with a process-local archive lock.
- [x] 2.3 Make `Retriever.archive` return `None` for same-model stem duplicates while preserving `PipelineResult` success and different-model archival.

## 3. Compact MCP Archive Result

- [x] 3.1 Register `archive_to_corpus(path: Path) -> dict` and return exactly status, source name/key, three counts, and database path.
- [x] 3.2 Return zero counts with `skipped_duplicate` for duplicates and expose no documents, paragraphs, semantic chunks, or chunks.
- [x] 3.3 Preserve exception propagation for missing paths, directories, unsupported formats, parsing failures, and model failures.

## 4. Verification

- [x] 4.1 Use temporary files and databases to verify same-model stem deduplication across paths/extensions/case, different-model archival, invalid-path precedence, single-process concurrency, unchanged schemas, corpus/vector persistence, retrieval, and exact MCP responses.
- [x] 4.2 Run the existing regression suite without modifying persistent tests.
- [x] 4.3 Run strict OpenSpec validation and confirm all apply tasks are complete.
