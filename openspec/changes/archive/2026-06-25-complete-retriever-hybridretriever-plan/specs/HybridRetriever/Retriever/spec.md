## ADDED Requirements

### Requirement: 初始化 Retriever 存储
系统 SHALL 按 `plan/HybridRetriever/Retriever.txt` 提供 Java 风格单例 `Retriever`，并在创建时检查知识库 `data/corpus/corpus.db` 与向量库 `data/vector/vector.db` 是否存在，不存在时创建对应目录和数据库结构。

#### Scenario: 默认数据库不存在
- **WHEN** 用户创建 `Retriever`
- **THEN** 系统创建 `data/corpus/corpus.db` 和 `data/vector/vector.db` 所需的父目录与数据库表

#### Scenario: 数据库已经存在
- **WHEN** 用户创建 `Retriever` 且两个数据库已经存在
- **THEN** 系统复用现有数据库，不删除已有语料分块或向量记录

#### Scenario: 重复创建 Retriever
- **WHEN** 用户多次创建 `Retriever`
- **THEN** 系统返回同一个全局实例

### Requirement: 维护知识库和向量库关联
系统 SHALL 以 `chunks` 作为唯一可检索文本入口，并让向量库通过 `(chunk_id, model_path)` 关联到知识库中对应的 chunk 文本。

#### Scenario: 创建知识库 chunk 表
- **WHEN** 系统初始化知识库
- **THEN** `chunks` 表至少支持 `id`、`content`、`metadata_json`、`source_path`、`source_name`、`chunk_index`、`model_path`、`created_at` 字段

#### Scenario: 创建向量表
- **WHEN** 系统初始化向量库
- **THEN** `vectors` 表至少支持 `chunk_id`、`model_path`、`embedding_json`、`dimension`、`content_hash`、`created_at`、`updated_at` 字段，并使用 `(chunk_id, model_path)` 作为主键

#### Scenario: 通过向量回查文本
- **WHEN** 系统从向量库获得候选 `chunk_id`
- **THEN** 系统通过 `chunk_id` JOIN 当前知识库 `chunks` 表，读取对应 `content` 和 `metadata_json`

### Requirement: 归档文档并更新向量库
系统 SHALL 通过 `archive(path)` 接口接收单文档路径，调用 `corpus.process_document(path, ...)` 完成文档预处理和分块，将分块保存到知识库，然后调用 `update()` 为知识库中当前 `model_path` 下所有缺失向量的分块补齐向量记录。

#### Scenario: 归档受支持文档路径
- **WHEN** 用户调用 `archive(path)` 且路径指向受支持文档
- **THEN** 系统将该文档分块保存到 `data/corpus/corpus.db`，并通过 `update()` 补齐 `data/vector/vector.db` 中当前 `model_path` 的缺失向量记录

#### Scenario: 重复归档同一文档
- **WHEN** 用户使用同一 `model_path` 多次调用 `archive(path)` 归档同一文档内容
- **THEN** 系统不返回重复检索结果，并保持语料分块 id 与向量记录的对应关系稳定

#### Scenario: 不同模型归档同一文档
- **WHEN** 用户使用不同 `model_path` 归档同一文档内容
- **THEN** 系统将不同模型处理结果视为不同入库结果，并保存可区分的 chunk 和向量记录

### Requirement: 更新向量库
系统 SHALL 提供 `update()` 接口，确保知识库中当前 `model_path` 的所有分块在向量库中都有对应 `(chunk_id, model_path)` 向量记录，并且不删除旧向量。

#### Scenario: 知识库存在缺失向量的分块
- **WHEN** 用户调用 `update()` 且 `data/corpus/corpus.db` 中存在当前 `model_path` 下没有向量记录的分块
- **THEN** 系统为缺失分块生成向量并写入 `data/vector/vector.db`

#### Scenario: 向量库已同步
- **WHEN** 用户调用 `update()` 且所有分块都已有向量记录
- **THEN** 系统不重复写入已有向量记录

#### Scenario: 向量库存在旧向量
- **WHEN** 用户调用 `update()` 且向量库中存在没有当前 chunk 对应关系或模型不匹配的旧向量
- **THEN** 系统不删除旧向量

### Requirement: 执行混合检索
系统 SHALL 提供 `retrieve(str, k)` 接口，使用同目录 `method` 中的向量检索和 BM25 检索方法分别评分，并按 0.6 向量得分与 0.4 BM25 得分的权重合并，从知识库返回当前 `model_path` 下最相关的 `k` 个完整结果。

#### Scenario: 返回 top-k 分块
- **WHEN** 用户调用 `retrieve(str, k)` 且知识库中存在相关分块
- **THEN** 系统返回按混合得分降序排列的最多 `k` 个结果，每个结果包含 `chunk_id`、`content`、`metadata`、`model_path`、`hybrid_score`、`vector_score`、`bm25_score`

#### Scenario: 过滤非当前模型向量
- **WHEN** 用户调用 `retrieve(str, k)` 且向量库中存在其他 `model_path` 的向量
- **THEN** 系统只使用当前 `Retriever.model_path` 对应的向量参与检索

#### Scenario: 忽略无对应文本的旧向量
- **WHEN** 用户调用 `retrieve(str, k)` 且向量库中存在无法 JOIN 到当前 `chunks` 表的旧向量
- **THEN** 系统不返回这些旧向量对应的结果

#### Scenario: 终端打印结果
- **WHEN** 测试或终端展示 `retrieve(str, k)` 返回结果
- **THEN** 系统只打印每个结果的 `content` 文本

#### Scenario: 查询空知识库
- **WHEN** 用户调用 `retrieve(str, k)` 且知识库没有任何分块
- **THEN** 系统返回空结果列表

#### Scenario: k 小于一
- **WHEN** 用户调用 `retrieve(str, k)` 且 `k` 小于 1
- **THEN** 系统拒绝该请求并报告 `k` 必须为正整数
