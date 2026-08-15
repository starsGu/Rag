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

## 5. Minimal Progressive Rewrite

- [x] 5.1 Rewrite `QaBuilder` to three methods with explicit model override, commented-response parsing, terminal/file progress logs, and cumulative atomic writes after every batch.
- [x] 5.2 Replace `qa/test_qaBuilder.py` with one direct CLI `main` supporting `--api-smoke`, `--datafile`, `--model`, and `--per-chunk`.
- [x] 5.3 Verify commented and adjacent-object parsing, progressive failure preservation, CLI syntax, project regression checks, and strict OpenSpec validation.

## 6. Logging Separation

- [x] 6.1 Initialize QaBuilder logging in `__init__`, add one `_log` method, and remove handler management from `getQA`.
- [x] 6.2 Verify method structure, terminal/file logging, regression tests, and strict OpenSpec status.

## 7. Source-Aware Saved Questions

- [x] 7.1 Prefix every saved ShareGPT human question with `根据 {dataFile} 论文，` without changing model requests or answers.
- [x] 7.2 Verify the exact `UBP.pdf` prefix using temporary output only, run regressions, and restore strict OpenSpec `all_done` status.

## 8. Spaced Source Prefix

- [x] 8.1 Normalize all existing human questions in `qa/eegclip.json` and `qa/UBP.json` to use spaces around the exact source filename.
- [x] 8.2 Verify future QaBuilder output uses `根据 {dataFile} 论文，{question}` and restore strict OpenSpec `all_done` status.
