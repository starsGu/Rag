"""Generate ShareGPT question-answer data from stored corpus chunks."""

from __future__ import annotations

import json
import os
import re
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path
from typing import Any


MODULE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = MODULE_DIR.parent
DEFAULT_CORPUS_DB_PATH = PROJECT_ROOT / "data" / "corpus" / "corpus.db"
DEFAULT_OUTPUT_DIR = MODULE_DIR
DEFAULT_BASE_URL = "https://opencode.ai/zen/go/v1"

SYSTEM_PROMPT = (
    "你是专家，以下是一篇论文的所有分段列表 [content_0, content_1, content_2, content_3 ... content_n] 和 将要处理文本段索引[a, b] 的的，你根据每一个文本分段content_i, (i大于等于a,i小于等于b])，你尽可能多的提出一些问题或者不提问题，"
    "然后根据所有文本分段拼凑的全文 [content_0 + content_1 + content_2 + content_3 + ... + content_n] 回答这些问题，最后把[a, b]分段的问答对返回。"
    '回复内容举例：'
    '['
    '   //content_a 提出了3个问答对 '
    '   {"question": xxx ,"answer": xxx ,"content_index": a}'
    '   {"question": xxx ,"answer": xxx ,"content_index": a}'
    '   {"question": xxx ,"answer": xxx ,"content_index": a}'
    '   //content_a+1 提出了0个问答对 '
    '   //content_a+2 提出了1个问答对 '
    '   {"question": xxx ,"answer": xxx ,"content_index": a+2}'
        '...'
    '   //content_i 提出了1个问答对 '
    '   {"question": xxx ,"answer": xxx ,"content_index": i}'
        '...'
    '   //content_b 提出了2个问答对 '
    '   {"question": xxx ,"answer": xxx ,"content_index": b}'
    '   {"question": xxx ,"answer": xxx ,"content_index": b}'
    ']'
)


class QaBuilder:
    """Build single-turn ShareGPT records for one stored source filename."""

    def __init__(self, corpus_db_path: str | Path = DEFAULT_CORPUS_DB_PATH):
        self.corpus_db_path = Path(corpus_db_path)
        self.output_dir = DEFAULT_OUTPUT_DIR
        self.output_path: Path | None = None

        try:
            from dotenv import load_dotenv
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "python-dotenv is required; install it with `pip install python-dotenv`"
            ) from exc

        try:
            from openai import OpenAI
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "openai is required; install it with `pip install openai`"
            ) from exc

        load_dotenv(PROJECT_ROOT / ".env")
        api_key = _required_environment_value("QA_API_KEY")
        self.model = _required_environment_value("QA_MODEL")
        base_url = os.getenv("QA_BASE_URL", DEFAULT_BASE_URL).strip()
        if not base_url:
            base_url = DEFAULT_BASE_URL

        self.client = OpenAI(base_url=base_url, api_key=api_key)

    def getQA(self, dataFile: str, per_chunk: int = 50) -> list[dict[str, Any]]:
        """Generate and persist ShareGPT records for ``dataFile``.

        ``dataFile`` is matched only against ``chunks.source_name``. The source
        document itself is never opened or uploaded.
        """

        if type(per_chunk) is not int or per_chunk <= 0:
            raise ValueError("per_chunk must be a positive integer")
        contents = self._load_chunk_contents(dataFile)
        output_path = self._output_path_for(dataFile)
        records: list[dict[str, Any]] = []
        for batch_start in range(0, len(contents), per_chunk):
            batch_end = min(batch_start + per_chunk - 1, len(contents) - 1)
            response_text = self._request_qa(contents, batch_start, batch_end)
            records.extend(
                self._parse_sharegpt_records(
                    response_text,
                    batch_start,
                    batch_end,
                )
            )
        self._replace_output(records, output_path)
        self.output_path = output_path
        return records

    def _output_path_for(self, data_file: str) -> Path:
        source_name = Path(data_file).name
        output_stem = Path(source_name).stem
        if not output_stem or output_stem in {".", ".."}:
            raise ValueError(f"dataFile has no usable filename stem: {data_file}")
        return self.output_dir / f"{output_stem}.json"

    def _load_chunk_contents(self, data_file: str) -> list[str]:
        if not isinstance(data_file, str) or not data_file.strip():
            raise ValueError("dataFile must be a non-empty source filename")
        if not self.corpus_db_path.exists():
            raise FileNotFoundError(f"corpus database not found: {self.corpus_db_path}")
        if not self.corpus_db_path.is_file():
            raise ValueError(f"corpus database path is not a file: {self.corpus_db_path}")

        database_uri = f"{self.corpus_db_path.resolve().as_uri()}?mode=ro"
        try:
            with closing(sqlite3.connect(database_uri, uri=True)) as connection:
                rows = connection.execute(
                    """
                    SELECT content
                    FROM chunks
                    WHERE source_name = ?
                    ORDER BY chunk_index, id
                    """,
                    (data_file,),
                ).fetchall()
        except sqlite3.Error as exc:
            raise RuntimeError(f"failed to read corpus database: {exc}") from exc

        contents = [row[0] for row in rows]
        if not contents:
            raise ValueError(f"no chunks found for source filename: {data_file}")
        if any(not isinstance(content, str) for content in contents):
            raise ValueError(f"non-text chunk found for source filename: {data_file}")
        return contents

    def _request_qa(
        self,
        contents: list[str],
        batch_start: int,
        batch_end: int,
    ) -> str:
        batch_prompt = SYSTEM_PROMPT.replace(
            "[a, b]",
            f"[{batch_start}, {batch_end}]",
        )
        user_content = (
            f"{json.dumps(contents, ensure_ascii=False)}\n"
            f"{json.dumps([batch_start, batch_end])}"
        )
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": batch_prompt},
                {"role": "user", "content": user_content},
            ],
        )
        try:
            content = response.choices[0].message.content
        except (AttributeError, IndexError, TypeError) as exc:
            raise ValueError("model response does not contain message content") from exc
        if not isinstance(content, str) or not content.strip():
            raise ValueError("model response content is empty")
        return content

    def _parse_sharegpt_records(
        self,
        response_text: str,
        batch_start: int,
        batch_end: int,
    ) -> list[dict[str, Any]]:
        json_text = _strip_json_code_fence(response_text)
        try:
            payload = json.loads(json_text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"model response is not valid JSON: {exc}") from exc

        if not isinstance(payload, list):
            raise ValueError("model response must be a JSON array")

        records: list[dict[str, Any]] = []
        for item_index, item in enumerate(payload):
            if not isinstance(item, dict):
                raise ValueError(f"response item {item_index} must be an object")

            question = item.get("question")
            if not isinstance(question, str) or not question.strip():
                question = item.get("qestion")
            answer = item.get("answer")
            content_index = item.get("content_index")

            if not isinstance(question, str) or not question.strip():
                raise ValueError(f"response item {item_index} has no non-empty question")
            if not isinstance(answer, str) or not answer.strip():
                raise ValueError(f"response item {item_index} has no non-empty answer")
            if type(content_index) is not int:
                raise ValueError(f"response item {item_index} has a non-integer content_index")
            if content_index < batch_start or content_index > batch_end:
                raise ValueError(
                    f"response item {item_index} has content_index outside "
                    f"the active range [{batch_start}, {batch_end}]"
                )

            records.append(
                {
                    "content_index": content_index,
                    "conversations": [
                        {"from": "human", "value": question.strip()},
                        {"from": "gpt", "value": answer.strip()},
                    ],
                }
            )
        return records

    def _replace_output(
        self,
        records: list[dict[str, Any]],
        output_path: Path,
    ) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n",
                dir=output_path.parent,
                prefix=f".{output_path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                json.dump(records, temporary_file, ensure_ascii=False, indent=2)
                temporary_file.write("\n")
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            os.replace(temporary_path, output_path)
            temporary_path = None
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)


def _required_environment_value(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"required environment variable is missing: {name}")
    return value


def _strip_json_code_fence(text: str) -> str:
    stripped = text.strip()
    match = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", stripped, flags=re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else stripped
