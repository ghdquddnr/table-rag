"""파서 비교 측정 코어. 무거운 의존성 없이 import 가능해야 한다."""
from __future__ import annotations

import re
from dataclasses import dataclass, field


def _cells_from_table(tbl: str) -> list[str]:
    """표 마크다운에서 셀 텍스트 리스트를 반환한다."""
    cells = []
    for ln in tbl.splitlines():
        if "|" not in ln:
            continue
        parts = [c.strip() for c in ln.split("|") if c.strip()]
        # 구분선 행 제외 (---|--- 형태)
        if all(set(p).issubset(set("-: ")) for p in parts):
            continue
        cells.extend(parts)
    return cells


@dataclass
class TableMetrics:
    """단일 파서의 표 파싱 품질 지표."""

    table_count: int = 0
    cell_count: int = 0
    has_header: bool = False
    header_row: list[str] = field(default_factory=list)
    # 유효 셀: CID 코드가 없는 셀
    valid_cell_count: int = 0
    # 숫자 포함 셀: 숫자·퍼센트·단위가 들어있는 셀
    numeric_cell_count: int = 0

    @property
    def structure_score(self) -> float:
        """0~1 점수: 헤더 유무 + 셀 밀도 휴리스틱."""
        if self.table_count == 0:
            return 0.0
        header_bonus = 0.2 if self.has_header else 0.0
        cell_density = min(self.cell_count / max(self.table_count * 4, 1), 1.0)
        return round(0.8 * cell_density + header_bonus, 3)

    @property
    def cid_contamination_rate(self) -> float:
        """CID 코드가 포함된 셀 비율 (0=깨끗, 1=완전 오염)."""
        if self.cell_count == 0:
            return 0.0
        return round(1.0 - self.valid_cell_count / self.cell_count, 3)

    @property
    def numeric_preservation_rate(self) -> float:
        """숫자·수치가 포함된 셀 비율 (높을수록 표 데이터 활용 가능)."""
        if self.valid_cell_count == 0:
            return 0.0
        return round(self.numeric_cell_count / self.valid_cell_count, 3)


_CID_RE = re.compile(r"\(cid:\d+\)")
_NUM_RE = re.compile(r"[\d,.]+[%억원만천조]?|\d+\.\d+")


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

            cells = _cells_from_table(tbl)
            m.cell_count += len(cells)
            for cell in cells:
                if not _CID_RE.search(cell):
                    m.valid_cell_count += 1
                    if _NUM_RE.search(cell):
                        m.numeric_cell_count += 1
        return m
