## 1. HybridRetriever Source Structure

- [x] 1.1 Create the HybridRetriever source files following `plan/HybridRetriever`: `Retriever` for the singleton facade and same-directory `method` for retrieval methods.
- [x] 1.2 Add retriever configuration for corpus DB path, vector DB path, embedding model path, and hybrid score weights with defaults matching `plan/HybridRetriever/Retriever.txt`.
- [x] 1.3 Implement Java-style singleton behavior so repeated `Retriever` creation returns one global instance.
- [x] 1.4 Implement initialization that creates parent directories and SQLite tables for `data/corpus/corpus.db` and `data/vector/vector.db` without deleting existing records.
- [x] 1.5 Create the vector table with `(chunk_id, model_path)` as the primary key and fields for embedding JSON, dimension, content hash, created time, and updated time.
- [x] 1.6 Add tests that verify initialization creates missing database files, preserves existing corpus/vector records, and enforces singleton behavior.

## 2. Embedding and Method Helpers

- [x] 2.1 Define an injectable embedding interface with a production model-backed implementation and deterministic test stub support.
- [x] 2.2 Implement vector serialization/deserialization and `vector_search(query_vector, chunk_vectors) -> dict[str, float]`.
- [x] 2.3 Implement character-level `bm25_search(query_text, chunks) -> dict[str, float]` in the planned same-directory `method` module.
- [x] 2.4 Implement score normalization and weighted merge logic using 0.6 vector score and 0.4 BM25 score.
- [x] 2.5 Add unit tests for vector scoring, BM25 scoring, normalization, and weighted ranking.

## 3. Corpus Archive and Update Behavior

- [x] 3.1 Implement `corpus.documentProcess.process_document(path, config=None, similarity_model=None)` for a single document path.
- [x] 3.2 Include `model_path` in chunk records and chunk id generation so same-document same-model processing deduplicates while different models can produce distinct records.
- [x] 3.3 Implement `Retriever.archive(path)` so it calls `process_document(path, ...)` to persist chunks, then calls `update()` to fill all missing vectors for the current `model_path`.
- [x] 3.4 Implement vector upsert behavior keyed by `(chunk_id, model_path)` so archived chunks receive vector records without duplicates for the same model.
- [x] 3.5 Implement `Retriever.update()` to scan current-model corpus chunks and generate vectors missing from the vector database without deleting old vectors.
- [x] 3.6 Add tests for single-document archive, same-model dedupe, different-model distinct records, missing-vector reconciliation, and no-op update when already synchronized.

## 4. Retrieval Behavior

- [x] 4.1 Implement `Retriever.retrieve(text, k)` validation, returning an error for `k < 1`.
- [x] 4.2 Load only current `model_path` vectors and JOIN current `chunks` rows so stale vectors or model-mismatched vectors are not returned.
- [x] 4.3 Combine vector and BM25 results into a descending top-k list that returns `chunk_id`, `content`, `metadata`, `model_path`, `hybrid_score`, `vector_score`, and `bm25_score`.
- [x] 4.4 Print only result `content` text in terminal/test display helpers.
- [x] 4.5 Return an empty list when retrieval is called against an empty corpus.
- [x] 4.6 Add end-to-end tests that archive sample documents and verify top-k hybrid retrieval ordering, metadata, model filtering, and stale-vector filtering.

## 5. Verification

- [x] 5.1 Verify the implementation source structure matches `plan/HybridRetriever` and the specs under `specs/HybridRetriever/Retriever` and `specs/HybridRetriever/method`.
- [x] 5.2 Run the existing corpus tests to ensure retriever work does not regress document processing.
- [x] 5.3 Run the new retriever test suite and verify all HybridRetriever OpenSpec scenarios are covered.
