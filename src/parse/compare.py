"""CLI: Docling vs MarkItDown 비교 → eval/parser_comparison.md 출력."""
from __future__ import annotations

import sys
from pathlib import Path

from src.parse import docling_parser, markitdown_parser
from src.parse.base import ParseResult


def _render_report(results: list[ParseResult]) -> str:
    lines = ["# Parser Comparison\n"]

    # 요약 비교 표
    lines += [
        "## 요약 비교\n",
        "| 지표 | " + " | ".join(r.parser_name.capitalize() for r in results) + " |",
        "|------|" + "|".join("------" for _ in results) + "|",
    ]
    metrics_list = [r.metrics for r in results]
    rows = [
        ("파싱 시간 (초)", [f"{r.parse_time_sec:.2f}s" for r in results]),
        ("추출된 표 수", [str(m.table_count) for m in metrics_list]),
        ("전체 셀 수", [str(m.cell_count) for m in metrics_list]),
        ("유효 셀 수 (CID 제외)", [str(m.valid_cell_count) for m in metrics_list]),
        ("CID 오염률", [f"{m.cid_contamination_rate:.1%}" for m in metrics_list]),
        ("숫자 보존률 (유효 셀 중)", [f"{m.numeric_preservation_rate:.1%}" for m in metrics_list]),
        ("헤더 인식", [str(m.has_header) for m in metrics_list]),
    ]
    for label, vals in rows:
        lines.append(f"| {label} | " + " | ".join(vals) + " |")

    lines.append("")

    # 개별 상세
    for r in results:
        m = r.metrics
        lines += [
            f"## {r.parser_name.capitalize()}\n",
            f"- **파싱 시간**: {r.parse_time_sec:.2f}s",
            f"- **표 수**: {m.table_count}개",
            f"- **전체 셀**: {m.cell_count}개 / **유효 셀**: {m.valid_cell_count}개",
            f"- **CID 오염률**: {m.cid_contamination_rate:.1%}",
            f"- **숫자 보존률**: {m.numeric_preservation_rate:.1%}",
            f"- **구조 점수**: {m.structure_score}",
            "",
        ]
        if r.error:
            lines.append(f"> ❌ Error: {r.error}\n")
        if r.tables:
            lines.append("### 첫 번째 표 샘플 (최대 600자)\n")
            lines.append(r.tables[0][:600])
            lines.append("")

    return "\n".join(lines)


def main(pdf_path: str) -> None:
    path = Path(pdf_path)
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        sys.exit(1)

    print(f"Parsing {path.name} with both parsers...")
    results = [docling_parser.parse(path), markitdown_parser.parse(path)]

    out_path = Path("eval/parser_comparison.md")
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(_render_report(results), encoding="utf-8")
    print(f"Written to {out_path}")

    for r in results:
        m = r.metrics
        print(
            f"  {r.parser_name}: {m.table_count} tables, "
            f"score={m.structure_score}, {r.parse_time_sec}s"
        )


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m src.parse.compare <pdf_path>", file=sys.stderr)
        sys.exit(1)
    main(sys.argv[1])
