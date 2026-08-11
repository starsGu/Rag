## 1. Corpus and Model Integration

- [x] 1.1 Implement dotenv-based OpenAI client initialization and read-only, deterministic chunk loading in `qa/qaBuilder.py` after verifying its `plan/qa/qaBuilder.txt` correspondence.
- [x] 1.2 Implement the exact system prompt and one-shot Chat Completions request containing only the complete JSON chunk list.

## 2. Response and Dataset Handling

- [x] 2.1 Implement fenced/raw JSON parsing, question-answer field validation, index validation, and ShareGPT conversion.
- [x] 2.2 Implement `getQA` orchestration and atomic UTF-8 replacement of the fixed `qa/datafile.json` output while preserving prior data on failure.

## 3. Verification

- [x] 3.1 Add isolated mocked tests for database selection, prompt/request behavior, validation, conversion, overwrite, and failure preservation in `qa/test_qaBuilder.py`.
- [x] 3.2 Add opt-in `--api-smoke` and `--datafile` command-line modes to the same test file.
- [x] 3.3 Run the mocked test suite and OpenSpec validation/status checks, then resolve any failures.

## 4. Batched Generation and Per-Document Output

- [x] 4.1 Implement `getQA(dataFile, per_chunk=50)`, full-context range requests, batch-level validation and merged atomic output at `qa/<dataFile-stem>.json`.
- [x] 4.2 Update `qa/test_qaBuilder.py` for 278-chunk range coverage, full-context requests, empty batches, range validation, dynamic naming and later-batch failure preservation.
- [x] 4.3 Run QA tests, project regressions, strict OpenSpec validation and final apply-status verification.
