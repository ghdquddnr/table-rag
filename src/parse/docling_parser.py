"""Docling 파서 — TableFormer 기반 표 구조 보존."""
from __future__ import annotations

import time
from pathlib import Path

from src.parse.base import ParseResult


def _df_to_markdown(df) -> str:
    """pandas DataFrame → pipe 마크다운 표. tabulate 의존성 없음."""
    header = "| " + " | ".join(str(c) for c in df.columns) + " |"
    sep = "| " + " | ".join("---" for _ in df.columns) + " |"
    rows = ["| " + " | ".join(str(v) for v in row) + " |" for _, row in df.iterrows()]
    return "\n".join([header, sep] + rows)


def parse(path: str | Path) -> ParseResult:
    """Docling으로 PDF → 마크다운 변환. 표는 DataFrame에서 직접 추출."""
    start = time.perf_counter()
    try:
        from docling.document_converter import DocumentConverter  # 지연 import

        converter = DocumentConverter()
        result = converter.convert(str(path))
        doc = result.document

        markdown = doc.export_to_markdown()

        tables: list[str] = []
        for tbl in doc.tables:
            try:
                df = tbl.export_to_dataframe()
                tables.append(_df_to_markdown(df))
            except Exception:
                pass

        return ParseResult(
            parser_name="docling",
            markdown=markdown,
            tables=tables,
            parse_time_sec=round(time.perf_counter() - start, 3),
        )
    except Exception as e:
        return ParseResult(
            parser_name="docling",
            markdown="",
            tables=[],
            parse_time_sec=round(time.perf_counter() - start, 3),
            error=str(e),
        )
