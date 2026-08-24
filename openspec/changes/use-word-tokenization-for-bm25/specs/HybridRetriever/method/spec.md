## MODIFIED Requirements

### Requirement: BM25 检索方法
系统 SHALL 按 `plan/HybridRetriever/method.txt` 提供 `bm25_search(query_text, chunks) -> dict[str, float]`，使用一致的词级规则处理查询和分块文本，并基于词频和逆文档频率对关键词匹配进行加权计算，衡量查询和分块之间的相关性。

#### Scenario: 构建中文 BM25 统计
- **WHEN** 系统对包含中文文本的查询和知识库分块执行 BM25 检索
- **THEN** 系统按中文词语切分查询和分块文本，并计算词频、文档频率和 BM25 所需统计信息

#### Scenario: 构建英文和数字 BM25 统计
- **WHEN** 系统对包含英文或数字的查询和知识库分块执行 BM25 检索
- **THEN** 系统按连续英文单词和连续数字切分、统一英文大小写，并过滤空白和标点

#### Scenario: 计算关键词相关性
- **WHEN** 系统已获得查询文本和 `chunk_id -> content` 映射
- **THEN** 系统使用与分块正文完全相同的分词逻辑处理查询，并返回 `chunk_id -> score` 映射
