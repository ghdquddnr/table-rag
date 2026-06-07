"""Query Condensing (백로그 #2) — 순수 로직 코어.

멀티턴 후속 질문("그럼 그 시점 자산총계는?")을 대화 맥락 없이도
단독 검색 가능한 질의로 재작성하기 위한 프롬프트 조립/후처리.

무거운 의존성(ollama·httpx) 0 → 단위 테스트로 보호. 실제 LLM 호출은 api.main 담당.
"""
from __future__ import annotations

# 재작성기 system 프롬프트. 새 정보 생성 금지, 한 줄 출력 강제.
CONDENSE_SYSTEM = (
    "너는 검색 질의 재작성기다. 아래 대화 기록과 후속 질문을 보고, "
    "후속 질문을 대화 맥락 없이도 단독으로 검색 가능한 한국어 질의로 재작성하라.\n"
    "규칙:\n"
    "- 대명사(이것/그/해당/위)와 생략된 주어·대상을 대화 기록에서 복원해 명시한다.\n"
    "- 문서에 없는 새로운 정보를 추가하거나 추측하지 않는다.\n"
    "- 후속 질문이 이미 독립적이면 그대로 반환한다.\n"
    "- 재작성된 질의 한 줄만 출력한다. 설명·따옴표·접두어 금지."
)

# 재작성 결과 허용 최대 길이(자). 초과 시 모델이 폭주한 것으로 보고 원본 사용.
_MAX_CONDENSED_LEN = 300


def build_condense_user(history: list[dict], query: str, max_turns: int = 6) -> str:
    """대화 기록 + 후속 질문을 재작성기 입력 텍스트로 조립한다.

    최근 ``max_turns`` 턴만 사용해 토큰을 절약한다.
    """
    recent = history[-max_turns:] if max_turns > 0 else history
    lines = []
    for h in recent:
        speaker = "어시스턴트" if h.get("role") == "assistant" else "사용자"
        content = (h.get("content") or "").strip()
        if content:
            lines.append(f"{speaker}: {content}")
    convo = "\n".join(lines) if lines else "(없음)"
    return f"[대화 기록]\n{convo}\n\n[후속 질문]\n{query}\n\n[독립 질의]"


def clean_condensed(raw: str, fallback: str) -> str:
    """LLM 재작성 결과를 정제한다.

    - 첫 비어 있지 않은 줄만 취한다.
    - 흔한 접두어("독립 질의:", "검색 질의:")와 감싼 따옴표를 제거한다.
    - 비었거나 비정상적으로 길면 ``fallback``(원본 질의)을 반환한다.
    """
    if not raw:
        return fallback

    line = ""
    for candidate in raw.splitlines():
        if candidate.strip():
            line = candidate.strip()
            break
    if not line:
        return fallback

    # 접두어 제거
    for prefix in ("독립 질의:", "독립질의:", "검색 질의:", "검색질의:", "질의:", "재작성:"):
        if line.startswith(prefix):
            line = line[len(prefix):].strip()
            break

    # 감싼 따옴표 제거
    if len(line) >= 2 and line[0] in "\"'`" and line[-1] == line[0]:
        line = line[1:-1].strip()

    if not line or len(line) > _MAX_CONDENSED_LEN:
        return fallback
    return line
