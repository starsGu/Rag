# qa/qaBuilder Specification

## Purpose

Define how `QaBuilder` generates source-aware ShareGPT question-answer data from ordered corpus chunks through an OpenAI-compatible Chat Completions API.

## Requirements

### Requirement: Configure a direct chat-completions client
The system SHALL initialize a direct OpenAI-compatible Chat Completions client using `QA_BASE_URL` and `QA_API_KEY`, and SHALL use an explicit constructor model when provided or otherwise `QA_MODEL`, without embedding credentials or using an Agent.

#### Scenario: Required model configuration is available
- **WHEN** a `QaBuilder` is constructed with all required environment variables
- **THEN** it creates a client that is ready to make Chat Completions requests

#### Scenario: Required configuration is missing
- **WHEN** `QA_API_KEY` is absent or blank, or neither an explicit model nor `QA_MODEL` is available
- **THEN** construction fails with an error identifying the missing variable

#### Scenario: Explicit model is provided
- **WHEN** `QaBuilder(model="gpt-example")` is constructed
- **THEN** requests use `gpt-example` instead of `QA_MODEL`

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
The system SHALL extract the response array, remove Markdown fences, surrounding explanation and full-line `//` comments, accept adjacent JSON objects without commas, validate every object's `content_index` against the current inclusive range, and convert valid objects to ShareGPT records in response order.

#### Scenario: Batch contains questions and aliases
- **WHEN** a batch returns valid `question` or compatible `qestion` fields with indexes inside its range
- **THEN** the system converts and appends every record while retaining each `content_index` and prefixes its human value with `根据 {dataFile} 论文，`

#### Scenario: Saved question identifies the source paper
- **WHEN** `getQA("UBP.pdf")` receives the question `模型采用什么优化器进行训练？`
- **THEN** the saved human value is `根据 UBP.pdf 论文，模型采用什么优化器进行训练？` and the answer remains unchanged

#### Scenario: Batch contains no questions
- **WHEN** a batch returns `[]`
- **THEN** the system accepts the batch and continues with the next range

#### Scenario: Batch response is invalid
- **WHEN** a response is empty text, malformed JSON, not an array, missing required fields, or contains an index outside the active range
- **THEN** the system prints the failed range and a bounded response preview, raises a validation error, and retains records from earlier completed batches

### Requirement: Publish cumulative results after every batch
The system SHALL derive the output filename from the basename stem of `dataFile`, initialize it to an empty UTF-8 JSON array after chunk loading, and atomically replace it with cumulative ShareGPT records after every successful batch.

#### Scenario: PDF source produces a named dataset
- **WHEN** `getQA("UBP.pdf")` succeeds
- **THEN** it writes the complete result to `qa/UBP.json`

#### Scenario: Multiple-dot source preserves its stem
- **WHEN** `getQA("paper.v2.pdf")` succeeds
- **THEN** it writes the complete result to `qa/paper.v2.json`

#### Scenario: Later batch fails
- **WHEN** any batch fails after earlier batches succeeded
- **THEN** the per-document JSON retains all records written by earlier batches in the current run

#### Scenario: Batch progress is visible
- **WHEN** a run starts and each batch begins or completes
- **THEN** a constructor-initialized logger and dedicated `_log` method immediately print and append to `qa/qaBuilder.log` the model, chunk count, range, per-batch count, cumulative count, and output path without credentials or full chunk text

### Requirement: Provide local and live test entry points
The system SHALL provide `qa/test_qaBuilder.py` as a single-function CLI with API smoke and `--datafile` integration modes plus optional `--model` and `--per-chunk` arguments.

#### Scenario: CLI steps are visible and retained
- **WHEN** either live mode runs
- **THEN** the terminal and `qa/test_qaBuilder.log` identify argument parsing, client initialization, the selected operation, completion, and failure

#### Scenario: Run the API smoke check
- **WHEN** the test file runs with `--api-smoke` and an optional `--model`
- **THEN** it sends a minimal live Chat Completions request and reports whether a non-empty answer is returned

#### Scenario: Generate QA for a named source
- **WHEN** the test file runs with `--datafile UBP.pdf` and optional model and batch size arguments
- **THEN** it calls `getQA`, writes `qa/UBP.json` incrementally, and reports progress and the generated record count
