"""Singleton hybrid retriever over corpus chunks and local vector storage."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Protocol

from corpus.documentProcess import (
    CorpusConfig,
    PipelineResult,
    SimilarityModel,
    process_document,
)

from .method import bm25_search, vector_search


DEFAULT_CORPUS_DB_PATH = Path("data/corpus/corpus.db")
DEFAULT_VECTOR_DB_PATH = Path("data/vector/vector.db")
DEFAULT_MODEL_PATH = "model/corpus/bge-small-zh-v1.5"


class Embedder(Protocol):
    def embed(self, text: str) -> list[float]:
        """Return an embedding vector for text."""


@dataclass(frozen=True)
class RetrieverConfig:
    corpus_db_path: Path = DEFAULT_CORPUS_DB_PATH
    vector_db_path: Path = DEFAULT_VECTOR_DB_PATH
    model_path: str = DEFAULT_MODEL_PATH
    vector_weight: float = 0.6
    bm25_weight: float = 0.4


@dataclass(frozen=True)
class RetrievalResult:
    chunk_id: str
    content: str
    metadata: dict
    model_path: str
    hybrid_score: float
    vector_score: float
    bm25_score: float


class SentenceTransformerEmbedder:
    def __init__(self, model_path: str):
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_path)

    def embed(self, text: str) -> list[float]:
        embedding = self._model.encode([text], normalize_embeddings=True)[0]
        return [float(value) for value in embedding]


class LexicalEmbedder:
    """Deterministic small embedder for tests and local dry-runs."""

    dimension = 64

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        for char in text:
            if char.isspace():
                continue
            digest = hashlib.sha256(char.lower().encode("utf-8")).digest()
            vector[digest[0] % self.dimension] += 1.0
        return vector


class Retriever:
    _instance: "Retriever | None" = None

    def __new__(
        cls,
        config: RetrieverConfig | None = None,
        embedder: Embedder | None = None,
        similarity_model: SimilarityModel | None = None,
    ) -> "Retriever":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(
        self,
        config: RetrieverConfig | None = None,
        embedder: Embedder | None = None,
        similarity_model: SimilarityModel | None = None,
    ) -> None:
        if self._initialized:
            return
        self.config = config or RetrieverConfig()
        self.corpus_db_path = Path(self.config.corpus_db_path)
        self.vector_db_path = Path(self.config.vector_db_path)
        self.model_path = self.config.model_path
        self.vector_weight = self.config.vector_weight
        self.bm25_weight = self.config.bm25_weight
        self.embedder = embedder or self._load_embedder(self.model_path)
        self.similarity_model = similarity_model
        self._archive_lock = threading.Lock()
        self._ensure_storage()
        self._initialized = True

    @classmethod
    def reset_instance(cls) -> None:
        cls._instance = None

    @staticmethod
    def source_key(path: Path | str) -> str:
        return Path(path).stem.casefold()

    def archive(self, path: Path | str) -> PipelineResult | None:
        document_path = self._validate_archive_path(path)
        source_key = self.source_key(document_path)

        with self._archive_lock:
            if self._source_key_exists(source_key):
                return None

            return self._archive_document(document_path)

    def _archive_document(self, path: Path) -> PipelineResult:
        corpus_config = CorpusConfig(
            raw_dir=path.parent,
            corpus_dir=self.corpus_db_path.parent,
            db_path=self.corpus_db_path,
            model_dir=Path(self.model_path) if self.model_path != "lexical" else Path(""),
            model_path=self.model_path,
        )
        result = process_document(path, corpus_config, self.similarity_model)
        self.update()
        return result

    @staticmethod
    def _validate_archive_path(path: Path | str) -> Path:
        document_path = Path(path)
        if not document_path.exists():
            raise FileNotFoundError(f"document not found: {document_path}")
        if not document_path.is_file():
            raise ValueError(f"document path is not a file: {document_path}")
        if document_path.suffix.lower() not in {".txt", ".pdf", ".docx"}:
            raise ValueError(f"unsupported file type: {document_path.suffix.lower()}")
        return document_path

    def _source_key_exists(self, source_key: str) -> bool:
        with closing(self._corpus_connection()) as connection:
            rows = connection.execute(
                "SELECT DISTINCT source_name FROM chunks WHERE model_path = ?",
                (self.model_path,),
            )
            return any(self.source_key(row["source_name"]) == source_key for row in rows)

    def update(self) -> None:
        chunks = self._load_chunks_for_model()
        existing = self._existing_vector_ids()
        missing = [chunk for chunk in chunks if chunk["id"] not in existing]
        self._upsert_vectors(missing)

    def retrieve(self, text: str, k: int) -> list[RetrievalResult]:
        if k < 1:
            raise ValueError("k must be a positive integer")
        candidates = self._load_vector_candidates()
        if not candidates:
            return []

        chunk_vectors = {
            candidate["id"]: self._deserialize_vector(candidate["embedding_json"])
            for candidate in candidates
        }
        chunk_texts = {candidate["id"]: candidate["content"] for candidate in candidates}
        vector_scores = vector_search(self.embedder.embed(text), chunk_vectors)
        bm25_scores = bm25_search(text, chunk_texts)
        normalized_vector = self._normalize_scores(vector_scores)
        normalized_bm25 = self._normalize_scores(bm25_scores)

        rows_by_id = {candidate["id"]: candidate for candidate in candidates}
        ordered_ids = sorted(
            rows_by_id,
            key=lambda chunk_id: (
                self.vector_weight * normalized_vector.get(chunk_id, 0.0)
                + self.bm25_weight * normalized_bm25.get(chunk_id, 0.0),
                normalized_vector.get(chunk_id, 0.0),
                -rows_by_id[chunk_id]["chunk_index"],
            ),
            reverse=True,
        )

        results: list[RetrievalResult] = []
        for chunk_id in ordered_ids[:k]:
            row = rows_by_id[chunk_id]
            vector_score = normalized_vector.get(chunk_id, 0.0)
            bm25_score = normalized_bm25.get(chunk_id, 0.0)
            results.append(
                RetrievalResult(
                    chunk_id=chunk_id,
                    content=row["content"],
                    metadata=json.loads(row["metadata_json"]),
                    model_path=row["model_path"],
                    hybrid_score=self.vector_weight * vector_score + self.bm25_weight * bm25_score,
                    vector_score=vector_score,
                    bm25_score=bm25_score,
                )
            )
        return results

    def print_results(self, results: Iterable[RetrievalResult]) -> None:
        for result in results:
            print(result.content)

    def _ensure_storage(self) -> None:
        self.corpus_db_path.parent.mkdir(parents=True, exist_ok=True)
        self.vector_db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.corpus_db_path)) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS chunks (
                    id TEXT PRIMARY KEY,
                    source_path TEXT NOT NULL,
                    source_name TEXT NOT NULL,
                    content_type TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    char_count INTEGER NOT NULL,
                    paragraph_start_index INTEGER NOT NULL,
                    paragraph_end_index INTEGER NOT NULL,
                    source_start_line INTEGER NOT NULL,
                    source_end_line INTEGER NOT NULL,
                    model_path TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            columns = {row[1] for row in connection.execute("PRAGMA table_info(chunks)").fetchall()}
            if "model_path" not in columns:
                connection.execute("ALTER TABLE chunks ADD COLUMN model_path TEXT NOT NULL DEFAULT ''")
            connection.commit()
        with closing(sqlite3.connect(self.vector_db_path)) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS vectors (
                    chunk_id TEXT NOT NULL,
                    model_path TEXT NOT NULL,
                    embedding_json TEXT NOT NULL,
                    dimension INTEGER NOT NULL,
                    content_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (chunk_id, model_path)
                )
                """
            )
            connection.commit()

    def _upsert_vectors(self, chunks: Iterable) -> None:
        now = datetime.now(timezone.utc).isoformat()
        rows = []
        for chunk in chunks:
            chunk_id = self._chunk_value(chunk, "id")
            content = self._chunk_value(chunk, "text", "content")
            model_path = self._chunk_value(chunk, "model_path") or self.model_path
            embedding = self.embedder.embed(content)
            rows.append(
                {
                    "chunk_id": chunk_id,
                    "model_path": model_path,
                    "embedding_json": self._serialize_vector(embedding),
                    "dimension": len(embedding),
                    "content_hash": self._content_hash(content),
                    "created_at": now,
                    "updated_at": now,
                }
            )
        if not rows:
            return
        with closing(sqlite3.connect(self.vector_db_path)) as connection:
            connection.executemany(
                """
                INSERT INTO vectors (
                    chunk_id, model_path, embedding_json, dimension,
                    content_hash, created_at, updated_at
                )
                VALUES (
                    :chunk_id, :model_path, :embedding_json, :dimension,
                    :content_hash, :created_at, :updated_at
                )
                ON CONFLICT(chunk_id, model_path) DO UPDATE SET
                    embedding_json = excluded.embedding_json,
                    dimension = excluded.dimension,
                    content_hash = excluded.content_hash,
                    updated_at = excluded.updated_at
                """,
                rows,
            )
            connection.commit()

    def _load_chunks_for_model(self) -> list[sqlite3.Row]:
        with closing(self._corpus_connection()) as connection:
            return list(
                connection.execute(
                    "SELECT * FROM chunks WHERE model_path = ? ORDER BY source_path, chunk_index",
                    (self.model_path,),
                )
            )

    def _load_vector_candidates(self) -> list[dict]:
        with closing(sqlite3.connect(self.vector_db_path)) as vector_connection:
            vector_connection.row_factory = sqlite3.Row
            vector_rows = vector_connection.execute(
                "SELECT chunk_id, embedding_json FROM vectors WHERE model_path = ?",
                (self.model_path,),
            ).fetchall()
        if not vector_rows:
            return []

        vectors_by_id = {row["chunk_id"]: row["embedding_json"] for row in vector_rows}
        placeholders = ",".join("?" for _ in vectors_by_id)
        with closing(self._corpus_connection()) as corpus_connection:
            rows = corpus_connection.execute(
                f"""
                SELECT id, content, metadata_json, model_path, chunk_index
                FROM chunks
                WHERE model_path = ? AND id IN ({placeholders})
                """,
                [self.model_path, *vectors_by_id.keys()],
            ).fetchall()

        candidates = []
        for row in rows:
            data = dict(row)
            data["embedding_json"] = vectors_by_id[row["id"]]
            candidates.append(data)
        return candidates

    def _existing_vector_ids(self) -> set[str]:
        with closing(sqlite3.connect(self.vector_db_path)) as connection:
            return {
                row[0]
                for row in connection.execute(
                    "SELECT chunk_id FROM vectors WHERE model_path = ?",
                    (self.model_path,),
                )
            }

    def _corpus_connection(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.corpus_db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _load_embedder(self, model_path: str) -> Embedder:
        if model_path == "lexical":
            return LexicalEmbedder()
        return SentenceTransformerEmbedder(model_path)

    @staticmethod
    def _serialize_vector(vector: list[float]) -> str:
        return json.dumps(vector)

    @staticmethod
    def _deserialize_vector(value: str) -> list[float]:
        return [float(item) for item in json.loads(value)]

    @staticmethod
    def _normalize_scores(scores: dict[str, float]) -> dict[str, float]:
        if not scores:
            return {}
        minimum = min(scores.values())
        maximum = max(scores.values())
        if maximum == minimum:
            return {key: 1.0 if maximum > 0 else 0.0 for key in scores}
        return {key: (value - minimum) / (maximum - minimum) for key, value in scores.items()}

    @staticmethod
    def _content_hash(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    @staticmethod
    def _chunk_value(chunk, *names: str):
        for name in names:
            if isinstance(chunk, dict) and name in chunk:
                return chunk[name]
            if hasattr(chunk, name):
                return getattr(chunk, name)
            try:
                return chunk[name]
            except (KeyError, TypeError, IndexError):
                continue
        raise KeyError(names[0])
