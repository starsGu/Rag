"""Run corpus preprocessing from the command line."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from corpus.documentProcess import (
    CorpusConfig,
    Chunk,
    LexicalSimilarityModel,
    SemanticModelUnavailable,
    load_similarity_model,
    process_corpus,
)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Run corpus document preprocessing.")
    parser.add_argument("--raw-dir", default="data/raw", help="source document directory")
    parser.add_argument("--db-path", default="data/corpus/corpus.db", help="SQLite output path")
    parser.add_argument("--threshold", type=float, default=0.72, help="semantic merge threshold")
    parser.add_argument("--max-paragraphs", type=int, default=6, help="max merged paragraphs")
    parser.add_argument(
        "--model",
        # default="lexical",
        default="data/corpus/bge-small-zh-v1.5",
        help="model path; use 'lexical' to run without ML dependencies",
    )
    parser.add_argument("--preview", type=int, default=10, help="number of saved chunks to preview")
    args = parser.parse_args()

    config = CorpusConfig(
        raw_dir=Path(args.raw_dir),
        db_path=Path(args.db_path),
        corpus_dir=Path(args.db_path).parent,
        model_dir=Path(args.model) if args.model != "lexical" else Path(""),
        model_path=args.model,
        similarity_threshold=args.threshold,
        max_semantic_paragraphs=args.max_paragraphs,
    )

    if args.model != "lexical":
        try:
            similarity_model = load_similarity_model(config.model_dir)
        except SemanticModelUnavailable as exc:
            raise SystemExit(f"Cannot load semantic model: {exc}") from exc
    else:
        similarity_model = LexicalSimilarityModel()

    result = process_corpus(config.raw_dir, config, similarity_model)

    print(f"documents: {len(result.documents)}")
    print(f"load_errors: {len(result.load_errors)}")
    for error in result.load_errors:
        print(f"  - {error.source_name}: {error.reason}")
    print(f"paragraphs: {len(result.paragraphs)}")
    print(f"semantic_chunks: {len(result.semantic_chunks)}")
    print(f"chunks: {len(result.chunks)}")
    print(f"database: {result.db_path}")

    if args.preview > 0:
        print()
        print(f"preview first {args.preview} chunks:")
        _print_preview(result.chunks, args.preview)


def _print_preview(chunks: list[Chunk], limit: int) -> None:
    for chunk in chunks[:limit]:
        preview = chunk.text.replace("\n", " ")[:100]
        print(
            f"[{chunk.source_name} #{chunk.chunk_index} "
            f"{chunk.content_type} {chunk.char_count}] {preview}"
        )


if __name__ == "__main__":
    main()
