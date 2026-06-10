"""골든셋 질문의 bge-m3 dense 임베딩을 JSON 으로 캐시 (백로그 #8).

CI 에서 2GB+ 모델 다운로드 없이 eval 을 돌리기 위한 사전 계산.
골든셋 질문이 바뀌면 다시 실행해 갱신할 것.

실행: python -m eval.make_embed_cache
출력: eval/golden_embeddings.json  ({질문ID: [1024 floats]})
"""
from __future__ import annotations

import json
from pathlib import Path

GOLDEN_SET = Path(__file__).parent / "golden_set.jsonl"
OUT_PATH = Path(__file__).parent / "golden_embeddings.json"


def main() -> None:
    from src.index.embedder import embed  # 무거운 import 지연

    items = [
        json.loads(line)
        for line in GOLDEN_SET.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    print(f"{len(items)}개 질문 임베딩 중...")
    vecs = embed([it["question"] for it in items])

    # float32 유효자릿수(~7자리)에 맞춰 반올림 — 파일 크기 절감, 코사인 순위 영향 없음
    cache = {
        it["id"]: [round(float(v), 7) for v in vec]
        for it, vec in zip(items, vecs, strict=True)
    }
    OUT_PATH.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8", newline="\n")
    print(f"OK: -> {OUT_PATH} ({OUT_PATH.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
