"""MarkItDown 파서 — 경량 대조군."""
from __future__ import annotations

import re
import time
from pathlib import Path

from src.parse.base import ParseResult

# 헤더 행 + 구분자 행 + 1개 이상의 데이터 행으로 구성된 pipe 표
_TABLE_RE = re.compile(
    r"(\|.+\|\n\|[-:| ]+\|\n(?:\|.+\|\n)*)",
    re.MULTILINE,
)


def parse(path: str | Path) -> ParseResult:
    start = time.perf_counter()
    try:
        from markitdown import MarkItDown  # 지연 import

        md_converter = MarkItDown()
        result = md_converter.convert(str(path))
        markdown = result.text_content

        tables = _TABLE_RE.findall(markdown)

        return ParseResult(
            parser_name="markitdown",
            markdown=markdown,
            tables=tables,
            parse_time_sec=round(time.perf_counter() - start, 3),
        )
    except Exception as e:
        return ParseResult(
            parser_name="markitdown",
            markdown="",
            tables=[],
            parse_time_sec=round(time.perf_counter() - start, 3),
            error=str(e),
        )
