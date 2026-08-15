"""Simple live checks for QaBuilder."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from qa.qaBuilder import QaBuilder  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a live QaBuilder check.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--api-smoke", action="store_true", help="send one small API request")
    mode.add_argument("--datafile", help="exact chunks.source_name, for example UBP.pdf")
    parser.add_argument("--model", help="model name; defaults to QA_MODEL in .env")
    parser.add_argument("--per-chunk", type=int, default=50, help="indexes per request")
    args = parser.parse_args(argv)

    log_path = PROJECT_ROOT / "qa" / "test_qaBuilder.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_path, encoding="utf-8"),
        ],
        force=True,
    )
    logger = logging.getLogger("test_qaBuilder")
    logger.info(
        "[步骤 1/4] 参数完成：mode=%s，model=%s，per_chunk=%d",
        "api-smoke" if args.api_smoke else f"datafile:{args.datafile}",
        args.model or "<读取 .env QA_MODEL>",
        args.per_chunk,
    )

    try:
        logger.info("[步骤 2/4] 正在初始化 QaBuilder 和模型客户端...")
        builder = QaBuilder(model=args.model)
        logger.info("[步骤 2/4] 初始化完成，实际模型：%s", builder.model)

        if args.api_smoke:
            logger.info("[步骤 3/4] 正在发送最小 API 请求...")
            response = builder.client.chat.completions.create(
                model=builder.model,
                messages=[
                    {"role": "system", "content": "请简洁回答。"},
                    {"role": "user", "content": "请回答：1+1等于几？"},
                ],
            )
            content = response.choices[0].message.content
            if not isinstance(content, str) or not content.strip():
                raise RuntimeError("API smoke response is empty")
            logger.info("[步骤 3/4] API 返回：%s", content.strip())
        else:
            logger.info(
                "[步骤 3/4] 正在调用 getQA(dataFile=%s, per_chunk=%d)...",
                args.datafile,
                args.per_chunk,
            )
            records = builder.getQA(args.datafile, per_chunk=args.per_chunk)
            logger.info(
                "[步骤 3/4] getQA 完成：%d 条，输出：%s，批次日志：%s",
                len(records),
                builder.output_path,
                builder.log_path,
            )

        logger.info("[步骤 4/4] 测试成功；主日志：%s", log_path)
        return 0
    except Exception as exc:
        logger.error("[步骤 4/4] 测试失败：%s；主日志：%s", exc, log_path)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

# python qa/test_qaBuilder.py --datafile SST-EmotionNet.pdf --per-chunk 10
