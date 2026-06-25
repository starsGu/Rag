## Context

The repository currently contains a `corpus` package with document loading, paragraph recovery, semantic chunking, dynamic chunking, metadata enrichment, and SQLite persistence. The HybridRetriever plan already defines the source and spec structure: `plan/HybridRetriever/Retriever.txt` maps to `specs/HybridRetriever/Retriever/spec.md`, and `plan/HybridRetriever/method.txt` maps to `specs/HybridRetriever/method/spec.md`.

The implementation should stay local and testable. Database paths default to `data/corpus/corpus.db` and `data/vector/vector.db`, and `model_path` defaults to `model/corpus/bge-small-zh-v1.5`; tests should be able to point the retriever at temporary paths and use `lexical` or deterministic stub embedders.

## Goals / Non-Goals

**Goals:**
- Provide a singleton-style `Retriever` API matching `plan/HybridRetriever/Retriever.txt`, with `archive(path)`, `retrieve(text, k)`, and `update()` methods.
- Add and reuse `corpus.documentProcess.process_document(path, ...)` for single-document preprocessing and chunk persistence.
- Store vector records in SQLite with stable `(chunk_id, model_path)` links back to corpus chunks.
- Treat the same document processed by different `model_path` values as different corpus/vector records.
- Implement vector similarity and BM25 helpers in the same-directory `method` module matching `plan/HybridRetriever/method.txt`, then combine scores from `Retriever` with the planned 0.6 vector / 0.4 BM25 weighting.
- Make retrieval deterministic under tests by allowing injected embedding and corpus-processing dependencies.

**Non-Goals:**
- Building answer generation, prompt assembly, or chat UI behavior.
- Replacing the existing corpus document processing pipeline.
- Introducing a remote vector database or external search service.
- Changing existing corpus requirements unless a later implementation discovers an actual contract gap.

## Decisions

1. Implement the source and spec structure directly from `plan/HybridRetriever`.

   Rationale: the plan already defines the intended layout. `Retriever` owns the public facade and database management, while the same-directory `method` module owns vector retrieval and BM25 retrieval. The spec structure should mirror this layout, as the archived corpus change mirrors `plan/corpus/documentProcess.txt`.

   Alternative considered: invent a broader package layout. That is unnecessary for this change because the plan structure is enough and should drive both source and spec.

2. Use SQLite for the vector database at `data/vector/vector.db`.

   Rationale: the plan explicitly names a local vector database path, and SQLite matches the existing persistence style. It is simple to inspect in tests and avoids adding infrastructure.

   Alternative considered: use an in-memory index only. That would be easier initially, but it would not satisfy update/reconciliation or persistence requirements.

3. Store vector rows keyed by `(chunk_id, model_path)`.

   Rationale: corpus chunks are the only retrievable text records, while `model_path` distinguishes embeddings and chunk records created by different models. Using `(chunk_id, model_path)` lets `update()` find missing embeddings for the current model and lets `retrieve()` return corpus chunk records instead of vector-only data.

   Alternative considered: key vectors only by `chunk_id`. That would prevent multiple model outputs from coexisting for the same document/content.

4. Make embedding a small injectable interface.

   Rationale: production retrieval needs model-backed embeddings, while tests need fast deterministic vectors. An injected embedder keeps the retriever testable without hiding model-loading failures in real usage.

   Alternative considered: instantiate the model directly inside every retriever method. That is simpler but slower and harder to test.

5. Normalize vector and BM25 scores before weighted merging.

   Rationale: cosine similarity and BM25 use different scales. Normalization makes the 0.6 / 0.4 weighting meaningful and stable across queries.

   Alternative considered: add raw scores directly. Raw-score blending can let BM25 dominate because its score range is query/corpus dependent.

## Risks / Trade-offs

- Model dependency availability -> Keep embedding injectable and fail explicitly when the configured model cannot be loaded.
- Corpus/vector drift -> `update()` scans current-model corpus chunk ids and creates missing `(chunk_id, model_path)` vector rows; stale vectors are not deleted and retrieval ignores vectors that cannot join current chunks.
- Duplicate archive calls -> include `model_path` in chunk identity so same-document same-model archive deduplicates while different models can coexist.
- BM25 tokenization quality for Chinese text -> start with a lightweight helper inside the planned `method` module, keeping future tokenizer changes isolated there.
- Large corpus performance -> SQLite scans are acceptable for the current local scope; indexing and batching can be added later without changing the public retriever API.
