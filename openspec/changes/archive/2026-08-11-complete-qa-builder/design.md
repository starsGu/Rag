## Context

The corpus pipeline stores ordered document chunks in `data/corpus/corpus.db`. The first QaBuilder implementation sends all matching chunk text in one non-streaming request and asks the model to return every question-answer pair at once. For large documents this creates a long response and an unreliable connection. The updated user plan keeps the whole document in every request but limits the requested output to an inclusive index range.

## Goals / Non-Goals

**Goals:**

- Preserve the complete ordered chunk list as context for every generated answer.
- Process no more than `per_chunk` source indexes per request, defaulting to 50, and merge valid batch results in order.
- Generate one per-document output path such as `qa/UBP.json`, clear it at run start, and publish cumulative results after each completed batch.
- Keep the direct OpenAI-compatible Chat Completions client and existing ShareGPT record format.
- Keep the implementation deliberately small: four focused `QaBuilder` methods and one CLI `main` function.

**Non-Goals:**

- Reading, parsing, or uploading the original PDF or another source document.
- Sending only the current chunk slice, streaming responses, parallel batch requests, deduplicating model output, or resuming an old run.
- Adding an Agent workflow, retry policy, new database schema, mocked test framework, or append-only dataset history.

## Decisions

1. **Expose the batch size on `getQA`.** `getQA(dataFile, per_chunk=50)` rejects booleans, non-integers, zero, and negative values. With `N` chunks, the last valid index is `n=N-1`; ranges are `[0,min(49,n)]`, then advance both bounds by `per_chunk` until `n` is covered.
2. **Repeat the full context with a changing range.** Every request uses the full `json.dumps(contents, ensure_ascii=False)` value, followed by a newline and `json.dumps([a,b])`. The system prompt is the exact plan-defined string with all literal `[a, b]` markers replaced by the current numeric range. Requests remain sequential and non-streaming.
3. **Parse the format demonstrated by the prompt.** Remove Markdown fences, surrounding explanation, and full-line `//` comments before parsing. First accept strict JSON; if objects are adjacent without commas, decode them sequentially. An empty array is valid. Every object must contain a non-empty `question` (with `qestion` retained as a compatibility alias), a non-empty `answer`, and an integer `content_index` within the active range.
4. **Derive a safe per-document output.** The output name is `Path(dataFile).name` with only its final extension replaced by `.json`, placed directly under `qa/`. Thus `UBP.pdf` becomes `qa/UBP.json` and `paper.v2.pdf` becomes `qa/paper.v2.json`; the old generic `qa/datafile.json` is not deleted.
5. **Publish and log every completed batch.** The constructor initializes terminal and append-mode file logging at `qa/qaBuilder.log`. A dedicated `_log` method emits and flushes each event. `getQA` only reports semantic events through `_log`, while continuing to publish cumulative JSON after every valid batch. Failures retain earlier batches and log the failed range plus a bounded response preview without credentials or full chunk text.
6. **Allow a model override without duplicating configuration.** `QaBuilder(..., model=None)` uses the explicit non-empty model when supplied and otherwise requires `QA_MODEL` from `.env`. The CLI exposes the same value through `--model`.
7. **Keep the code surface minimal.** `QaBuilder` contains only `__init__`, `getQA`, `_parse_response`, and `_log`; `qa/test_qaBuilder.py` contains only `main`, direct command dispatch, step-by-step terminal messages, and an appended `qa/test_qaBuilder.log`.
8. **Identify the source paper in saved questions.** After parsing a batch and before publishing it, prepend `根据 {dataFile} 论文，` to every ShareGPT human value, including one space before and after the filename. Use the exact `dataFile` argument, including its extension; do not alter model requests or answers.

## Risks / Trade-offs

- **Each request repeats the full document** → This satisfies the global-answer requirement but multiplies input tokens by the number of batches.
- **A later batch may fail after earlier batches consumed time and tokens** → Surface the range immediately and retain every batch already published during this run.
- **The prompt's illustrative response contains comments and may omit commas** → Normalize only those demonstrated deviations, then retain field and range validation.
- **A credential was previously written in planning text** → Never copy it into implementation or tests; use only the environment value and rotate exposed credentials.
