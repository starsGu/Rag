# 语料库查看说明

本次变更计划使用 `data/corpus/corpus.db` 作为本地 SQL 语料库。建议首版使用 SQLite，方便直接用 SQL 命令或可视化工具查看分块内容。

## 推荐表结构

分块表建议命名为 `chunks`，至少包含以下字段：

```text
id
source_path
source_name
content_type
chunk_index
content
char_count
metadata_json
created_at
```

这些字段中，`content`、`source_name`、`content_type`、`chunk_index` 必须单独成列，不建议全部塞进 JSON 字段，否则后续 SQL 查询和人工抽查会很不直观。

## 常用 SQL 查询

查看前 20 条分块预览：

```sql
SELECT
  id,
  source_name,
  content_type,
  chunk_index,
  char_count,
  substr(replace(content, char(10), ' '), 1, 120) AS preview
FROM chunks
ORDER BY source_name, chunk_index
LIMIT 20;
```

查看某个分块的完整内容：

```sql
SELECT content
FROM chunks
WHERE id = '某个chunk_id';
```

按来源文档统计分块数量和平均长度：

```sql
SELECT
  source_name,
  count(*) AS chunk_count,
  avg(char_count) AS avg_chars
FROM chunks
GROUP BY source_name
ORDER BY source_name;
```

按内容类型统计分块数量：

```sql
SELECT
  content_type,
  count(*) AS chunk_count
FROM chunks
GROUP BY content_type
ORDER BY chunk_count DESC;
```

查看某个来源文档的连续分块：

```sql
SELECT
  chunk_index,
  content_type,
  char_count,
  content
FROM chunks
WHERE source_name = '某个文件名'
ORDER BY chunk_index;
```

查找包含关键词的分块：

```sql
SELECT
  id,
  source_name,
  content_type,
  chunk_index,
  substr(replace(content, char(10), ' '), 1, 160) AS preview
FROM chunks
WHERE content LIKE '%关键词%'
ORDER BY source_name, chunk_index
LIMIT 50;
```

检查分块是否过短或过长：

```sql
SELECT
  id,
  source_name,
  content_type,
  chunk_index,
  char_count
FROM chunks
WHERE char_count < 50 OR char_count > 800
ORDER BY char_count DESC;
```

## 命令行查看方式

如果本机安装了 SQLite 命令行工具，可以这样打开数据库：

```powershell
sqlite3 data/corpus/corpus.db
```

进入 SQLite 后可以先查看表：

```sql
.tables
.schema chunks
```

再执行上面的查询语句。

## 可视化工具

推荐以下工具直接打开 `data/corpus/corpus.db`：

- DB Browser for SQLite：最直观，适合直接点开表格查看分块正文。
- DBeaver：功能更完整，后续如果切换 MySQL 或 PostgreSQL 也能继续使用。
- VS Code SQLite Viewer 插件：适合在编辑器里快速查看数据库内容。

首版实现时应优先保证 SQL 查询结果可读，方便人工抽查分块质量、内容类型识别结果和来源追溯信息。
