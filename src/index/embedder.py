"""bge-m3 dense 임베딩 생성.

FlagEmbedding은 함수 내부에서 지연 import — 측정 코어가 이 모듈 없이도 import 되도록.
모델은 프로세스당 한 번만 로드하는 싱글턴 패턴.
"""
from __future__ import annotations

from src.config import settings

_model = None


def _get_model():
    global _model
    if _model is None:
        import datasets  # noqa: F401  # Windows DLL 로드 순서 문제: datasets가 transformers보다 먼저여야 함

        # Windows에서 symlink 권한(WinError 1314) 없이도 동작하도록:
        # are_symlinks_supported를 False로 강제해 huggingface_hub가 copy fallback을 쓰게 함
        import huggingface_hub.file_download as _hf_fd
        _hf_fd.are_symlinks_supported = lambda cache_dir=None: False

        import torch
        from FlagEmbedding import BGEM3FlagModel  # 지연 import

        _model = BGEM3FlagModel(settings.embed_model, use_fp16=torch.cuda.is_available())
    return _model


def embed(texts: list[str], batch_size: int = 8) -> list[list[float]]:
    """텍스트 리스트 → dense 1024차원 임베딩 리스트."""
    if not texts:
        return []
    model = _get_model()
    result = model.encode(texts, batch_size=batch_size, return_dense=True)
    vecs: list[list[float]] = result["dense_vecs"].tolist()
    return vecs


def embed_full(
    texts: list[str], batch_size: int = 8
) -> tuple[list[list[float]], list[dict[str, float]]]:
    """텍스트 리스트 → (dense_vecs, sparse_vecs) 동시 반환.

    sparse_vecs: bge-m3 lexical_weights — {token_str: weight} dict 리스트.
    인제스트 및 3-way 하이브리드 검색 쿼리 임베딩에 사용.
    """
    if not texts:
        return [], []
    model = _get_model()
    result = model.encode(texts, batch_size=batch_size, return_dense=True, return_sparse=True)
    dense_vecs: list[list[float]] = result["dense_vecs"].tolist()
    # lexical_weights는 defaultdict 리스트 → 직렬화를 위해 일반 dict로 변환
    sparse_vecs: list[dict[str, float]] = [
        {k: float(v) for k, v in lw.items()} for lw in result["lexical_weights"]
    ]
    return dense_vecs, sparse_vecs
