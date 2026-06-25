"""Chinese corpus document preprocessing.

This module follows ``plan/corpus/documentProcess.txt``:
load raw documents, recover natural paragraphs, run semantic chunking,
perform content-type-aware splitting, add metadata, and persist chunks to
SQLite for inspection.
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
import uuid
import zipfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Protocol
from xml.etree import ElementTree


DEFAULT_RAW_DIR = Path("data/raw")
DEFAULT_CORPUS_DIR = Path("data/corpus")
DEFAULT_DB_PATH = DEFAULT_CORPUS_DIR / "corpus.db"
DEFAULT_MODEL_DIR = Path("model/corpus")


@dataclass(frozen=True)
class CorpusConfig:
    raw_dir: Path = DEFAULT_RAW_DIR
    corpus_dir: Path = DEFAULT_CORPUS_DIR
    db_path: Path = DEFAULT_DB_PATH
    model_dir: Path = DEFAULT_MODEL_DIR
    model_path: str = str(DEFAULT_MODEL_DIR)
    similarity_threshold: float = 0.72
    max_semantic_paragraphs: int = 6
    code_chunk_size: int = 256
    code_overlap: int = 64
    table_chunk_size: int = 384
    table_overlap: int = 96
    text_chunk_size: int = 512
    text_overlap: int = 128


@dataclass(frozen=True)
class Document:
    text: str
    source_path: str
    source_name: str
    extension: str
    document_index: int


@dataclass(frozen=True)
class LoadError:
    source_path: str
    source_name: str
    extension: str
    reason: str


@dataclass(frozen=True)
class Paragraph:
    text: str
    block_type: str
    source_path: str
    source_name: str
    source_start_line: int
    source_end_line: int
    paragraph_index: int = 0


@dataclass(frozen=True)
class SemanticChunk:
    text: str
    block_type: str
    source_path: str
    source_name: str
    paragraph_start_index: int
    paragraph_end_index: int
    source_start_line: int
    source_end_line: int


@dataclass
class Chunk:
    text: str
    content_type: str
    source_path: str
    source_name: str
    paragraph_start_index: int
    paragraph_end_index: int
    source_start_line: int
    source_end_line: int
    chunk_index: int
    char_count: int
    id: str = ""
    model_path: str = ""
    created_at: str = ""
    metadata_json: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PipelineResult:
    documents: list[Document]
    load_errors: list[LoadError]
    paragraphs: list[Paragraph]
    semantic_chunks: list[SemanticChunk]
    chunks: list[Chunk]
    db_path: str


@dataclass(frozen=True)
class CalibrationReport:
    samples: list[dict[str, Any]]
    percentiles: dict[str, float]
    suggested_threshold: float
    sample_count: int


class SimilarityModel(Protocol):
    def similarity(self, left: str, right: str) -> float:
        """Return cosine-like similarity in the 0..1 range."""


class SemanticModelUnavailable(RuntimeError):
    """Raised when a real semantic model cannot be loaded."""


class _SentenceTransformerSimilarity:
    def __init__(self, model_dir: Path):
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(str(model_dir))

    def similarity(self, left: str, right: str) -> float:
        embeddings = self._model.encode([left, right], normalize_embeddings=True)
        return float(embeddings[0] @ embeddings[1])


class LexicalSimilarityModel:
    """Small deterministic model for tests and threshold dry-runs."""

    def similarity(self, left: str, right: str) -> float:
        left_tokens = _lexical_tokens(left)
        right_tokens = _lexical_tokens(right)
        if not left_tokens or not right_tokens:
            return 0.0
        overlap = len(left_tokens & right_tokens)
        return overlap / math.sqrt(len(left_tokens) * len(right_tokens))


def load_similarity_model(model_dir: Path = DEFAULT_MODEL_DIR) -> SimilarityModel:
    """Load the configured semantic model.

    The downloaded BGE model needs either sentence-transformers or transformers.
    Keep failure explicit so production chunking does not silently degrade.
    """

    if not model_dir.exists():
        raise SemanticModelUnavailable(f"model directory not found: {model_dir}")
    try:
        return _SentenceTransformerSimilarity(model_dir)
    except ModuleNotFoundError as exc:
        raise SemanticModelUnavailable(
            "sentence-transformers is required to load the semantic model"
        ) from exc
    except Exception as exc:
        raise SemanticModelUnavailable(f"failed to load semantic model from {model_dir}: {exc}") from exc


def load_documents(raw_dir: Path | str = DEFAULT_RAW_DIR) -> tuple[list[Document], list[LoadError]]:
    raw_path = Path(raw_dir)
    documents: list[Document] = []
    errors: list[LoadError] = []
    supported = {".txt", ".pdf", ".docx"}

    if not raw_path.exists():
        return documents, [LoadError(str(raw_path), raw_path.name, "", "raw directory not found")]

    files = [p for p in sorted(raw_path.iterdir()) if p.is_file()]
    for index, path in enumerate(files):
        ext = path.suffix.lower()
        if ext not in supported:
            errors.append(_load_error(path, "unsupported file type"))
            continue
        try:
            documents.append(_load_document_file(path, index))
        except Exception as exc:  # keep processing other files
            errors.append(_load_error(path, str(exc)))
    return documents, errors


def load_document(path: Path | str) -> Document:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"document not found: {file_path}")
    if not file_path.is_file():
        raise ValueError(f"document path is not a file: {file_path}")
    if file_path.suffix.lower() not in {".txt", ".pdf", ".docx"}:
        raise ValueError(f"unsupported file type: {file_path.suffix.lower()}")
    return _load_document_file(file_path, 0)


def clean_document_text(document: Document) -> list[Paragraph]:
    text = normalize_text(document.text)
    raw_lines = text.split("\n")
    units = _line_units(raw_lines)
    paragraphs: list[Paragraph] = []
    buffer: list[tuple[str, int]] = []

    def flush_buffer() -> None:
        nonlocal buffer
        if not buffer:
            return
        merged = _join_wrapped_lines([line for line, _ in buffer])
        if merged:
            paragraphs.append(
                Paragraph(
                    text=merged,
                    block_type="text",
                    source_path=document.source_path,
                    source_name=document.source_name,
                    source_start_line=buffer[0][1],
                    source_end_line=buffer[-1][1],
                    paragraph_index=len(paragraphs),
                )
            )
        buffer = []

    index = 0
    while index < len(units):
        unit = units[index]
        line = unit["line"]
        line_no = unit["line_no"]
        kind = unit["kind"]

        if kind == "blank":
            flush_buffer()
            index += 1
            continue

        if kind == "underline" and paragraphs:
            index += 1
            continue

        if kind in {"title", "code", "list", "table"}:
            flush_buffer()
            block_lines = [(line, line_no)]
            index += 1
            while index < len(units) and units[index]["kind"] == kind:
                block_lines.append((units[index]["line"], units[index]["line_no"]))
                index += 1
            block_text = "\n".join(value for value, _ in block_lines)
            paragraphs.append(
                Paragraph(
                    text=block_text,
                    block_type=kind,
                    source_path=document.source_path,
                    source_name=document.source_name,
                    source_start_line=block_lines[0][1],
                    source_end_line=block_lines[-1][1],
                    paragraph_index=len(paragraphs),
                )
            )
            continue

        buffer.append((line, line_no))
        index += 1

    flush_buffer()
    return paragraphs


def semantic_chunk_paragraphs(
    paragraphs: Iterable[Paragraph],
    similarity_model: SimilarityModel,
    config: CorpusConfig | None = None,
) -> list[SemanticChunk]:
    cfg = config or CorpusConfig()
    items = list(paragraphs)
    if not items:
        return []

    chunks: list[SemanticChunk] = []
    current = [items[0]]

    for paragraph in items[1:]:
        previous = current[-1]
        force_boundary = len(current) >= cfg.max_semantic_paragraphs
        same_structural_type = previous.block_type == paragraph.block_type == "text"
        score = (
            similarity_model.similarity(previous.text, paragraph.text)
            if same_structural_type and not force_boundary
            else 0.0
        )
        if same_structural_type and score >= cfg.similarity_threshold and not force_boundary:
            current.append(paragraph)
        else:
            chunks.append(_semantic_chunk_from_paragraphs(current))
            current = [paragraph]

    chunks.append(_semantic_chunk_from_paragraphs(current))
    return chunks


def calibrate_similarity_threshold(
    paragraphs: Iterable[Paragraph],
    similarity_model: SimilarityModel,
    sample_limit: int = 200,
) -> CalibrationReport:
    items = list(paragraphs)
    pairs = list(zip(items, items[1:]))
    samples: list[dict[str, Any]] = []
    for left, right in pairs[:sample_limit]:
        score = similarity_model.similarity(left.text, right.text)
        samples.append(
            {
                "left_index": left.paragraph_index,
                "right_index": right.paragraph_index,
                "similarity": round(float(score), 6),
                "left_preview": left.text[:80],
                "right_preview": right.text[:80],
            }
        )

    values = sorted(item["similarity"] for item in samples)
    percentiles = {
        "p50": _percentile(values, 0.50),
        "p75": _percentile(values, 0.75),
        "p90": _percentile(values, 0.90),
        "p95": _percentile(values, 0.95),
    }
    suggested = percentiles["p75"] if values else 0.72
    return CalibrationReport(samples, percentiles, round(float(suggested), 6), len(samples))


def dynamic_chunk(semantic_chunks: Iterable[SemanticChunk], config: CorpusConfig | None = None) -> list[Chunk]:
    cfg = config or CorpusConfig()
    chunks: list[Chunk] = []
    chunk_index = 0
    for semantic in semantic_chunks:
        content_type = detect_content_type(semantic.text, semantic.block_type)
        size, overlap = _chunk_profile(content_type, cfg)
        for piece in _split_with_overlap(semantic.text, size, overlap):
            chunks.append(
                Chunk(
                    text=piece,
                    content_type=content_type,
                    source_path=semantic.source_path,
                    source_name=semantic.source_name,
                    paragraph_start_index=semantic.paragraph_start_index,
                    paragraph_end_index=semantic.paragraph_end_index,
                    source_start_line=semantic.source_start_line,
                    source_end_line=semantic.source_end_line,
                    chunk_index=chunk_index,
                    char_count=len(piece),
                )
            )
            chunk_index += 1
    return chunks


def add_metadata(chunks: Iterable[Chunk], model_path: str = str(DEFAULT_MODEL_DIR)) -> list[Chunk]:
    created_at = datetime.now(timezone.utc).isoformat()
    enriched: list[Chunk] = []
    source_counts: dict[str, int] = {}
    model_key = model_path or str(DEFAULT_MODEL_DIR)
    for chunk in chunks:
        source_key = chunk.source_path
        chunk.chunk_index = source_counts.get(source_key, 0)
        source_counts[source_key] = chunk.chunk_index + 1
        chunk.char_count = len(chunk.text)
        chunk.model_path = model_key
        chunk.created_at = created_at
        chunk.id = str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"{chunk.source_path}:{chunk.paragraph_start_index}:{chunk.paragraph_end_index}:{chunk.chunk_index}:{model_key}:{chunk.text}",
            )
        )
        chunk.metadata = {
            "source_path": chunk.source_path,
            "source_name": chunk.source_name,
            "paragraph_start_index": chunk.paragraph_start_index,
            "paragraph_end_index": chunk.paragraph_end_index,
            "source_start_line": chunk.source_start_line,
            "source_end_line": chunk.source_end_line,
            "chunk_index": chunk.chunk_index,
            "char_count": chunk.char_count,
            "content_type": chunk.content_type,
            "model_path": chunk.model_path,
            "created_at": chunk.created_at,
        }
        chunk.metadata_json = json.dumps(chunk.metadata, ensure_ascii=False)
        enriched.append(chunk)
    return enriched


def save_chunks(chunks: Iterable[Chunk], db_path: Path | str = DEFAULT_DB_PATH) -> Path:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        with connection:
            _ensure_chunks_table(connection)
            connection.executemany(
                """
                INSERT OR IGNORE INTO chunks (
                    id, source_path, source_name, content_type, chunk_index, content,
                    char_count, paragraph_start_index, paragraph_end_index,
                    source_start_line, source_end_line, model_path, metadata_json, created_at
                )
                VALUES (
                    :id, :source_path, :source_name, :content_type, :chunk_index, :text,
                    :char_count, :paragraph_start_index, :paragraph_end_index,
                    :source_start_line, :source_end_line, :model_path, :metadata_json, :created_at
                )
                """,
                [asdict(chunk) for chunk in chunks],
            )
    finally:
        connection.close()
    return path


def process_corpus(
    raw_dir: Path | str = DEFAULT_RAW_DIR,
    config: CorpusConfig | None = None,
    similarity_model: SimilarityModel | None = None,
) -> PipelineResult:
    cfg = config or CorpusConfig(raw_dir=Path(raw_dir))
    model = similarity_model or _resolve_similarity_model(cfg)
    documents, errors = load_documents(cfg.raw_dir)
    paragraphs: list[Paragraph] = []
    for document in documents:
        paragraphs.extend(clean_document_text(document))
    semantic = semantic_chunk_paragraphs(paragraphs, model, cfg)
    final_chunks = add_metadata(dynamic_chunk(semantic, cfg), cfg.model_path)
    db_path = save_chunks(final_chunks, cfg.db_path)
    return PipelineResult(documents, errors, paragraphs, semantic, final_chunks, str(db_path))


def process_document(
    path: Path | str,
    config: CorpusConfig | None = None,
    similarity_model: SimilarityModel | None = None,
) -> PipelineResult:
    document_path = Path(path)
    cfg = config or CorpusConfig(raw_dir=document_path.parent)
    document = load_document(document_path)
    model = similarity_model or _resolve_similarity_model(cfg)
    paragraphs = clean_document_text(document)
    semantic = semantic_chunk_paragraphs(paragraphs, model, cfg)
    final_chunks = add_metadata(dynamic_chunk(semantic, cfg), cfg.model_path)
    db_path = save_chunks(final_chunks, cfg.db_path)
    return PipelineResult([document], [], paragraphs, semantic, final_chunks, str(db_path))


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\ufeff", "")
    text = re.sub(r"[\u200b\u200c\u200d]", "", text)
    normalized_lines = []
    for line in text.split("\n"):
        line = line.rstrip()
        line = re.sub(r"[\t\u3000]+", " ", line)
        normalized_lines.append(line)
    return "\n".join(normalized_lines)


def detect_content_type(text: str, block_type: str = "text") -> str:
    if block_type in {"code", "table"}:
        return block_type
    lines = [line for line in text.splitlines() if line.strip()]
    if lines and sum(1 for line in lines if _is_code_line(line)) / len(lines) >= 0.4:
        return "code"
    if lines and sum(1 for line in lines if _is_table_line(line)) / len(lines) >= 0.4:
        return "table"
    return "text"


def _read_txt(path: Path) -> str:
    data = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _load_document_file(path: Path, document_index: int) -> Document:
    ext = path.suffix.lower()
    if ext == ".txt":
        text = _read_txt(path)
    elif ext == ".docx":
        text = _read_docx(path)
    elif ext == ".pdf":
        text = _read_pdf(path)
    else:
        raise ValueError(f"unsupported file type: {ext}")
    return Document(
        text=text,
        source_path=str(path),
        source_name=path.name,
        extension=ext,
        document_index=document_index,
    )


def _resolve_similarity_model(config: CorpusConfig) -> SimilarityModel:
    if config.model_path == "lexical":
        return LexicalSimilarityModel()
    return load_similarity_model(config.model_dir)


def _ensure_chunks_table(connection: sqlite3.Connection) -> None:
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


def _read_docx(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        xml = archive.read("word/document.xml")
    root = ElementTree.fromstring(xml)
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs = []
    for paragraph in root.findall(".//w:p", ns):
        texts = [node.text or "" for node in paragraph.findall(".//w:t", ns)]
        if texts:
            paragraphs.append("".join(texts))
    return "\n\n".join(paragraphs)


def _read_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        return "\n\n".join(page.extract_text() or "" for page in reader.pages)
    except ModuleNotFoundError:
        pass
    try:
        from PyPDF2 import PdfReader

        reader = PdfReader(str(path))
        return "\n\n".join(page.extract_text() or "" for page in reader.pages)
    except ModuleNotFoundError:
        pass
    try:
        import pdfplumber

        with pdfplumber.open(str(path)) as pdf:
            return "\n\n".join(page.extract_text() or "" for page in pdf.pages)
    except ModuleNotFoundError as exc:
        raise RuntimeError("PDF support requires pypdf, PyPDF2, or pdfplumber") from exc


def _load_error(path: Path, reason: str) -> LoadError:
    return LoadError(str(path), path.name, path.suffix.lower(), reason)


def _line_units(lines: list[str]) -> list[dict[str, Any]]:
    units: list[dict[str, Any]] = []
    for index, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line:
            kind = "blank"
        elif _is_title_underline(line):
            kind = "underline"
        elif _is_code_line(raw):
            kind = "code"
            line = raw.rstrip()
        elif _is_table_line(line):
            kind = "table"
        elif _is_list_line(line):
            kind = "list"
        elif _is_title_line(line):
            kind = "title"
        else:
            kind = "text"
        units.append({"line": line, "line_no": index, "kind": kind})
    return units


def _join_wrapped_lines(lines: list[str]) -> str:
    result = ""
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if not result:
            result = stripped
            continue
        if _needs_space(result[-1], stripped[0]):
            result += " " + stripped
        else:
            result += stripped
    return result


def _needs_space(left: str, right: str) -> bool:
    return bool(re.match(r"[A-Za-z0-9_]", left) and re.match(r"[A-Za-z0-9_]", right))


def _is_title_underline(line: str) -> bool:
    return bool(re.fullmatch(r"[=\-*#]{3,}", line.strip()))


def _is_title_line(line: str) -> bool:
    if len(line) > 80:
        return False
    return bool(
        re.match(r"^=+\s*[^=].*?=+$", line)
        or re.match(r"^第[一二三四五六七八九十百千0-9]+[章节回篇部卷]", line)
        or re.match(r"^\d+(\.\d+)*[.、]?\s+\S+", line)
        or line.endswith(("章", "节", "回", "篇"))
    )


def _is_code_line(line: str) -> bool:
    raw = line.rstrip()
    stripped = raw.strip()
    return bool(
        raw.startswith(("   ", "\t"))
        and (
            stripped.startswith((">>>", "...", "#", "def ", "class ", "for ", "if ", "while "))
            or re.search(r"[:=(){}\[\]]", stripped)
        )
    )


def _is_list_line(line: str) -> bool:
    return bool(re.match(r"^([-*+]|\d+[.)、]|[（(]?\d+[）)])\s+", line))


def _is_table_line(line: str) -> bool:
    if "|" in line and line.count("|") >= 2:
        return True
    return bool(re.search(r"\S+\s{2,}\S+\s{2,}\S+", line))


def _semantic_chunk_from_paragraphs(paragraphs: list[Paragraph]) -> SemanticChunk:
    block_type = paragraphs[0].block_type if len({p.block_type for p in paragraphs}) == 1 else "mixed"
    separator = "\n" if block_type in {"code", "table", "list"} else "\n\n"
    return SemanticChunk(
        text=separator.join(p.text for p in paragraphs),
        block_type=block_type,
        source_path=paragraphs[0].source_path,
        source_name=paragraphs[0].source_name,
        paragraph_start_index=paragraphs[0].paragraph_index,
        paragraph_end_index=paragraphs[-1].paragraph_index,
        source_start_line=paragraphs[0].source_start_line,
        source_end_line=paragraphs[-1].source_end_line,
    )


def _chunk_profile(content_type: str, config: CorpusConfig) -> tuple[int, int]:
    if content_type == "code":
        return config.code_chunk_size, config.code_overlap
    if content_type == "table":
        return config.table_chunk_size, config.table_overlap
    return config.text_chunk_size, config.text_overlap


def _split_with_overlap(text: str, size: int, overlap: int) -> list[str]:
    if size <= 0:
        raise ValueError("chunk size must be positive")
    if overlap < 0 or overlap >= size:
        raise ValueError("overlap must be >= 0 and smaller than chunk size")
    if len(text) <= size:
        return [text]
    pieces = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        pieces.append(text[start:end])
        if end == len(text):
            break
        start = end - overlap
    return pieces


def _lexical_tokens(text: str) -> set[str]:
    words = set(re.findall(r"[A-Za-z0-9_]+", text.lower()))
    chars = {char for char in text if "\u4e00" <= char <= "\u9fff"}
    return words | chars


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    index = (len(values) - 1) * percentile
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return round(float(values[int(index)]), 6)
    weight = index - lower
    return round(float(values[lower] * (1 - weight) + values[upper] * weight), 6)
