# RAG Retriever

## 运行交互脚本

使用默认模型 `model/corpus/bge-small-zh-v1.5`：

```powershell
python run_retriever.py
```

无 ML 依赖测试时可以使用词法模型：

```powershell
python run_retriever.py --model lexical
```

默认数据库路径：

- 知识库：`data/corpus/corpus.db`
- 向量库：`data/vector/vector.db`

如果两个库不存在，脚本启动时会通过 `Retriever` 自动创建。

## 交互命令

归档单个文档：

```text
归档 doc.txt
```

归档文件夹：

```text
归档 data/raw
```

归档命令会先把文档分块写入知识库，然后调用 `retriever.update()`，为知识库中当前模型下缺失向量的分块补齐向量库记录。

检索最近 7 条结果：

```text
请检索人工智能
```

结果会按序号分隔打印文本内容。

手动更新向量库：

```text
更新
```

退出：

```text
退出
```
