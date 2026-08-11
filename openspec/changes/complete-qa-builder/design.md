## Context

The corpus pipeline stores ordered document chunks in `data/corpus/corpus.db`. The first QaBuilder implementation sends all matching chunk text in one non-streaming request and asks the model to return every question-answer pair at once. For large documents this creates a long response and an unreliable connection. The updated user plan keeps the whole document in every request but limits the requested output to an inclusive index range.

## Goals / Non-Goals

**Goals:**

- Preserve the complete ordered chunk list as context for every generated answer.
- Process no more than `per_chunk` source indexes per request, defaulting to 50, and merge valid batch results in order.
- Generate one per-document output path such as `qa/UBP.json` and preserve its previous contents unless all batches succeed.
- Keep the direct OpenAI-compatible Chat Completions client and existing ShareGPT record format.

**Non-Goals:**

- Reading, parsing, or uploading the original PDF or another source document.
- Sending only the current chunk slice, streaming responses, parallel batch requests, deduplicating model output, or resuming a partial run.
- Adding an Agent workflow, retry policy, new database schema, or append-only dataset history.

## Decisions

1. **Expose the batch size on `getQA`.** `getQA(dataFile, per_chunk=50)` rejects booleans, non-integers, zero, and negative values. With `N` chunks, the last valid index is `n=N-1`; ranges are `[0,min(49,n)]`, then advance both bounds by `per_chunk` until `n` is covered.
2. **Repeat the full context with a changing range.** Every request uses the full `json.dumps(contents, ensure_ascii=False)` value, followed by a newline and `json.dumps([a,b])`. The system prompt is the exact plan-defined string with all literal `[a, b]` markers replaced by the current numeric range. Requests remain sequential and non-streaming.
3. **Validate against the active range.** Each response must be a JSON array, optionally fenced. An empty array is valid because a batch may produce no questions. Every object must contain a non-empty `question` (with `qestion` retained as a compatibility alias), a non-empty `answer`, and an integer `content_index` within the current inclusive range. Batch records are appended without sorting or deduplication.
4. **Derive a safe per-document output.** The output name is `Path(dataFile).name` with only its final extension replaced by `.json`, placed directly under `qa/`. Thus `UBP.pdf` becomes `qa/UBP.json` and `paper.v2.pdf` becomes `qa/paper.v2.json`; the old generic `qa/datafile.json` is not deleted.
5. **Commit only a complete run.** All batch responses are generated, parsed, validated, and merged in memory before the existing atomic temporary-file replacement runs. Any failure before replacement leaves the document's previous JSON unchanged.

## Risks / Trade-offs

- **Each request repeats the full document** → This satisfies the global-answer requirement but multiplies input tokens by the number of batches.
- **A later batch may fail after earlier batches consumed time and tokens** → Do not publish a partial dataset; surface the error and retain the last complete output.
- **The prompt's illustrative response is not strict JSON** → Continue requiring actual model output to be valid JSON and report parsing failures rather than guessing repairs.
- **A credential was previously written in planning text** → Never copy it into implementation or tests; use only the environment value and rotate exposed credentials.
