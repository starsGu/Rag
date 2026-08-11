"""Tests and opt-in live checks for :mod:`qa.qaBuilder`."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from qa import qaBuilder as qa_builder_module  # noqa: E402
from qa.qaBuilder import QaBuilder, SYSTEM_PROMPT  # noqa: E402


class _FakeCompletions:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.response_text = (
            '[{"question":"问题一","answer":"综合全部分段得到的答案","content_index":0}]'
        )
        self.response_texts: list[str] = []
        self.errors_by_call: dict[int, Exception] = {}

    def create(self, **kwargs):
        call_index = len(self.calls)
        self.calls.append(kwargs)
        if call_index in self.errors_by_call:
            raise self.errors_by_call[call_index]
        content = (
            self.response_texts[call_index]
            if call_index < len(self.response_texts)
            else self.response_text
        )
        message = types.SimpleNamespace(content=content)
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)])


class _FakeOpenAI:
    instances: list["_FakeOpenAI"] = []

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.chat = types.SimpleNamespace(completions=_FakeCompletions())
        self.instances.append(self)


class QaBuilderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.database_path = self.root / "corpus.db"
        self._replace_chunks(2)

        _FakeOpenAI.instances.clear()
        self.dotenv_paths: list[Path] = []
        fake_dotenv = types.ModuleType("dotenv")
        fake_dotenv.load_dotenv = lambda path: self.dotenv_paths.append(Path(path))
        fake_openai = types.ModuleType("openai")
        fake_openai.OpenAI = _FakeOpenAI

        modules_patch = patch.dict(
            sys.modules,
            {"dotenv": fake_dotenv, "openai": fake_openai},
        )
        environment_patch = patch.dict(
            os.environ,
            {
                "QA_BASE_URL": "https://example.invalid/v1",
                "QA_API_KEY": "test-key",
                "QA_MODEL": "deepseek-v4-pro",
            },
        )
        output_patch = patch.object(
            qa_builder_module,
            "DEFAULT_OUTPUT_DIR",
            self.root,
        )
        modules_patch.start()
        environment_patch.start()
        output_patch.start()
        self.addCleanup(output_patch.stop)
        self.addCleanup(environment_patch.stop)
        self.addCleanup(modules_patch.stop)

        self.builder = QaBuilder(self.database_path)
        self.client = _FakeOpenAI.instances[-1]
        self.completions = self.client.chat.completions

    def _replace_chunks(self, count: int, source_name: str = "UBP.pdf") -> None:
        if self.database_path.exists():
            self.database_path.unlink()
        connection = sqlite3.connect(self.database_path)
        try:
            connection.execute(
                "CREATE TABLE chunks (id TEXT, source_name TEXT, chunk_index INTEGER, content TEXT)"
            )
            rows = [
                (
                    f"chunk-{index:04d}",
                    source_name,
                    index,
                    f"content-{index:04d}",
                )
                for index in reversed(range(count))
            ]
            connection.executemany("INSERT INTO chunks VALUES (?, ?, ?, ?)", rows)
            connection.execute(
                "INSERT INTO chunks VALUES (?, ?, ?, ?)",
                ("other", "Other.pdf", 0, "must-not-be-sent"),
            )
            connection.commit()
        finally:
            connection.close()

    def _request_parts(self, call: dict) -> tuple[str, list[str], list[int]]:
        system_prompt = call["messages"][0]["content"]
        chunk_json, range_json = call["messages"][1]["content"].rsplit("\n", 1)
        return system_prompt, json.loads(chunk_json), json.loads(range_json)

    def test_constructor_loads_dotenv_and_creates_configured_client(self) -> None:
        self.assertEqual(self.dotenv_paths, [PROJECT_ROOT / ".env"])
        self.assertEqual(
            self.client.kwargs,
            {"base_url": "https://example.invalid/v1", "api_key": "test-key"},
        )
        self.assertEqual(self.builder.model, "deepseek-v4-pro")

    def test_default_batch_sends_full_ordered_context_and_writes_ubp_json(self) -> None:
        generic_output = self.root / "datafile.json"
        generic_output.write_text("legacy", encoding="utf-8")

        records = self.builder.getQA("UBP.pdf")

        self.assertEqual(len(self.completions.calls), 1)
        prompt, contents, active_range = self._request_parts(self.completions.calls[0])
        self.assertEqual(active_range, [0, 1])
        self.assertEqual(contents, ["content-0000", "content-0001"])
        self.assertEqual(prompt, SYSTEM_PROMPT.replace("[a, b]", "[0, 1]"))
        self.assertEqual(self.builder.output_path, self.root / "UBP.json")
        self.assertEqual(
            json.loads((self.root / "UBP.json").read_text(encoding="utf-8")),
            records,
        )
        self.assertEqual(generic_output.read_text(encoding="utf-8"), "legacy")

    def test_278_chunks_use_six_ranges_and_repeat_full_context(self) -> None:
        self._replace_chunks(278)
        ranges = [[0, 49], [50, 99], [100, 149], [150, 199], [200, 249], [250, 277]]
        self.completions.response_texts = [
            json.dumps(
                [
                    {
                        "question": f"question-{start}",
                        "answer": f"answer-{start}",
                        "content_index": start,
                    }
                ]
            )
            for start, _ in ranges
        ]

        records = self.builder.getQA("UBP.pdf")

        self.assertEqual(len(self.completions.calls), 6)
        for call, expected_range in zip(self.completions.calls, ranges):
            prompt, contents, active_range = self._request_parts(call)
            self.assertEqual(active_range, expected_range)
            self.assertEqual(len(contents), 278)
            self.assertEqual(contents[0], "content-0000")
            self.assertEqual(contents[-1], "content-0277")
            self.assertEqual(
                prompt,
                SYSTEM_PROMPT.replace(
                    "[a, b]",
                    f"[{expected_range[0]}, {expected_range[1]}]",
                ),
            )
        self.assertEqual([record["content_index"] for record in records], [0, 50, 100, 150, 200, 250])

    def test_custom_batch_merges_empty_and_qestion_alias_responses(self) -> None:
        self._replace_chunks(3)
        self.completions.response_texts = [
            "[]",
            '```json\n[{"qestion":"别名问题","answer":"答案","content_index":2}]\n```',
        ]

        records = self.builder.getQA("UBP.pdf", per_chunk=2)

        self.assertEqual(len(self.completions.calls), 2)
        self.assertEqual(self._request_parts(self.completions.calls[0])[2], [0, 1])
        self.assertEqual(self._request_parts(self.completions.calls[1])[2], [2, 2])
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["content_index"], 2)
        self.assertEqual(records[0]["conversations"][0]["value"], "别名问题")

    def test_invalid_per_chunk_fails_before_api_or_output(self) -> None:
        invalid_values = [True, False, 0, -1, 1.5, "50", None]
        for value in invalid_values:
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "per_chunk"):
                    self.builder.getQA("UBP.pdf", per_chunk=value)
        self.assertEqual(self.completions.calls, [])
        self.assertFalse((self.root / "UBP.json").exists())

    def test_invalid_first_batch_responses_preserve_existing_output(self) -> None:
        invalid_responses = [
            "",
            "not-json",
            "{}",
            '[{"question":"问题","content_index":0}]',
            '[{"question":"问题","answer":"答案","content_index":true}]',
        ]
        output_path = self.root / "UBP.json"
        for response_text in invalid_responses:
            with self.subTest(response_text=response_text):
                output_path.write_text("previous-result", encoding="utf-8")
                self.completions.response_text = response_text

                with self.assertRaises(ValueError):
                    self.builder.getQA("UBP.pdf")

                self.assertEqual(output_path.read_text(encoding="utf-8"), "previous-result")

    def test_later_batch_out_of_range_preserves_existing_output(self) -> None:
        self._replace_chunks(3)
        output_path = self.root / "UBP.json"
        output_path.write_text("previous-result", encoding="utf-8")
        self.completions.response_texts = [
            '[{"question":"第一批","answer":"答案","content_index":0}]',
            '[{"question":"越界","answer":"答案","content_index":0}]',
        ]

        with self.assertRaisesRegex(ValueError, "active range"):
            self.builder.getQA("UBP.pdf", per_chunk=2)

        self.assertEqual(len(self.completions.calls), 2)
        self.assertEqual(output_path.read_text(encoding="utf-8"), "previous-result")

    def test_later_provider_failure_preserves_existing_output(self) -> None:
        self._replace_chunks(3)
        output_path = self.root / "UBP.json"
        output_path.write_text("previous-result", encoding="utf-8")
        self.completions.response_texts = [
            '[{"question":"第一批","answer":"答案","content_index":0}]'
        ]
        self.completions.errors_by_call[1] = RuntimeError("provider rejected request")

        with self.assertRaisesRegex(RuntimeError, "provider rejected request"):
            self.builder.getQA("UBP.pdf", per_chunk=2)

        self.assertEqual(output_path.read_text(encoding="utf-8"), "previous-result")

    def test_multiple_dot_filename_and_successive_runs_replace(self) -> None:
        self._replace_chunks(1, source_name="paper.v2.pdf")
        first = self.builder.getQA("paper.v2.pdf")
        self.completions.response_text = (
            '[{"question":"第二次问题","answer":"第二次答案","content_index":0}]'
        )

        second = self.builder.getQA("paper.v2.pdf")

        output_path = self.root / "paper.v2.json"
        self.assertNotEqual(first, second)
        self.assertEqual(self.builder.output_path, output_path)
        self.assertEqual(json.loads(output_path.read_text(encoding="utf-8")), second)
        self.assertEqual(len(second), 1)

    def test_database_failures_do_not_call_provider(self) -> None:
        missing_builder = QaBuilder(self.root / "missing.db")
        missing_builder.output_dir = self.root
        with self.assertRaises(FileNotFoundError):
            missing_builder.getQA("UBP.pdf")
        with self.assertRaises(ValueError):
            self.builder.getQA("Missing.pdf")
        self.assertEqual(self.completions.calls, [])

    def test_constructor_rejects_missing_required_environment(self) -> None:
        with patch.dict(os.environ, {"QA_API_KEY": ""}):
            with self.assertRaisesRegex(ValueError, "QA_API_KEY"):
                QaBuilder(self.database_path)
        with patch.dict(os.environ, {"QA_MODEL": ""}):
            with self.assertRaisesRegex(ValueError, "QA_MODEL"):
                QaBuilder(self.database_path)


def _run_api_smoke() -> int:
    builder = QaBuilder()
    response = builder.client.chat.completions.create(
        model=builder.model,
        messages=[
            {"role": "system", "content": "请简洁回答。"},
            {"role": "user", "content": "请回答：1+1等于几？"},
        ],
    )
    try:
        content = response.choices[0].message.content
    except (AttributeError, IndexError, TypeError) as exc:
        raise RuntimeError("API smoke response does not contain message content") from exc
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("API smoke response is empty")
    print(content.strip())
    return 0


def _run_datafile(data_file: str) -> int:
    builder = QaBuilder()
    records = builder.getQA(data_file)
    print(f"generated {len(records)} records: {builder.output_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Test QaBuilder or run an opt-in live check.")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--api-smoke", action="store_true", help="make one minimal live API request")
    modes.add_argument("--datafile", help="generate QA for this exact chunks.source_name")
    args = parser.parse_args(argv)

    try:
        if args.api_smoke:
            return _run_api_smoke()
        if args.datafile:
            return _run_datafile(args.datafile)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    program = unittest.main(argv=[sys.argv[0]], exit=False)
    return 0 if program.result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
