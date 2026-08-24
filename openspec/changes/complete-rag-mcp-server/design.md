## Context

See `proposal.md` for motivation. The corpus already stores `source_name` and `model_path` on every chunk, so duplicate detection can be added before processing without changing either database schema. The MCP server currently returns the complete pipeline object, which repeats the document text across multiple processing stages.

## Goals / Non-Goals

**Goals:**

- Skip same-model documents whose case-insensitive filename stem already exists.
- Preserve different-model processing, the existing chunk identity formula, and all stored source metadata.
- Return a fixed seven-field MCP summary with no document or chunk content.
- Serialize same-process archive calls so concurrent duplicates cannot both pass the check.

**Non-Goals:**

- Database schema or data migration, chunk ID changes, cross-process locking, folder archival, or path sandboxing.
- New or modified persistent Python test modules.
- Synchronizing or archiving the OpenSpec change in this implementation pass.

## Decisions

1. **Compare current-model source names in Python.** `Retriever.source_key(path)` uses `Path(path).stem.casefold()`. Before processing, query `SELECT DISTINCT source_name FROM chunks WHERE model_path = ?` and compare normalized keys. This supports existing databases without schema changes.
2. **Validate before duplicate detection.** Check existence, file type, and `.txt`/`.pdf`/`.docx` support before querying duplicates so an invalid path never reports a successful skip.
3. **Lock the whole same-process archive operation.** A `threading.Lock` covers duplicate lookup, document processing, corpus persistence, and vector update. This guarantees one writer within the singleton process; multiple service processes remain outside scope.
4. **Use `None` for an internal duplicate outcome.** `Retriever.archive` returns its existing `PipelineResult` on success and `None` when skipped. No exception is used for an expected duplicate.
5. **Build a compact MCP response.** The tool returns `status`, original `source_name`, normalized `source_key`, three counts, and `db_path`. Duplicate counts are zero; successful counts come from the internal pipeline result, which is never returned to the client.
6. **Verify without tracked tests.** Run temporary database/file scenarios for stem, model, invalid-path, concurrency, and MCP schema/response behavior, then run the unchanged existing regressions.

## Risks / Trade-offs

- **Separate server processes can race** → The user selected single-process guarantees; cross-process locking and schema constraints remain out of scope.
- **Scanning source names is linear in distinct current-model documents** → The current corpus is small, and avoiding a schema/index change is an explicit requirement.
- **A filename stem is broader than path identity** → This is intentional within one model; different models remain independently archivable.

## Migration Plan

No migration is required. Restart the MCP server after deployment. Rollback consists of reverting the precheck/lock and compact response while leaving both databases untouched.
