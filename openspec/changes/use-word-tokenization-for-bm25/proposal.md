## Why

当前 BM25 将中文和英文都按单个字符切分，无法按中文词语或英文单词表达关键词匹配关系，降低了关键词检索的可解释性和准确性。需要让查询文本与语料分块使用一致的词级分词规则。

## What Changes

- 将 BM25 的字符切分替换为统一的混合文本分词：中文使用 jieba 精确模式，英文和数字按连续单词切分并转为小写。
- 过滤空白和标点，确保查询文本与分块正文通过同一个分词入口处理。
- 增加中文词语、英文单词、数字、大小写和标点处理的测试覆盖。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `HybridRetriever/method`: BM25 的查询和分块分词由字符级改为一致的中文词语及英文/数字单词级规则。

## Impact

- 修改 `HybridRetriever/method.py` 的 BM25 分词实现。
- 修改 `tests/test_HybridRetriever.py` 的 BM25 测试覆盖。
- 增加 jieba 运行时依赖；`vector_search`、BM25 公式、评分返回结构及 Retriever 的 0.6/0.4 混合逻辑保持不变。
