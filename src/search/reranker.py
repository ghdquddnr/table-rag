"""BGE Cross-encoder Re-ranking (2-stage 파이프라인 Stage 2).

Stage 1: hybrid search (RRF) → top_n 후보
Stage 2: bge-reranker-v2-m3 → 최종 k개 재순위

FlagReranker는 함수 내부 지연 import — 측정 코어가 이 모듈 없이도 동작하도록.
"""
from __future__ import annotations

from src.config import settings
from src.search.hybrid import SearchResult

_reranker = None


def _get_reranker():
    global _reranker
    if _reranker is None:
        import torch
        from FlagEmbedding import FlagReranker

        _reranker = FlagReranker(
            settings.reranker_model,
            use_fp16=torch.cuda.is_available(),
        )
    return _reranker


def rerank(
    query: str,
    results: list[SearchResult],
    top_n: int | None = None,
) -> list[SearchResult]:
    """Cross-encoder로 후보 목록을 재순위화하여 반환.

    Args:
        query:   원본 검색 질의
        results: Stage 1(hybrid/dense) 검색 결과 후보 리스트
        top_n:   재순위 후 상위 N개만 반환. None이면 전체.

    Returns:
        score 필드가 cross-encoder 점수(normalize=True → 0~1 sigmoid)로
        교체되고, channels 에 'rerank' 가 추가된 SearchResult 리스트.
    """
    if not results:
        return results

    model = _get_reranker()
    pairs = [[query, r.content] for r in results]
    # normalize=True: sigmoid 변환으로 0~1 범위 → RRF score와 스케일 유사
    raw_scores: list[float] = model.compute_score(pairs, normalize=True)

    reranked = sorted(
        zip(raw_scores, results, strict=True),
        key=lambda x: x[0],
        reverse=True,
    )

    output = []
    for score, r in reranked[:top_n]:
        output.append(
            SearchResult(
                chunk_id=r.chunk_id,
                document_id=r.document_id,
                chunk_type=r.chunk_type,
                content=r.content,
                section_header=r.section_header,
                page_number=r.page_number,
                score=round(float(score), 6),
                channels=[*r.channels, "rerank"],
            )
        )
    return output
