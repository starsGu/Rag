"""Generate ShareGPT question-answer data from stored corpus chunks."""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import sys
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
    def __init__(
        self,
        corpus_db_path: str | Path = DEFAULT_CORPUS_DB_PATH,
        model: str | None = None,
    ):
        self.corpus_db_path = Path(corpus_db_path)
        self.output_path: Path | None = None
        self.log_path = DEFAULT_OUTPUT_DIR / "qaBuilder.log"
        self.logger = logging.getLogger(f"QaBuilder.{id(self)}")
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False
        for handler in self.logger.handlers:
            handler.close()
        self.logger.handlers.clear()
        formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        console_handler = logging.StreamHandler(sys.stdout)
        file_handler = logging.FileHandler(self.log_path, encoding="utf-8")
        console_handler.setFormatter(formatter)
        file_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)
        self.logger.addHandler(file_handler)
        from dotenv import load_dotenv
        from openai import OpenAI

        load_dotenv(PROJECT_ROOT / ".env")
        api_key = os.getenv("QA_API_KEY", "").strip()
        if not api_key:
            raise ValueError("required environment variable is missing: QA_API_KEY")
        if model is not None and (not isinstance(model, str) or not model.strip()):
            raise ValueError("model must be a non-empty string")
        self.model = model.strip() if model is not None else os.getenv("QA_MODEL", "").strip()
        if not self.model:
            raise ValueError("required environment variable is missing: QA_MODEL")
        base_url = os.getenv("QA_BASE_URL", DEFAULT_BASE_URL).strip()
        self.client = OpenAI(base_url=base_url or DEFAULT_BASE_URL, api_key=api_key)

    def getQA(self, dataFile: str, per_chunk: int = 50) -> list[dict[str, Any]]:
        if type(per_chunk) is not int or per_chunk <= 0:
            raise ValueError("per_chunk must be a positive integer")
        if not isinstance(dataFile, str) or not dataFile.strip():
            raise ValueError("dataFile must be a non-empty source filename")
        if not self.corpus_db_path.is_file():
            raise FileNotFoundError(f"corpus database not found: {self.corpus_db_path}")

        connection = sqlite3.connect(
            f"{self.corpus_db_path.resolve().as_uri()}?mode=ro",
            uri=True,
        )
        try:
            rows = connection.execute(
                "SELECT content FROM chunks WHERE source_name = ? ORDER BY chunk_index, id",
                (dataFile,),
            ).fetchall()
        finally:
            connection.close()
        contents = [row[0] for row in rows]
        if not contents:
            raise ValueError(f"no chunks found for source filename: {dataFile}")

        output_stem = Path(Path(dataFile).name).stem
        if not output_stem:
            raise ValueError(f"dataFile has no usable filename stem: {dataFile}")
        self.output_path = DEFAULT_OUTPUT_DIR / f"{output_stem}.json"
        temporary_path = self.output_path.with_name(f".{self.output_path.name}.tmp")
        records: list[dict[str, Any]] = []
        try:
            temporary_path.write_text("[]\n", encoding="utf-8")
            os.replace(temporary_path, self.output_path)
        finally:
            temporary_path.unlink(missing_ok=True)

        total_batches = (len(contents) + per_chunk - 1) // per_chunk
        self._log(
            "模型：%s；读取到 %d 个分块；per_chunk=%d；输出文件：%s",
            self.model,
            len(contents),
            per_chunk,
            self.output_path,
        )
        for batch_start in range(0, len(contents), per_chunk):
            batch_end = min(batch_start + per_chunk - 1, len(contents) - 1)
            batch_number = batch_start // per_chunk + 1
            self._log(
                "[%d/%d] 请求分块 [%d,%d]...",
                batch_number,
                total_batches,
                batch_start,
                batch_end,
            )
            response_text = ""
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {
                            "role": "system",
                            "content": SYSTEM_PROMPT.replace(
                                "[a, b]", f"[{batch_start}, {batch_end}]"
                            ),
                        },
                        {
                            "role": "user",
                            "content": (
                                f"{json.dumps(contents, ensure_ascii=False)}\n"
                                f"{json.dumps([batch_start, batch_end])}"
                            ),
                        },
                    ],
                )
                response_text = response.choices[0].message.content
                batch_records = self._parse_response(
                    response_text, batch_start, batch_end
                )
                for record in batch_records:
                    question = record["conversations"][1]["value"]
                    record["conversations"][1]["value"] = (
                        f"根据 {dataFile} 论文，{question}"
                    )
            except Exception as exc:
                self._log(
                    "[%d/%d] 分块 [%d,%d] 失败：%s",
                    batch_number,
                    total_batches,
                    batch_start,
                    batch_end,
                    exc,
                    level=logging.ERROR,
                )
                if isinstance(response_text, str) and response_text.strip():
                    self._log(
                        "模型回复片段：%s",
                        response_text.strip()[:500],
                        level=logging.ERROR,
                    )
                raise

            records.extend(batch_records)
            try:
                temporary_path.write_text(
                    json.dumps(records, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                os.replace(temporary_path, self.output_path)
            finally:
                temporary_path.unlink(missing_ok=True)
            self._log(
                "[%d/%d] 完成，本批 %d 条，累计 %d 条，已写入 %s",
                batch_number,
                total_batches,
                len(batch_records),
                len(records),
                self.output_path,
            )
        self._log("全部完成，共生成 %d 条；日志：%s", len(records), self.log_path)
        return records

    def _parse_response(self, text: str, a: int, b: int) -> list[dict[str, Any]]:
        if not isinstance(text, str) or not text.strip():
            raise ValueError("model response content is empty")
        fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.IGNORECASE | re.DOTALL)
        cleaned = fenced.group(1) if fenced else text
        array_start = re.search(r"\[\s*(?:\]|//|\{)", cleaned)
        array_end = cleaned.rfind("]")
        if array_start is None or array_end < array_start.start():
            raise ValueError("model response does not contain a JSON array")
        cleaned = cleaned[array_start.start() : array_end + 1]
        cleaned = "\n".join(
            line for line in cleaned.splitlines() if not line.lstrip().startswith("//")
        )
        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError:
            payload = []
            decoder = json.JSONDecoder()
            body = cleaned[1:-1]
            position = 0
            while position < len(body):
                while position < len(body) and (body[position].isspace() or body[position] == ","):
                    position += 1
                if position >= len(body):
                    break
                try:
                    item, position = decoder.raw_decode(body, position)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"model response is not valid commented JSON: {exc}") from exc
                payload.append(item)

        if not isinstance(payload, list):
            raise ValueError("model response must be a JSON array")
        records: list[dict[str, Any]] = []
        for item_index, item in enumerate(payload):
            if not isinstance(item, dict):
                raise ValueError(f"response item {item_index} must be an object")
            question = item.get("question") or item.get("qestion")
            answer = item.get("answer")
            content_index = item.get("content_index")
            if not isinstance(question, str) or not question.strip():
                raise ValueError(f"response item {item_index} has no non-empty question")
            if not isinstance(answer, str) or not answer.strip():
                raise ValueError(f"response item {item_index} has no non-empty answer")
            if type(content_index) is not int:
                raise ValueError(f"response item {item_index} has a non-integer content_index")
            if content_index < a or content_index > b:
                raise ValueError(
                    f"response item {item_index} has content_index outside [{a},{b}]"
                )
            records.append(
                {
                    "content_index": content_index,
                    "conversations": [
                        {"from": "system","value": "你是一个专业领域问答助手,请基于所学知识准确回答用户的问题"},
                        {"from": "human", "value": question.strip()},
                        {"from": "gpt", "value": answer.strip()},
                    ],
                }
            )
        return records

    def _log(
        self,
        message: str,
        *args: Any,
        level: int = logging.INFO,
    ) -> None:
        self.logger.log(level, message, *args)
        for handler in self.logger.handlers:
            handler.flush()


# python qa/test_qaBuilder.py --datafile GANSER.pdf --per-chunk 10
