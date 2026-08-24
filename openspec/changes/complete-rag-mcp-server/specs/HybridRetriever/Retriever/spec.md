## MODIFIED Requirements

### Requirement: 归档文档并更新向量库
系统 SHALL 通过 `archive(path)` 接口接收单文档路径，先验证文件路径和格式，再在进程内归档锁中使用去掉最后一个扩展名并忽略大小写的文件名 stem 检查当前 `model_path` 的已有 `chunks.source_name`。同 stem 已存在时返回 `None`；否则调用 `corpus.process_document(path, ...)` 完成文档预处理和分块，将分块保存到知识库，然后调用 `update()` 为当前模型的所有缺失向量补齐记录。

#### Scenario: 归档受支持文档路径
- **WHEN** 用户调用 `archive(path)` 且路径指向当前模型中不存在同 stem 记录的受支持文档
- **THEN** 系统将该文档分块保存到知识库，补齐向量库中当前 `model_path` 的缺失记录，并返回 `PipelineResult`

#### Scenario: 同模型归档同 stem 文档
- **WHEN** 用户使用同一 `model_path` 归档不同目录、扩展名或大小写但无后缀文件名相同的文档
- **THEN** 系统返回 `None`，不处理文档、不写入 chunk 且不生成向量

#### Scenario: 不同模型归档同 stem 文档
- **WHEN** 用户使用不同 `model_path` 归档无后缀文件名相同的文档
- **THEN** 系统将不同模型处理结果视为不同入库结果，并保存可区分的 chunk 和向量记录

#### Scenario: 并发归档同 stem 文档
- **WHEN** 同一 Retriever 进程中两个调用并发归档当前模型的同 stem 文档
- **THEN** 恰好一个调用执行文档处理和写入，另一个返回 `None`

#### Scenario: 非法路径先于重复检查失败
- **WHEN** 路径不存在、指向目录或文件格式不受支持，即使其 stem 已存在
- **THEN** 系统抛出对应的路径或格式异常，而不是返回 `None`
