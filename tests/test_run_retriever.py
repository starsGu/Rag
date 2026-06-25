import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace

from HybridRetriever import Retriever, RetrieverConfig
from run_retriever import _archive_to_corpus


class RunRetrieverTests(unittest.TestCase):
    def setUp(self):
        Retriever.reset_instance()

    def tearDown(self):
        Retriever.reset_instance()

    def test_retriever_startup_creates_corpus_and_vector_databases(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            corpus_db = root / "missing" / "corpus.db"
            vector_db = root / "missing" / "vector.db"

            Retriever(RetrieverConfig(corpus_db, vector_db, "lexical"))

            self.assertTrue(corpus_db.exists())
            self.assertTrue(vector_db.exists())

    def test_archive_to_corpus_processes_file_or_folder_without_vector_db(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            file_path = root / "one.txt"
            file_path.write_text("苹果 知识库", encoding="utf-8")
            folder = root / "docs"
            folder.mkdir()
            (folder / "two.txt").write_text("香蕉 检索", encoding="utf-8")
            corpus_db = root / "corpus.db"
            vector_db = root / "vector.db"
            args = SimpleNamespace(corpus_db=str(corpus_db), vector_db=str(vector_db), model="lexical")

            file_result = _archive_to_corpus(file_path, args)
            folder_result = _archive_to_corpus(folder, args)

            with closing(sqlite3.connect(corpus_db)) as connection:
                chunk_count = connection.execute("SELECT count(*) FROM chunks").fetchone()[0]

        self.assertGreaterEqual(len(file_result.chunks), 1)
        self.assertGreaterEqual(len(folder_result.chunks), 1)
        self.assertGreaterEqual(chunk_count, 2)
        self.assertFalse(vector_db.exists())


if __name__ == "__main__":
    unittest.main()
