"""RRF (Reciprocal Rank Fusion) 하이브리드 검색: dense cosine + pg_trgm lexical.

§9 함정 메모:
- psycopg %(name)s 스타일에서 pg_trgm % 연산자는 %% 로 이스케이프.
- pgvector 사용 전 register_vector(conn) 필수.
- 긴 자연어 쿼리는 similarity()로 threshold를 못 넘음.
  숫자 패턴을 추출해 word_similarity(token, content) 방식으로 매칭.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import psycopg
from pgvector.psycopg import register_vector

# 소수점 숫자 (0.70, 1.5%, 44.3%) — 가장 고유, 최우선
_DECIMAL_RE = re.compile(r"\d+\.\d+%?")
# 천단위 구분자 있는 큰 숫자 (8,084 / 10,594)
_BIG_NUM_RE = re.compile(r"\d{1,3}(?:,\d{3})+")
# 2–3자리 독립 숫자 (37, 40) — 연도(4자리)는 의도적으로 제외
_SHORT_NUM_RE = re.compile(r"(?<!\d)\d{2,3}(?!\d)")


def _lexical_token(text: str) -> str | None:
    """질문에서 pg_trgm용 숫자 토큰 추출. 우선순위: 소수점 > 천단위 > 2-3자리.

    연도(4자리 독립 숫자)는 여러 chunk에 흔해 false-positive를 유발하므로 제외.
    유효 토큰이 없으면 None 반환 → 호출자가 dense-only로 폴백해야 함.
    """
    m = _DECIMAL_RE.findall(text)
    if m:
        return max(m, key=len)
    m = _BIG_NUM_RE.findall(text)
    if m:
        return max(m, key=len)
    m = _SHORT_NUM_RE.findall(text)
    if m:
        return max(m, key=len)
    return None


@dataclass
class SearchResult:
    chunk_id: int
    document_id: int
    chunk_type: str
    content: str
    section_header: str | None
    score: float


# word_similarity(token, content): token이 content의 부분 문자열과 얼마나 일치하는지.
# <% 연산자: word_similarity(a, b) > pg_trgm.word_similarity_threshold (default 0.6)
# <<-> 연산자: 1 - word_similarity(a, b) (distance, ascending sort)
_DENSE_ONLY_SQL = """
SELECT id, document_id, chunk_type, content, section_header,
       1.0 - (embedding <=> %(embedding)s::vector) AS score
FROM chunks
WHERE embedding IS NOT NULL
ORDER BY embedding <=> %(embedding)s::vector
LIMIT %(k)s
"""

_SQL = """
WITH dense AS (
    SELECT id, document_id, chunk_type, content, section_header,
           ROW_NUMBER() OVER (ORDER BY embedding <=> %(embedding)s::vector) AS rank
    FROM chunks
    WHERE embedding IS NOT NULL
    ORDER BY embedding <=> %(embedding)s::vector
    LIMIT %(top_n)s
),
lexical AS (
    SELECT id, document_id, chunk_type, content, section_header,
           ROW_NUMBER() OVER (ORDER BY %(lexical_q)s <<-> content) AS rank
    FROM chunks
    WHERE %(lexical_q)s <%% content
    ORDER BY %(lexical_q)s <<-> content
    LIMIT %(top_n)s
),
rrf AS (
    SELECT
        COALESCE(d.id,             l.id)             AS id,
        COALESCE(d.document_id,    l.document_id)    AS document_id,
        COALESCE(d.chunk_type,     l.chunk_type)     AS chunk_type,
        COALESCE(d.content,        l.content)        AS content,
        COALESCE(d.section_header, l.section_header) AS section_header,
        COALESCE(1.0 / (%(rrf_k)s + d.rank), 0)
        + COALESCE(1.0 / (%(rrf_k)s + l.rank), 0)   AS score
    FROM dense d
    FULL OUTER JOIN lexical l ON d.id = l.id
)
SELECT id, document_id, chunk_type, content, section_header, score
FROM rrf
ORDER BY score DESC
LIMIT %(k)s
"""


def search(
    query_embedding: list[float],
    query_text: str,
    conn: psycopg.Connection,
    k: int = 10,
    rrf_k: int = 60,
    top_n: int = 40,
) -> list[SearchResult]:
    """RRF 하이브리드 검색. dense + lexical(word_similarity) 순위를 RRF로 융합.

    lexical_token: 질문에서 숫자 패턴 추출 → word_similarity로 표 안 숫자 직접 매칭.
    """
    register_vector(conn)
    lexical_q = _lexical_token(query_text)
    sql = _SQL if lexical_q is not None else _DENSE_ONLY_SQL
    params: dict = {
        "embedding": query_embedding,
        "top_n": top_n,
        "rrf_k": rrf_k,
        "k": k,
    }
    if lexical_q is not None:
        params["lexical_q"] = lexical_q
    with conn.cursor() as cur:
        cur.execute(
            sql,
            params,
        )
        rows = cur.fetchall()

    return [
        SearchResult(
            chunk_id=row[0],
            document_id=row[1],
            chunk_type=row[2],
            content=row[3],
            section_header=row[4],
            score=float(row[5]),
        )
        for row in rows
    ]


if __name__ == "__main__":
    import sys

    # Windows cp949 콘솔에서 깨진 PDF 텍스트 출력 시 인코딩 오류 방지
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    import psycopg

    from src.config import settings
    from src.index.embedder import embed

    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "500명 표본"
    print(f"Query: {query}\n{'='*60}")

    emb = embed([query])[0]
    with psycopg.connect(settings.db_dsn) as conn:
        results = search(emb, query, conn, k=5)

    if not results:
        print("결과 없음 — chunks에 데이터가 있는지 확인하세요.")
    for i, r in enumerate(results, 1):
        header = f"[{r.section_header}] " if r.section_header else ""
        print(f"\n#{i} score={r.score:.4f} | {r.chunk_type} | doc={r.document_id} | {header}")
        print("-" * 60)
        print(r.content[:400])
