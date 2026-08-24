import io
import sqlite3
import tempfile
import unittest
from contextlib import closing
from contextlib import redirect_stdout
from pathlib import Path

from HybridRetriever.Retriever import Retriever, RetrieverConfig
from HybridRetriever.method import bm25_search, vector_search
from corpus.documentProcess import LexicalSimilarityModel


class HybridRetrieverTests(unittest.TestCase):
    def setUp(self):
        Retriever.reset_instance()

    def tearDown(self):
        Retriever.reset_instance()

    def test_initialization_creates_storage_and_singleton(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = RetrieverConfig(
                corpus_db_path=root / "corpus.db",
                vector_db_path=root / "vector.db",
                model_path="lexical",
            )

            first = Retriever(config)
            second = Retriever(RetrieverConfig(model_path="ignored"))

            self.assertIs(first, second)
            self.assertTrue(config.corpus_db_path.exists())
            self.assertTrue(config.vector_db_path.exists())
            with closing(sqlite3.connect(config.vector_db_path)) as connection:
                columns = [row[1] for row in connection.execute("PRAGMA table_info(vectors)").fetchall()]
            self.assertIn("chunk_id", columns)
            self.assertIn("model_path", columns)

    def test_vector_and_bm25_scoring(self):
        vector_scores = vector_search([1.0, 0.0], {"a": [1.0, 0.0], "b": [0.0, 1.0]})
        bm25_scores = bm25_search("苹果", {"a": "苹果 苹果 香蕉", "b": "香蕉 梨子"})

        self.assertGreater(vector_scores["a"], vector_scores["b"])
        self.assertGreater(bm25_scores["a"], bm25_scores["b"])

    def test_bm25_uses_chinese_words_instead_of_individual_characters(self):
        scores = bm25_search(
            "人工智能",
            {
                "word": "人工智能推动技术发展",
                "characters": "人 工 智 能",
            },
        )

        self.assertGreater(scores["word"], scores["characters"])
        self.assertEqual(scores["characters"], 0.0)

    def test_bm25_normalizes_english_numbers_and_filters_punctuation(self):
        scores = bm25_search(
            "OPENAI, 2026!!!",
            {
                "match": "openai 2026",
                "split": "open ai 20 26",
            },
        )
        punctuation_scores = bm25_search("!!!", {"punctuation": "!!!", "text": "openai"})

        self.assertGreater(scores["match"], scores["split"])
        self.assertEqual(punctuation_scores, {"punctuation": 0.0, "text": 0.0})

    def test_archive_dedupes_same_model_and_distinguishes_different_models(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            doc_path = root / "sample.txt"
            doc_path.write_text("苹果 知识库\n\n香蕉 检索", encoding="utf-8")
            corpus_db = root / "corpus.db"
            vector_db = root / "vector.db"

            retriever = Retriever(RetrieverConfig(corpus_db, vector_db, "lexical"))
            retriever.archive(doc_path)
            retriever.archive(doc_path)

            with closing(sqlite3.connect(corpus_db)) as connection:
                same_model_count = connection.execute("SELECT count(*) FROM chunks").fetchone()[0]
                vector_count = self._table_count(connection, "chunks")
            with closing(sqlite3.connect(vector_db)) as connection:
                same_vector_count = self._table_count(connection, "vectors")

            Retriever.reset_instance()
            other = Retriever(
                RetrieverConfig(corpus_db, vector_db, "other-model"),
                embedder=retriever.embedder,
                similarity_model=LexicalSimilarityModel(),
            )
            other.archive(doc_path)
            with closing(sqlite3.connect(corpus_db)) as connection:
                all_model_count = connection.execute("SELECT count(*) FROM chunks").fetchone()[0]

        self.assertEqual(same_model_count, vector_count)
        self.assertEqual(same_model_count, same_vector_count)
        self.assertGreater(all_model_count, same_model_count)

    def test_archive_updates_all_missing_vectors_after_processing_document(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            doc_path = root / "sample.txt"
            doc_path.write_text("苹果 知识库\n\n香蕉 检索", encoding="utf-8")
            config = RetrieverConfig(root / "corpus.db", root / "vector.db", "lexical")
            retriever = Retriever(config)
            with closing(sqlite3.connect(config.corpus_db_path)) as connection:
                connection.execute(
                    """
                    INSERT INTO chunks (
                        id, source_path, source_name, content_type, chunk_index, content,
                        char_count, paragraph_start_index, paragraph_end_index,
                        source_start_line, source_end_line, model_path, metadata_json, created_at
                    )
                    VALUES (
                        'preexisting', 'raw/old.txt', 'old.txt', 'text', 0, '旧 苹果 文本',
                        7, 0, 0, 1, 1, 'lexical', '{}', 'now'
                    )
                    """
                )
                connection.commit()

            retriever.archive(doc_path)

            with closing(sqlite3.connect(config.vector_db_path)) as connection:
                preexisting_vectors = connection.execute(
                    "SELECT count(*) FROM vectors WHERE chunk_id = 'preexisting' AND model_path = 'lexical'"
                ).fetchone()[0]

        self.assertEqual(preexisting_vectors, 1)

    def test_update_reconciles_missing_vectors_without_deleting_old_vectors(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            doc_path = root / "sample.txt"
            doc_path.write_text("苹果 知识库\n\n香蕉 检索", encoding="utf-8")
            config = RetrieverConfig(root / "corpus.db", root / "vector.db", "lexical")
            retriever = Retriever(config)
            retriever.archive(doc_path)

            with closing(sqlite3.connect(config.vector_db_path)) as connection:
                connection.execute("DELETE FROM vectors WHERE chunk_id = (SELECT chunk_id FROM vectors LIMIT 1)")
                connection.execute(
                    """
                    INSERT INTO vectors (
                        chunk_id, model_path, embedding_json, dimension,
                        content_hash, created_at, updated_at
                    )
                    VALUES ('stale', 'lexical', '[0.0]', 1, 'hash', 'now', 'now')
                    """
                )
                connection.commit()
                before = self._table_count(connection, "vectors")

            retriever.update()

            with closing(sqlite3.connect(config.vector_db_path)) as connection:
                after = self._table_count(connection, "vectors")
                stale_count = connection.execute("SELECT count(*) FROM vectors WHERE chunk_id = 'stale'").fetchone()[0]

        self.assertEqual(after, before + 1)
        self.assertEqual(stale_count, 1)

    def test_retrieve_filters_model_and_stale_vectors_and_prints_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            doc_path = root / "sample.txt"
            doc_path.write_text("苹果 知识库\n\n香蕉 检索", encoding="utf-8")
            config = RetrieverConfig(root / "corpus.db", root / "vector.db", "lexical")
            retriever = Retriever(config)
            retriever.archive(doc_path)

            with closing(sqlite3.connect(config.vector_db_path)) as connection:
                connection.execute(
                    """
                    INSERT INTO vectors (
                        chunk_id, model_path, embedding_json, dimension,
                        content_hash, created_at, updated_at
                    )
                    VALUES ('stale', 'lexical', '[0.0]', 1, 'hash', 'now', 'now')
                    """
                )
                connection.execute(
                    """
                    INSERT INTO vectors (
                        chunk_id, model_path, embedding_json, dimension,
                        content_hash, created_at, updated_at
                    )
                    VALUES ('other', 'other-model', '[0.0]', 1, 'hash', 'now', 'now')
                    """
                )
                connection.commit()

            results = retriever.retrieve("苹果", 1)
            output = io.StringIO()
            with redirect_stdout(output):
                retriever.print_results(results)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].model_path, "lexical")
        self.assertIn("苹果", results[0].content)
        self.assertEqual(output.getvalue().strip(), results[0].content)

    def test_retrieve_empty_and_invalid_k(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            retriever = Retriever(RetrieverConfig(root / "corpus.db", root / "vector.db", "lexical"))

            self.assertEqual(retriever.retrieve("苹果", 3), [])
            with self.assertRaises(ValueError):
                retriever.retrieve("苹果", 0)

    def _table_count(self, connection: sqlite3.Connection, table: str) -> int:
        return connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]


if __name__ == "__main__":
    unittest.main()
