## Why

The project already has corpus document processing, but it does not yet expose a retriever that can archive documents, maintain a vector index, and answer keyword queries from stored chunks. Completing the HybridRetriever plan provides the RAG retrieval layer needed between processed corpus chunks and downstream answer generation.

## What Changes

- Add a singleton-style `Retriever` source module following `plan/HybridRetriever/Retriever.txt`, managing the corpus database at `data/corpus/corpus.db` and the vector database at `data/vector/vector.db`.
- Add archive behavior that accepts a document path, invokes the existing corpus processing interfaces, persists chunks to the corpus database, embeds chunks through the configured model layer, and records vectors.
- Add hybrid retrieval behavior that combines vector similarity and BM25 keyword scoring with a 0.6 / 0.4 weighting and returns the top `k` matching corpus chunks.
- Add update behavior that reconciles the vector database with all chunks currently present in the corpus database.
- Add the same-directory `method` source module following `plan/HybridRetriever/method.txt`, implementing vector search and BM25 scoring.
- Add single-document corpus processing so `Retriever.archive(path)` can process one document path directly.
- Treat the same document processed by different `model_path` values as distinct corpus/vector records.

## Capabilities

### New Capabilities
- `HybridRetriever/Retriever`: 覆盖单例 Retriever、知识库和向量库管理、文档归档、向量库更新和 top-k 混合检索接口。
- `HybridRetriever/method`: 覆盖向量检索和 BM25 检索两种检索编码/评分方法。

### Modified Capabilities
- `corpus/documentProcess`: 增加单文档处理接口，并让 chunk 入库包含 `model_path` 维度。

## Impact

- Affected code: HybridRetriever source structure matching the plan, specifically the `Retriever` module and same-directory `method` module, plus focused tests.
- Affected data: creates or updates `data/corpus/corpus.db` and `data/vector/vector.db`.
- Dependencies: relies on the existing `corpus.documentProcess` public interfaces and the local model/embedding layer available to the project.
