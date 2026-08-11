## ADDED Requirements

### Requirement: Configure a direct chat-completions client
The system SHALL initialize a direct OpenAI-compatible Chat Completions client from project dotenv configuration using `QA_BASE_URL`, `QA_API_KEY`, and `QA_MODEL`, without embedding credentials or using an Agent.

#### Scenario: Required model configuration is available
- **WHEN** a `QaBuilder` is constructed with all required environment variables
- **THEN** it creates a client that is ready to make Chat Completions requests

#### Scenario: Required configuration is missing
- **WHEN** `QA_API_KEY` or `QA_MODEL` is absent or blank
- **THEN** construction fails with an error identifying the missing variable

### Requirement: Load all chunks for an exact source filename
The system SHALL read every `chunks.content` value whose `source_name` exactly equals `dataFile`, ordered by `chunk_index` and then chunk id, using a read-only connection to the configured corpus database.

#### Scenario: Matching chunks exist
- **WHEN** `getQA("UBP.pdf")` is called and matching chunk rows exist
- **THEN** the system loads their content in deterministic zero-based chunk order

#### Scenario: Corpus database does not exist
- **WHEN** the configured corpus database path does not exist
- **THEN** the system raises an error without creating a database or calling the model

#### Scenario: Source filename has no chunks
- **WHEN** no chunk has a `source_name` exactly matching `dataFile`
- **THEN** the system raises an error without calling the model or changing an output file

### Requirement: Generate questions in configurable index batches
The system SHALL provide `getQA(dataFile, per_chunk=50)` and sequentially cover every zero-based chunk index using inclusive ranges containing at most `per_chunk` indexes.

#### Scenario: Default ranges for 278 chunks
- **WHEN** `getQA("UBP.pdf")` processes 278 chunks with the default batch size
- **THEN** it makes six requests for `[0,49]`, `[50,99]`, `[100,149]`, `[150,199]`, `[200,249]`, and `[250,277]`

#### Scenario: Invalid batch size
- **WHEN** `per_chunk` is a boolean, non-integer, zero, or negative value
- **THEN** the system raises an error before calling the model or changing the output

### Requirement: Send full context and the active range
The system SHALL make one direct non-streaming Chat Completions request per batch using the plan-defined prompt with the current numeric range, and a user message containing the complete JSON chunk list followed by the current `[a,b]` JSON range.

#### Scenario: Generate a middle batch
- **WHEN** the system processes `[50,99]`
- **THEN** the request contains every document chunk, identifies `[50,99]`, and does not read, parse, or upload the original PDF

### Requirement: Validate and merge batch responses
The system SHALL accept each batch response as a JSON array, validate every question-answer object's `content_index` against the current inclusive range, convert valid objects to single-turn ShareGPT records, and append records in batch and response order without deduplication.

#### Scenario: Batch contains questions and aliases
- **WHEN** a batch returns valid `question` or compatible `qestion` fields with indexes inside its range
- **THEN** the system converts and appends every record while retaining each `content_index`

#### Scenario: Batch contains no questions
- **WHEN** a batch returns `[]`
- **THEN** the system accepts the batch and continues with the next range

#### Scenario: Batch response is invalid
- **WHEN** a response is empty text, malformed JSON, not an array, missing required fields, or contains an index outside the active range
- **THEN** the system raises a validation error and does not change the output file

### Requirement: Atomically replace the per-document ShareGPT dataset
The system SHALL derive the output filename from the basename stem of `dataFile`, write the complete merged record list as UTF-8 JSON under `qa/`, and atomically replace the matching file only after every batch succeeds.

#### Scenario: PDF source produces a named dataset
- **WHEN** `getQA("UBP.pdf")` succeeds
- **THEN** it writes the complete result to `qa/UBP.json`

#### Scenario: Multiple-dot source preserves its stem
- **WHEN** `getQA("paper.v2.pdf")` succeeds
- **THEN** it writes the complete result to `qa/paper.v2.json`

#### Scenario: Later batch fails
- **WHEN** any batch fails after earlier batches succeeded
- **THEN** the previous per-document JSON remains unchanged and no partial result is published

### Requirement: Provide local and live test entry points
The system SHALL provide `qa/test_qaBuilder.py` with default mocked tests, an opt-in API smoke mode, and a `--datafile` integration mode that uses the default batch size.

#### Scenario: Run mocked tests
- **WHEN** the test file runs without live-operation flags
- **THEN** it validates batch ranges, repeated full context, prompt construction, conversion, validation, merging, and atomic replacement without network access

#### Scenario: Run the API smoke check
- **WHEN** the test file runs with `--api-smoke`
- **THEN** it sends a minimal live Chat Completions request and reports whether a non-empty answer is returned

#### Scenario: Generate QA for a named source
- **WHEN** the test file runs with `--datafile UBP.pdf`
- **THEN** it calls `getQA("UBP.pdf")` with `per_chunk=50`, writes `qa/UBP.json`, and reports the generated record count
