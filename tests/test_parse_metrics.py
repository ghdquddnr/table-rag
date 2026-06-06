"""측정 코어 테스트 — 무거운 의존성(docling, FlagEmbedding) 없이 동작해야 한다."""
from src.parse.base import ParseResult


def test_empty_result_has_zero_score():
    r = ParseResult(parser_name="test", markdown="", tables=[], parse_time_sec=0.0)
    m = r.metrics
    assert m.table_count == 0
    assert m.structure_score == 0.0


def test_table_with_header_detected():
    tbl = "| A | B |\n|---|---|\n| 1 | 2 |\n"
    r = ParseResult(parser_name="test", markdown=tbl, tables=[tbl], parse_time_sec=0.1)
    m = r.metrics
    assert m.table_count == 1
    assert m.has_header is True
    assert m.cell_count > 0
    assert m.structure_score > 0


def test_table_without_separator_no_header():
    tbl = "| A | B |\n| 1 | 2 |\n"
    r = ParseResult(parser_name="test", markdown=tbl, tables=[tbl], parse_time_sec=0.0)
    m = r.metrics
    assert m.has_header is False


def test_structure_score_in_range():
    tbl = "| X | Y | Z |\n|---|---|---|\n| a | b | c |\n| d | e | f |\n"
    r = ParseResult(parser_name="test", markdown=tbl, tables=[tbl], parse_time_sec=0.0)
    assert 0.0 <= r.metrics.structure_score <= 1.0


def test_multiple_tables_count():
    tbl = "| A |\n|---|\n| 1 |\n"
    r = ParseResult(parser_name="test", markdown="", tables=[tbl, tbl], parse_time_sec=0.0)
    assert r.metrics.table_count == 2
