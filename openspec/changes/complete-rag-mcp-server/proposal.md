## Why

The RAG MCP archive tool must avoid reprocessing the same logical filename for the same model, and returning a complete `PipelineResult` can inject the entire document and every intermediate chunk into agent context. This change makes archival idempotent by case-insensitive filename stem and returns only a compact status summary.

## What Changes

- Check existing `chunks.source_name` values for the current model before archival, using the filename without its final extension and case differences as the comparison key.
- Skip same-stem archival for the same model while allowing the same stem to be processed under a different model.
- Add an `archive_to_corpus(path: Path) -> dict` MCP tool that returns only status, source identity, counts, and the corpus database path.
- Keep invalid-path, directory, unsupported-format, parsing, and model errors as MCP tool errors.
- Preserve the existing retrieval tool, `TOP_K` setting, server address, and transport configuration.

## Capabilities

### New Capabilities

- `rag_mcp_server`: Expose the plan-defined RAG retrieval server behavior and a single-document archive MCP tool.

### Modified Capabilities

- `HybridRetriever/Retriever`: Add same-model, case-insensitive filename-stem duplicate detection before document processing.

## Impact

- Affects `rag_mcp_server.py` and `HybridRetriever/Retriever.py`.
- Changes `Retriever.archive` to return `None` when a same-model filename-stem duplicate is skipped.
- Adds no new database schema, persistent test module, or dependency manifest.
