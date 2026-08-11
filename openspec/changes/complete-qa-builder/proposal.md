## Why

`qa/qaBuilder.py` can generate ShareGPT data, but asking for every chunk's questions in one response makes large documents slow and vulnerable to long-response connection failures. This change keeps the full paper available as context while limiting each response to a configurable index range.

## What Changes

- Load every `chunks.content` row for an exact `source_name` match from the corpus SQLite database in deterministic order.
- Send the complete JSON chunk list repeatedly while processing inclusive index ranges of `per_chunk` chunks, defaulting to 50.
- Inject the current `[a,b]` range into the plan-defined prompt, validate every response against that range, and merge the resulting ShareGPT conversations in batch order.
- Atomically replace `qa/<dataFile-stem>.json` after all batches succeed while preserving the prior per-document file on failure.
- Add mocked unit coverage plus explicit API-smoke and `--datafile` integration entry points under `qa/`.

## Capabilities

### New Capabilities

- `qa/qaBuilder`: Generate validated ShareGPT question-answer records from all stored chunks belonging to one source filename.

### Modified Capabilities

None.

## Impact

- Affects `qa/qaBuilder.py`, `qa/test_qaBuilder.py`, and generated per-document JSON artifacts such as `qa/UBP.json`.
- Uses the existing corpus database schema and adds runtime use of the OpenAI Python client and python-dotenv.
- Introduces `QA_BASE_URL`, `QA_API_KEY`, and `QA_MODEL` environment configuration without changing existing retrieval APIs.
