import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path

from corpus.documentProcess import (
    CorpusConfig,
    Document,
    Paragraph,
    SemanticChunk,
    add_metadata,
    calibrate_similarity_threshold,
    clean_document_text,
    dynamic_chunk,
    process_document,
    load_documents,
    save_chunks,
    semantic_chunk_paragraphs,
)


class StubSimilarityModel:
    def similarity(self, left: str, right: str) -> float:
        if "相同主题" in left and "相同主题" in right:
            return 0.95
        return 0.1


class CorpusDocumentProcessTests(unittest.TestCase):
    def test_load_documents_reads_txt_docx_and_reports_unsupported(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp)
            (raw / "sample.txt").write_text("第一段\n\n第二段", encoding="utf-8")
            self._write_docx(raw / "sample.docx", ["甲段", "乙段"])
            (raw / "sample.bin").write_bytes(b"nope")

            documents, errors = load_documents(raw)

            self.assertEqual([doc.source_name for doc in documents], ["sample.docx", "sample.txt"])
            self.assertEqual(len(errors), 1)
            self.assertEqual(errors[0].source_name, "sample.bin")
            self.assertIn("甲段", documents[0].text)

    def test_clean_document_text_recovers_hard_wrapped_natural_paragraphs(self):
        document = Document(
            text=(
                "第一章 标题\n"
                "========\n\n"
                "这是一个自然段的前半句，\n"
                "因为显示宽度被硬换行。\n"
                "这仍然是同一个自然段。\n\n"
                "这是第二个自然段。"
            ),
            source_path="raw/sample.txt",
            source_name="sample.txt",
            extension=".txt",
            document_index=0,
        )

        paragraphs = clean_document_text(document)

        self.assertEqual(paragraphs[0].block_type, "title")
        self.assertEqual(paragraphs[1].block_type, "text")
        self.assertIn("前半句，因为显示宽度", paragraphs[1].text)
        self.assertIn("硬换行。这仍然", paragraphs[1].text)
        self.assertEqual(paragraphs[2].text, "这是第二个自然段。")

    def test_clean_document_text_preserves_code_list_and_table_boundaries(self):
        document = Document(
            text=(
                "正文第一行\n"
                "正文第二行\n\n"
                "== 小标题 ==\n\n"
                "   >>> if x < 0:\n"
                "   ...     print(x)\n\n"
                "- 第一项\n"
                "- 第二项\n\n"
                "列A  列B  列C\n"
                "1    2    3"
            ),
            source_path="raw/sample.txt",
            source_name="sample.txt",
            extension=".txt",
            document_index=0,
        )

        paragraphs = clean_document_text(document)
        block_types = [paragraph.block_type for paragraph in paragraphs]

        self.assertEqual(block_types, ["text", "title", "code", "list", "table"])
        self.assertEqual(paragraphs[1].text, "== 小标题 ==")
        self.assertIn("\n", paragraphs[2].text)
        self.assertIn("- 第一项\n- 第二项", paragraphs[3].text)

    def test_semantic_chunk_merges_similar_and_splits_different_paragraphs(self):
        paragraphs = [
            self._paragraph("相同主题 第一段", 0),
            self._paragraph("相同主题 第二段", 1),
            self._paragraph("完全不同内容", 2),
        ]

        chunks = semantic_chunk_paragraphs(
            paragraphs,
            StubSimilarityModel(),
            CorpusConfig(similarity_threshold=0.72, max_semantic_paragraphs=6),
        )

        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[0].paragraph_start_index, 0)
        self.assertEqual(chunks[0].paragraph_end_index, 1)
        self.assertEqual(chunks[1].paragraph_start_index, 2)

    def test_semantic_chunk_respects_max_consecutive_paragraphs(self):
        paragraphs = [self._paragraph(f"相同主题 第{i}段", i) for i in range(4)]

        chunks = semantic_chunk_paragraphs(
            paragraphs,
            StubSimilarityModel(),
            CorpusConfig(similarity_threshold=0.72, max_semantic_paragraphs=2),
        )

        self.assertEqual([(c.paragraph_start_index, c.paragraph_end_index) for c in chunks], [(0, 1), (2, 3)])

    def test_calibrate_similarity_threshold_returns_samples_and_percentiles(self):
        paragraphs = [
            self._paragraph("相同主题 第一段", 0),
            self._paragraph("相同主题 第二段", 1),
            self._paragraph("完全不同内容", 2),
        ]

        report = calibrate_similarity_threshold(paragraphs, StubSimilarityModel())

        self.assertEqual(report.sample_count, 2)
        self.assertIn("p75", report.percentiles)
        self.assertGreaterEqual(report.suggested_threshold, 0.1)
        self.assertEqual(report.samples[0]["left_index"], 0)

    def test_dynamic_chunk_uses_content_type_specific_sizes(self):
        semantic_chunks = [
            SemanticChunk("x" * 600, "code", "raw/a.txt", "a.txt", 0, 0, 1, 1),
            SemanticChunk("y" * 900, "table", "raw/a.txt", "a.txt", 1, 1, 2, 2),
            SemanticChunk("z" * 1200, "text", "raw/a.txt", "a.txt", 2, 2, 3, 3),
        ]

        chunks = dynamic_chunk(semantic_chunks, CorpusConfig())

        self.assertTrue(any(chunk.content_type == "code" and chunk.char_count == 256 for chunk in chunks))
        self.assertTrue(any(chunk.content_type == "table" and chunk.char_count == 384 for chunk in chunks))
        self.assertTrue(any(chunk.content_type == "text" and chunk.char_count == 512 for chunk in chunks))

    def test_save_chunks_persists_traceable_metadata(self):
        semantic_chunks = [SemanticChunk("普通文本内容", "text", "raw/a.txt", "a.txt", 2, 4, 10, 12)]
        chunks = add_metadata(dynamic_chunk(semantic_chunks, CorpusConfig(model_path="model-a")), "model-a")

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "corpus.db"
            save_chunks(chunks, db_path)
            connection = sqlite3.connect(db_path)
            try:
                row = connection.execute(
                    "SELECT source_name, content_type, chunk_index, content, model_path, metadata_json FROM chunks"
                ).fetchone()
            finally:
                connection.close()

        self.assertEqual(row[0], "a.txt")
        self.assertEqual(row[1], "text")
        self.assertEqual(row[2], 0)
        self.assertEqual(row[3], "普通文本内容")
        self.assertEqual(row[4], "model-a")
        self.assertIn('"paragraph_start_index": 2', row[5])
        self.assertIn('"model_path": "model-a"', row[5])

    def test_save_chunks_is_incremental_for_existing_chunks(self):
        semantic_chunks = [SemanticChunk("普通文本内容", "text", "raw/a.txt", "a.txt", 2, 4, 10, 12)]
        chunks = add_metadata(dynamic_chunk(semantic_chunks, CorpusConfig(model_path="model-a")), "model-a")

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "corpus.db"
            save_chunks(chunks, db_path)
            save_chunks(chunks, db_path)
            connection = sqlite3.connect(db_path)
            try:
                count = connection.execute("SELECT count(*) FROM chunks").fetchone()[0]
            finally:
                connection.close()

        self.assertEqual(count, 1)

    def test_model_path_distinguishes_chunk_identity(self):
        semantic_chunks = [SemanticChunk("普通文本内容", "text", "raw/a.txt", "a.txt", 2, 4, 10, 12)]
        chunks_a = add_metadata(dynamic_chunk(semantic_chunks, CorpusConfig(model_path="model-a")), "model-a")
        chunks_b = add_metadata(dynamic_chunk(semantic_chunks, CorpusConfig(model_path="model-b")), "model-b")

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "corpus.db"
            save_chunks(chunks_a, db_path)
            save_chunks(chunks_a, db_path)
            save_chunks(chunks_b, db_path)
            connection = sqlite3.connect(db_path)
            try:
                rows = connection.execute("SELECT id, model_path FROM chunks ORDER BY model_path").fetchall()
            finally:
                connection.close()

        self.assertEqual(len(rows), 2)
        self.assertEqual([row[1] for row in rows], ["model-a", "model-b"])
        self.assertNotEqual(rows[0][0], rows[1][0])

    def test_process_document_processes_one_file_and_returns_pipeline_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            document_path = root / "sample.txt"
            document_path.write_text("相同主题 第一段\n相同主题 第二段", encoding="utf-8")
            config = CorpusConfig(
                raw_dir=root,
                db_path=root / "corpus.db",
                corpus_dir=root,
                model_dir=Path(""),
                model_path="lexical",
            )

            result = process_document(document_path, config, StubSimilarityModel())

        self.assertEqual(len(result.documents), 1)
        self.assertEqual(result.documents[0].source_name, "sample.txt")
        self.assertGreaterEqual(len(result.chunks), 1)
        self.assertEqual(result.chunks[0].model_path, "lexical")

    def test_process_document_rejects_invalid_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            unsupported = root / "sample.bin"
            unsupported.write_bytes(b"nope")

            with self.assertRaises(FileNotFoundError):
                process_document(root / "missing.txt", CorpusConfig(model_path="lexical"), StubSimilarityModel())
            with self.assertRaises(ValueError):
                process_document(root, CorpusConfig(model_path="lexical"), StubSimilarityModel())
            with self.assertRaises(ValueError):
                process_document(unsupported, CorpusConfig(model_path="lexical"), StubSimilarityModel())

    def _paragraph(self, text: str, index: int) -> Paragraph:
        return Paragraph(text, "text", "raw/a.txt", "a.txt", index + 1, index + 1, index)

    def _write_docx(self, path: Path, paragraphs: list[str]) -> None:
        body = "".join(
            f"<w:p><w:r><w:t>{paragraph}</w:t></w:r></w:p>" for paragraph in paragraphs
        )
        document_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            f"<w:body>{body}</w:body></w:document>"
        )
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("word/document.xml", document_xml)


if __name__ == "__main__":
    unittest.main()
