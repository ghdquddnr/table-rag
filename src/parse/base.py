"""파서 비교 측정 코어. 무거운 의존성 없이 import 가능해야 한다."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TableMetrics:
    """단일 파서의 표 파싱 품질 지표."""

    table_count: int = 0
    cell_count: int = 0
    has_header: bool = False
    header_row: list[str] = field(default_factory=list)

    @property
    def structure_score(self) -> float:
        """0~1 점수: 헤더 유무 + 셀 밀도 휴리스틱."""
        if self.table_count == 0:
            return 0.0
        header_bonus = 0.2 if self.has_header else 0.0
        cell_density = min(self.cell_count / max(self.table_count * 4, 1), 1.0)
        return round(0.8 * cell_density + header_bonus, 3)


@dataclass
class ParseResult:
    """파서 실행 결과 컨테이너."""

    parser_name: str       # 'docling' | 'markitdown'
    markdown: str          # 변환된 전체 마크다운
    tables: list[str]      # 추출된 표 마크다운 목록 (pipe 형식)
    parse_time_sec: float
    error: str | None = None

    @property
    def metrics(self) -> TableMetrics:
        m = TableMetrics(table_count=len(self.tables))
        for tbl in self.tables:
            lines = [ln for ln in tbl.splitlines() if "|" in ln]
            if not lines:
                continue
            cols = [c.strip() for c in lines[0].split("|") if c.strip()]
            m.header_row = cols
            if len(lines) >= 2:
                sep_cols = [c.strip() for c in lines[1].split("|") if c.strip()]
                m.has_header = all(set(c).issubset(set("-: ")) for c in sep_cols)
            m.cell_count += sum(
                len([c for c in ln.split("|") if c.strip()]) for ln in lines
            )
        return m
