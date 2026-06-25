## ADDED Requirements

### Requirement: 向量检索方法
系统 SHALL 按 `plan/HybridRetriever/method.txt` 提供 `vector_search(query_vector, chunk_vectors) -> dict[str, float]`，通过余弦相似度等度量计算查询与分块之间的语义相似性。

#### Scenario: 查询文本向量化
- **WHEN** 系统执行向量检索
- **THEN** 系统将查询文本转换为与分块向量可比较的高维向量

#### Scenario: 计算语义相似度
- **WHEN** 系统已获得查询向量和 `chunk_id -> vector` 映射
- **THEN** 系统返回 `chunk_id -> score` 映射

### Requirement: BM25 检索方法
系统 SHALL 按 `plan/HybridRetriever/method.txt` 提供 `bm25_search(query_text, chunks) -> dict[str, float]`，暂按字符切分，并基于词频和逆文档频率对关键词匹配进行加权计算，衡量查询和分块之间的相关性。

#### Scenario: 构建 BM25 统计
- **WHEN** 系统对知识库分块执行 BM25 检索
- **THEN** 系统按字符切分查询和分块文本，并计算词频、文档频率和 BM25 所需统计信息

#### Scenario: 计算关键词相关性
- **WHEN** 系统已获得查询文本和 `chunk_id -> content` 映射
- **THEN** 系统返回 `chunk_id -> score` 映射

### Requirement: 输出评分供 Retriever 混合
系统 SHALL 让向量检索和 BM25 检索都返回 `chunk_id -> score`，由 `Retriever` 负责归一化并按照 0.6 向量得分与 0.4 BM25 得分混合排序。

#### Scenario: Retriever 混合评分
- **WHEN** `Retriever` 同时获得向量检索分数和 BM25 检索分数
- **THEN** `Retriever` 按 `0.6 * vector_score + 0.4 * bm25_score` 计算混合分数
