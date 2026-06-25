## ADDED Requirements

### Requirement: 加载原始语料文档
系统 SHALL 从 `data/raw` 加载源文档，并支持 PDF、TXT、DOCX 文件。

#### Scenario: 加载受支持文档
- **WHEN** `data/raw` 下存在 PDF、TXT 或 DOCX 文件
- **THEN** 系统提取其中的文本内容，并为后续分块记录保留来源文件元数据

#### Scenario: 跳过不支持文档
- **WHEN** `data/raw` 下存在不支持扩展名的文件
- **THEN** 系统不将该文件作为语料内容处理，并报告文件类型不支持

### Requirement: 恢复自然段
系统 SHALL 在初步语义分块前规范化文档文本，并把硬换行拆开的连续文本恢复为完整自然段。

#### Scenario: 合并硬换行文本
- **WHEN** TXT 或抽取文本中一个自然段被显示宽度拆成多行
- **THEN** 系统将这些连续文本行合并为同一个自然段

#### Scenario: 保留真实段落边界
- **WHEN** 文本中存在空行、章节标题或明显段落分隔
- **THEN** 系统将其作为自然段边界，不把相邻自然段错误合并

#### Scenario: 保留结构化内容边界
- **WHEN** 文本中存在代码块、列表或表格形态内容
- **THEN** 系统保留其结构边界，供后续内容类型识别和动态分块使用

### Requirement: 初步语义分块
系统 SHALL 基于恢复后的自然段进行初步语义分块，并使用 `model/corpus` 中的已有模型判断相邻自然段语义是否接近，语义接近时合并为同一个初步分块。

#### Scenario: 相邻段落语义相近
- **WHEN** 两个相邻段落的语义相似度达到或超过配置的合并阈值
- **THEN** 系统将两个段落合并到同一个初步分块

#### Scenario: 相邻段落语义不同
- **WHEN** 两个相邻段落的语义相似度低于配置的合并阈值
- **THEN** 系统从后一个段落开始创建新的初步分块

#### Scenario: 连续相近段落达到上限
- **WHEN** 多个连续段落语义相近，并且当前初步分块已达到配置的最大连续段数
- **THEN** 系统强制截断当前初步分块，并从后续段落开始创建新的初步分块

### Requirement: 校准语义相似度阈值
系统 SHALL 将语义相似度阈值作为可配置参数，并提供基于样本文档的阈值校准结果。

#### Scenario: 使用默认阈值
- **WHEN** 用户没有显式配置语义相似度阈值
- **THEN** 系统使用 0.72 作为默认阈值

#### Scenario: 输出校准报告
- **WHEN** 对样本文档执行阈值校准
- **THEN** 系统输出相邻自然段相似度样本、分位数和建议阈值，供人工抽查后调整配置

### Requirement: 二次动态分块
系统 SHALL 根据检测到的内容类型，对初步分块继续细分。

#### Scenario: 代码内容分块
- **WHEN** 初步分块被识别为代码
- **THEN** 系统使用 256 字符分块大小和 64 字符重叠进行拆分

#### Scenario: 表格内容分块
- **WHEN** 初步分块被识别为表格内容
- **THEN** 系统使用 384 字符分块大小和 96 字符重叠进行拆分

#### Scenario: 普通文本分块
- **WHEN** 初步分块被识别为普通文本
- **THEN** 系统使用 512 字符分块大小和 128 字符重叠进行拆分

### Requirement: 添加分块元数据
系统 SHALL 为每个最终分块添加元数据，包括唯一 id 和内容类型。

#### Scenario: 最终分块获得元数据
- **WHEN** 系统创建最终分块
- **THEN** 分块包含 id、内容类型、来源文档引用和分块顺序元数据

### Requirement: 保存处理后的语料
系统 SHALL 将所有最终分块及其元数据保存到 `data/corpus` 下的 SQL 数据库中，用于长期存储。

#### Scenario: 处理成功完成
- **WHEN** 受支持源文档的处理流程完成
- **THEN** 系统将全部最终分块内容和元数据持久化到 `data/corpus` 下的 SQL 数据库

#### Scenario: 保存结果可追溯
- **WHEN** 检查已保存的分块
- **THEN** 系统提供足够元数据，可追溯该分块的来源文档和处理顺序

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
