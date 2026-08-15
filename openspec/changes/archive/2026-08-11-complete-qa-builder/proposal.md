## Why

`qa/qaBuilder.py` can generate ShareGPT data, but asking for every chunk's questions in one response makes large documents slow and vulnerable to long-response connection failures. This change keeps the full paper available as context while limiting each response to a configurable index range.

## What Changes

- Load every `chunks.content` row for an exact `source_name` match from the corpus SQLite database in deterministic order.
- Send the complete JSON chunk list repeatedly while processing inclusive index ranges of `per_chunk` chunks, defaulting to 50.
- Inject the current `[a,b]` range into the plan-defined prompt, validate every response against that range, and merge the resulting ShareGPT conversations in batch order.
- Clear `qa/<dataFile-stem>.json` at the start of a valid run, then atomically publish the cumulative records after every successful batch so later failures retain completed work.
- Accept an explicit model override, parse the prompt's commented JSON examples, print and persist live batch progress, and reduce the test file to direct API-smoke and `--datafile` entry points.
- Initialize logging in the constructor and route all QaBuilder progress through one `_log` method instead of embedding handler management in `getQA`.
- Prefix each saved ShareGPT human question with `根据 {dataFile} 论文，` while leaving the model request and answer unchanged.

## Capabilities

### New Capabilities

- `qa/qaBuilder`: Generate validated ShareGPT question-answer records from all stored chunks belonging to one source filename.

### Modified Capabilities

None.

## Impact

- Affects `qa/qaBuilder.py`, `qa/test_qaBuilder.py`, and generated per-document JSON artifacts such as `qa/UBP.json`.
- Uses the existing corpus database schema and adds runtime use of the OpenAI Python client and python-dotenv.
- Uses `QA_BASE_URL`, `QA_API_KEY`, and `QA_MODEL`, with an optional constructor model override.
