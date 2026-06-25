## ADDED Requirements

### Requirement: 处理单个文档
系统 SHALL 提供 `process_document(path, config=None, similarity_model=None) -> PipelineResult`，用于只处理传入的单个 PDF、TXT 或 DOCX 文档路径，并复用现有文档加载、清洗、语义分块、动态分块、元数据添加和保存流程。

#### Scenario: 处理受支持单文档
- **WHEN** 用户调用 `process_document(path, ...)` 且 `path` 指向受支持文档文件
- **THEN** 系统只处理该文档，并返回包含 `documents`、`load_errors`、`paragraphs`、`semantic_chunks`、`chunks`、`db_path` 的完整 `PipelineResult`

#### Scenario: 路径不存在
- **WHEN** 用户调用 `process_document(path, ...)` 且 `path` 不存在
- **THEN** 系统抛出异常

#### Scenario: 路径是目录
- **WHEN** 用户调用 `process_document(path, ...)` 且 `path` 是目录
- **THEN** 系统抛出异常

#### Scenario: 文件格式不支持
- **WHEN** 用户调用 `process_document(path, ...)` 且文件扩展名不是 PDF、TXT 或 DOCX
- **THEN** 系统抛出异常

#### Scenario: 模型加载失败
- **WHEN** 用户调用 `process_document(path, ...)` 且所需模型无法加载
- **THEN** 系统抛出异常，终端或测试代码负责捕获并打印文本错误

### Requirement: 按模型区分分块入库
系统 SHALL 在 chunk 记录中包含 `model_path`，并将 `model_path` 作为区分处理结果的维度，使同一文档由不同模型处理时可以生成不同入库结果。

#### Scenario: 同文档同模型重复处理
- **WHEN** 用户使用同一 `model_path` 多次处理同一文档内容
- **THEN** 系统不产生重复分块结果

#### Scenario: 同文档不同模型处理
- **WHEN** 用户使用不同 `model_path` 处理同一文档内容
- **THEN** 系统允许生成可区分的 chunk 记录

#### Scenario: 保存模型路径
- **WHEN** 系统保存 chunk 到 `data/corpus/corpus.db`
- **THEN** chunk 记录包含用于生成该处理结果的 `model_path`
