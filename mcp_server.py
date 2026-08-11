from fastmcp import FastMCP
import datetime
from pathlib import Path
# from mcp.server.fastmcp import FastMCP

from HybridRetriever import Retriever, RetrieverConfig

retriever = Retriever(
    RetrieverConfig(
        corpus_db_path=Path("data/corpus/corpus.db"),
        vector_db_path=Path("data/vector/vector.db"),
        model_path="model/corpus/bge-small-zh-v1.5",
    )
)
mcp = FastMCP("demo-server")

@mcp.tool()
def get_current_time() -> str:
    """返回当前系统时间（ISO格式）。"""
    return datetime.datetime.now().isoformat()

@mcp.tool()
def get_RAG_result(command: str) -> str:
    """检索"""
    query = command.strip()
    results = retriever.retrieve(query, 5)
    response = ""
    if not results:
        print("没有检索结果。")
        response = "没有检索结果。"
    for index, result in enumerate(results, start=1):
        print(f"[{index}]")
        response = response + f"[{index}]"
        print(result.content)
        response = response + result.content

    return response

# 启动Server（stdio模式，适合本地测试）
if __name__ == "__main__":
    mcp.run(transport="stdio")