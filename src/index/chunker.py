"""표 인지 청킹 — 표는 1청크로 유지, 본문은 섹션/사이즈 기반 분할.

설계 원칙:
- 표 블록: chunk_type='table', 섹션 헤더와 캡션을 컨텍스트로 부착.
- 텍스트 블록: chunk_type='text', max_chars 단위 분할.
- 무거운 import 없음 (ParseResult만 의존).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.parse.base import ParseResult

_HEADING_RE = re.compile(r"^#{1,6}\s+(.+)$", re.MULTILINE)
# 헤더 행 + 구분자 행 + 0개 이상의 데이터 행 (마지막 행의 trailing \n 선택적)
_TABLE_BLOCK_RE = re.compile(
    r"(?:^|\n)(\|.+\|\n\|[-:| ]+\|\n(?:\|.+\|\n)*(?:\|.+\|)?)",
    re.MULTILINE,
)

MAX_TEXT_CHARS = 800


@dataclass
class Chunk:
    chunk_type: str           # 'table' | 'text'
    content: str
    section_header: str | None = None
    caption: str | None = None
    page_number: int | None = None
    embedding: list[float] | None = field(default=None, repr=False)


def chunk(result: ParseResult, max_chars: int = MAX_TEXT_CHARS) -> list[Chunk]:
    """ParseResult.markdown → Chunk 리스트."""
    return _chunk_markdown(result.markdown, max_chars)


def _get_header_at(sections: list[re.Match], pos: int) -> str | None:
    """pos 이전의 가장 가까운 섹션 헤더를 반환."""
    header = None
    for m in sections:
        if m.start() <= pos:
            header = m.group(1).strip()
        else:
            break
    return header


def _extract_caption(markdown: str, table_start: int) -> str | None:
    """표 바로 앞 비어 있지 않은 텍스트 줄을 캡션으로 추출."""
    before = markdown[max(0, table_start - 300):table_start]
    candidates = [
        ln.strip()
        for ln in before.splitlines()
        if ln.strip() and not ln.startswith("#") and not ln.startswith("|")
    ]
    return candidates[-1] if candidates else None


def _chunk_markdown(markdown: str, max_chars: int) -> list[Chunk]:
    chunks: list[Chunk] = []
    sections = list(_HEADING_RE.finditer(markdown))
    table_matches = list(_TABLE_BLOCK_RE.finditer(markdown))

    # ── 표 청크 ──────────────────────────────────────────
    table_spans: list[tuple[int, int]] = []
    for m in table_matches:
        content = m.group(1).strip()
        if not content:
            continue
        start = m.start(1)
        end = m.end(1)
        table_spans.append((start, end))
        chunks.append(
            Chunk(
                chunk_type="table",
                content=content,
                section_header=_get_header_at(sections, start),
                caption=_extract_caption(markdown, start),
            )
        )

    # ── 텍스트 청크 (표 범위 제외) ────────────────────────
    prev = 0
    for t_start, t_end in sorted(table_spans):
        _append_text_chunks(chunks, markdown[prev:t_start], sections, prev, max_chars)
        prev = t_end
    _append_text_chunks(chunks, markdown[prev:], sections, prev, max_chars)

    return chunks


def _append_text_chunks(
    chunks: list[Chunk],
    segment: str,
    sections: list[re.Match],
    offset: int,
    max_chars: int,
) -> None:
    """텍스트 세그먼트를 max_chars 단위로 분할해 Chunk 리스트에 추가."""
    # 헤딩 줄 제거 후 순수 본문만
    text = _HEADING_RE.sub("", segment).strip()
    if not text:
        return
    header = _get_header_at(sections, offset)
    for i in range(0, len(text), max_chars):
        piece = text[i : i + max_chars].strip()
        if piece:
            chunks.append(Chunk(chunk_type="text", content=piece, section_header=header))
