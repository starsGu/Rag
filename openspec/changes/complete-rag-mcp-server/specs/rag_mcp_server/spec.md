## Purpose

Expose the repository's private RAG knowledge base through a fixed MCP server interface that supports retrieval and single-document archival with structured results.

## ADDED Requirements

### Requirement: Serve the RAG knowledge base over MCP
The system SHALL create the `rag-knowledge-base` MCP server on `127.0.0.1:8001`, using the `/mcp` streamable HTTP path in stateless HTTP mode.

#### Scenario: Start the MCP server
- **WHEN** the server module is run as the main program
- **THEN** the system starts the configured streamable HTTP MCP transport

### Requirement: Retrieve knowledge-base content
The system SHALL expose `get_RAG_result(command: str) -> str` and retrieve the configured `TOP_K` most relevant knowledge-base passages for the supplied command.

#### Scenario: Retrieve relevant passages
- **WHEN** an MCP client calls `get_RAG_result` with a complete search command
- **THEN** the system returns up to `TOP_K` passages produced by the configured retriever

### Requirement: Archive one document through MCP
The system SHALL expose `archive_to_corpus(path: Path) -> dict` for one supported PDF, TXT, or DOCX file and return only `status`, `source_name`, `source_key`, `document_count`, `chunk_count`, `load_error_count`, and `db_path`.

#### Scenario: Archive a supported document
- **WHEN** an MCP client calls `archive_to_corpus` with a supported document path
- **THEN** the document is processed into persisted chunks, its missing vectors are synchronized, and the returned summary has status `archived` with counts derived from the internal pipeline result

#### Scenario: Skip a same-model filename-stem duplicate
- **WHEN** the current model already has chunks whose `source_name`, without its final extension and ignoring case, matches the requested document
- **THEN** the tool does not process or persist the requested document and returns status `skipped_duplicate` with all three counts set to zero

#### Scenario: Return no document content
- **WHEN** archival succeeds or is skipped
- **THEN** the tool response contains no document text, paragraph list, semantic chunk list, or final chunk list

#### Scenario: Reject an invalid archive target
- **WHEN** an MCP client supplies a missing path, directory path, unsupported format, unparseable document, or a document that cannot be processed because the configured model fails to load
- **THEN** the operation fails as an MCP tool error instead of returning a successful summary
