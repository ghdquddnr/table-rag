"""Phase 3 평가: vector-only vs hybrid (RRF) 검색 품질 비교.

지표: Recall@1, Recall@5, Recall@10, MRR@10, 숫자정답률
실행: python -m eval.run_eval
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

import psycopg
from pgvector.psycopg import register_vector

from src.search.hybrid import _lexical_token

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── 경로 설정 ──────────────────────────────────────────────────────────────
GOLDEN_SET = Path(__file__).parent / "golden_set.jsonl"

# ── SQL ────────────────────────────────────────────────────────────────────
_VECTOR_ONLY_SQL = """
SELECT id, document_id, chunk_type, content, section_header,
       1.0 - (embedding <=> %(embedding)s::vector) AS score
FROM chunks
WHERE embedding IS NOT NULL
ORDER BY embedding <=> %(embedding)s::vector
LIMIT %(k)s
"""

_HYBRID_SQL = """
WITH dense AS (
    SELECT id, document_id, chunk_type, content, section_header,
           ROW_NUMBER() OVER (ORDER BY embedding <=> %(embedding)s::vector) AS rank
    FROM chunks WHERE embedding IS NOT NULL
    ORDER BY embedding <=> %(embedding)s::vector LIMIT %(top_n)s
),
lexical AS (
    SELECT id, document_id, chunk_type, content, section_header,
           ROW_NUMBER() OVER (ORDER BY %(lexical_q)s <<-> content) AS rank
    FROM chunks WHERE %(lexical_q)s <%% content
    ORDER BY %(lexical_q)s <<-> content LIMIT %(top_n)s
),
rrf AS (
    SELECT
        COALESCE(d.id,             l.id)             AS id,
        COALESCE(d.document_id,    l.document_id)    AS document_id,
        COALESCE(d.chunk_type,     l.chunk_type)     AS chunk_type,
        COALESCE(d.content,        l.content)        AS content,
        COALESCE(d.section_header, l.section_header) AS section_header,
        COALESCE(1.0/(60+d.rank),0) + COALESCE(1.0/(60+l.rank),0) AS score
    FROM dense d FULL OUTER JOIN lexical l ON d.id = l.id
)
SELECT id, document_id, chunk_type, content, section_header, score
FROM rrf ORDER BY score DESC LIMIT %(k)s
"""


# ── 데이터 클래스 ───────────────────────────────────────────────────────────
@dataclass
class GoldenItem:
    id: str
    question: str
    expected_contains: str
    source_chunk_id: int
    chunk_type: str
    note: str = ""


@dataclass
class EvalResult:
    method: str
    recall_at: dict[int, float] = field(default_factory=dict)
    mrr: float = 0.0
    number_hit_rate: float = 0.0
    per_question: list[dict] = field(default_factory=list)


# ── 검색 함수 ───────────────────────────────────────────────────────────────
def _run_search(sql: str, params: dict, conn: psycopg.Connection) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        cols = ["chunk_id", "document_id", "chunk_type", "content", "section_header", "score"]
        return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]


def vector_search(emb: list[float], conn: psycopg.Connection, k: int = 10) -> list[dict]:
    return _run_search(_VECTOR_ONLY_SQL, {"embedding": emb, "k": k}, conn)


def hybrid_search(
    emb: list[float], query: str, conn: psycopg.Connection, k: int = 10
) -> list[dict]:
    lexical_q = _lexical_token(query)
    return _run_search(
        _HYBRID_SQL, {"embedding": emb, "lexical_q": lexical_q, "top_n": 40, "k": k}, conn
    )


# ── 지표 계산 ───────────────────────────────────────────────────────────────
def _reciprocal_rank(results: list[dict], item: GoldenItem) -> float:
    for rank, r in enumerate(results, 1):
        if r["chunk_id"] == item.source_chunk_id:
            return 1.0 / rank
    return 0.0


def _number_hit(results: list[dict], item: GoldenItem, k: int = 5) -> bool:
    """top-k 결과 중 expected_contains 문자열이 content에 존재하는지."""
    for r in results[:k]:
        if item.expected_contains in (r["content"] or ""):
            return True
    return False


def compute_metrics(items: list[GoldenItem], all_results: list[list[dict]]) -> EvalResult:
    method = ""
    rr_list, hit_list = [], []
    per_q = []
    ks = [1, 5, 10]
    recall_counts = {k: 0 for k in ks}

    for item, results in zip(items, all_results, strict=True):
        rr = _reciprocal_rank(results, item)
        rr_list.append(rr)
        hit = _number_hit(results, item)
        hit_list.append(hit)

        for k in ks:
            if any(r["chunk_id"] == item.source_chunk_id for r in results[:k]):
                recall_counts[k] += 1

        per_q.append({
            "id": item.id,
            "question": item.question[:35],
            "rr": round(rr, 3),
            "num_hit": hit,
            "top1_chunk": results[0]["chunk_id"] if results else None,
        })

    n = len(items)
    return EvalResult(
        method=method,
        recall_at={k: round(recall_counts[k] / n, 3) for k in ks},
        mrr=round(sum(rr_list) / n, 3),
        number_hit_rate=round(sum(hit_list) / n, 3),
        per_question=per_q,
    )


# ── 출력 ────────────────────────────────────────────────────────────────────
def _print_table(vector: EvalResult, hybrid: EvalResult) -> None:
    print("\n" + "=" * 65)
    print("  Phase 3 Eval — vector-only vs hybrid (RRF, k=60)")
    print("=" * 65)
    header = f"{'지표':<20} {'vector-only':>12} {'hybrid':>12} {'delta':>10}"
    print(header)
    print("-" * 65)

    rows = [
        ("Recall@1",       vector.recall_at[1],  hybrid.recall_at[1]),
        ("Recall@5",       vector.recall_at[5],  hybrid.recall_at[5]),
        ("Recall@10",      vector.recall_at[10], hybrid.recall_at[10]),
        ("MRR@10",         vector.mrr,           hybrid.mrr),
        ("숫자정답률@5",    vector.number_hit_rate, hybrid.number_hit_rate),
    ]
    for name, v, h in rows:
        delta = h - v
        sign = "+" if delta >= 0 else ""
        print(f"  {name:<18} {v:>12.3f} {h:>12.3f} {sign}{delta:>9.3f}")

    print("-" * 65)
    print("\n  Per-question (hybrid):")
    print(f"  {'ID':<5} {'Recall':>6} {'NumHit':>7} {'Top1':>6}  질문")
    print("  " + "-" * 58)
    for vq, hq in zip(vector.per_question, hybrid.per_question, strict=True):
        recall_mark = "O" if hq["rr"] > 0 else "X"
        num_mark = "O" if hq["num_hit"] else "X"
        v_recall = "O" if vq["rr"] > 0 else "X"
        print(
            f"  {hq['id']:<5} v:{v_recall}/h:{recall_mark}  {num_mark}     "
            f"{str(hq['top1_chunk']):>5}  {hq['question']}"
        )
    print("=" * 65)


# ── 메인 ────────────────────────────────────────────────────────────────────
def main() -> None:
    from src.config import settings
    from src.index.embedder import embed

    items = [
        GoldenItem(**json.loads(line))
        for line in GOLDEN_SET.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    print(f"Golden set: {len(items)}개 질문 로드")

    questions = [it.question for it in items]
    print("임베딩 중...")
    embeddings = embed(questions)
    print("검색 중...")

    with psycopg.connect(settings.db_dsn) as conn:
        register_vector(conn)
        vec_results = [
            vector_search(emb, conn, k=10) for emb, _ in zip(embeddings, items, strict=True)
        ]
        hyb_results = [
            hybrid_search(emb, it.question, conn, k=10)
            for emb, it in zip(embeddings, items, strict=True)
        ]

    vec_eval = compute_metrics(items, vec_results)
    vec_eval.method = "vector-only"
    hyb_eval = compute_metrics(items, hyb_results)
    hyb_eval.method = "hybrid"

    _print_table(vec_eval, hyb_eval)


if __name__ == "__main__":
    main()
