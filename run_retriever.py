"""Interactive runner for HybridRetriever."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from corpus.documentProcess import CorpusConfig, process_corpus, process_document
from HybridRetriever import Retriever, RetrieverConfig


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Run HybridRetriever interactively.")
    parser.add_argument("--corpus-db", default="data/corpus/corpus.db", help="corpus SQLite path")
    parser.add_argument("--vector-db", default="data/vector/vector.db", help="vector SQLite path")
    parser.add_argument(
        "--model",
        default="model/corpus/bge-small-zh-v1.5",
        help="model path; use 'lexical' to run without ML dependencies",
    )
    parser.add_argument("--top-k", type=int, default=7, help="number of retrieval results")
    args = parser.parse_args()

    retriever = Retriever(
        RetrieverConfig(
            corpus_db_path=Path(args.corpus_db),
            vector_db_path=Path(args.vector_db),
            model_path=args.model,
        )
    )

    print("输入：归档 doc.txt")
    print("输入：请检索xxx")
    print("输入：更新")
    print("输入：退出")

    while True:
        try:
            command = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not command:
            continue
        if command in {"退出", "exit", "quit"}:
            break

        try:
            if command.startswith("归档"):
                path_text = _strip_quotes(command[len("归档") :].strip())
                if not path_text:
                    print("请提供要归档的文档路径。")
                    continue
                result = _archive_to_corpus(Path(path_text), args)
                retriever.update()
                print(f"归档完成：{len(result.chunks)} 个分块")
                continue

            if command.startswith("请检索"):
                query = command[len("请检索") :].strip()
                if not query:
                    print("请提供检索内容。")
                    continue
                results = retriever.retrieve(query, args.top_k)
                if not results:
                    print("没有检索结果。")
                    continue
                for index, result in enumerate(results, start=1):
                    print(f"[{index}]")
                    print(result.content)
                    if index != len(results):
                        print("-" * 40)
                continue

            if command == "更新":
                retriever.update()
                print("更新完成。")
                continue

            print("无法识别输入。请使用：归档 doc.txt、请检索xxx、更新 或 退出")
        except Exception as exc:
            print(f"错误：{exc}")


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'", "“", "”"}:
        return value[1:-1]
    return value


def _archive_to_corpus(path: Path, args):
    config = CorpusConfig(
        raw_dir=path if path.is_dir() else path.parent,
        corpus_dir=Path(args.corpus_db).parent,
        db_path=Path(args.corpus_db),
        model_dir=Path(args.model) if args.model != "lexical" else Path(""),
        model_path=args.model,
    )
    if path.is_dir():
        return process_corpus(path, config)
    return process_document(path, config)


if __name__ == "__main__":
    main()
