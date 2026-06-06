"""CLI: Docling vs MarkItDown 비교 → eval/parser_comparison.md 출력."""
from __future__ import annotations

import sys
from pathlib import Path

from src.parse import docling_parser, markitdown_parser
from src.parse.base import ParseResult


def _render_report(results: list[ParseResult]) -> str:
    lines = ["# Parser Comparison\n"]
    for r in results:
        m = r.metrics
        lines += [
            f"## {r.parser_name.capitalize()}",
            f"- parse time: {r.parse_time_sec}s",
            f"- tables found: {m.table_count}",
            f"- total cells: {m.cell_count}",
            f"- has header: {m.has_header}",
            f"- structure score: {m.structure_score}",
            "",
        ]
        if r.error:
            lines.append(f"> ❌ Error: {r.error}\n")
        if r.tables:
            lines.append("### First Table Sample\n")
            lines.append(r.tables[0][:500])
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
