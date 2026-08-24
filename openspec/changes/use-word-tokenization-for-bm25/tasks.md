## 1. Scope and Dependency

- [x] 1.1 Verify the exact correspondence among `plan/HybridRetriever/method.txt`, `HybridRetriever/method.py`, `openspec/specs/HybridRetriever/method/spec.md`, and this change's `specs/HybridRetriever/method/spec.md`, and confirm the artifacts follow the plan.
- [x] 1.2 Declare the jieba runtime dependency and document the installation command without changing unrelated project dependencies.

## 2. BM25 Tokenization

- [x] 2.1 Replace character tokenization in `HybridRetriever/method.py` with one shared tokenizer that uses jieba precise mode for Chinese, lowercased continuous tokens for English and numbers, and excludes whitespace and punctuation.
- [x] 2.2 Keep the public scoring interfaces, BM25 formula, vector scoring, and hybrid retrieval behavior unchanged.

## 3. Verification

- [x] 3.1 Add focused tests in `tests/test_HybridRetriever.py` that distinguish word tokenization from character tokenization and cover Chinese, English, numbers, case normalization, and punctuation filtering.
- [x] 3.2 Run the HybridRetriever tests and the complete test suite, then validate `use-word-tokenization-for-bm25` with OpenSpec strict validation.
