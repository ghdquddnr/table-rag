"""청커 단위 테스트 — 무거운 의존성 없이 동작해야 한다."""
from src.index.chunker import MAX_TEXT_CHARS, chunk
from src.parse.base import ParseResult


def _make_result(markdown: str) -> ParseResult:
    return ParseResult(parser_name="test", markdown=markdown, tables=[], parse_time_sec=0.0)


def test_table_chunk_type():
    md = "## 실적\n\n| 연도 | 매출 |\n|------|------|\n| 2023 | 100억 |\n"
    result = _make_result(md)
    chunks = chunk(result)
    table_chunks = [c for c in chunks if c.chunk_type == "table"]
    assert len(table_chunks) == 1
    assert "2023" in table_chunks[0].content


def test_table_inherits_section_header():
    md = "## 재무 현황\n\n| 항목 | 값 |\n|------|----|\n| 매출 | 50 |\n"
    chunks = chunk(_make_result(md))
    table_chunks = [c for c in chunks if c.chunk_type == "table"]
    assert table_chunks[0].section_header == "재무 현황"


def test_text_chunk_max_size():
    long_text = "가나다 " * 1000
    chunks = chunk(_make_result(long_text))
    text_chunks = [c for c in chunks if c.chunk_type == "text"]
    for c in text_chunks:
        assert len(c.content) <= MAX_TEXT_CHARS


def test_no_chunks_for_empty_markdown():
    chunks = chunk(_make_result(""))
    assert chunks == []


def test_table_not_duplicated_in_text():
    md = "본문입니다.\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\n후속 텍스트."
    chunks = chunk(_make_result(md))
    table_chunks = [c for c in chunks if c.chunk_type == "table"]
    text_chunks = [c for c in chunks if c.chunk_type == "text"]
    # 표 내용이 텍스트 청크에 중복 포함되지 않아야 함
    for tc in text_chunks:
        assert "| A |" not in tc.content
    assert len(table_chunks) == 1
