"""Query Condensing 순수 로직(src.api.condense) 단위 테스트.

무거운 의존성 없이 import 되는 코어만 검증한다 (실제 LLM 호출은 제외).
"""
from src.api.condense import build_condense_user, clean_condensed


class TestBuildCondenseUser:
    def test_includes_history_and_query(self):
        history = [
            {"role": "user", "content": "2023년 부채비율은?"},
            {"role": "assistant", "content": "44.3%입니다."},
        ]
        text = build_condense_user(history, "그럼 그 시점 자산총계는?")
        assert "사용자: 2023년 부채비율은?" in text
        assert "어시스턴트: 44.3%입니다." in text
        assert "그럼 그 시점 자산총계는?" in text
        assert "[독립 질의]" in text

    def test_empty_history_marks_none(self):
        text = build_condense_user([], "질문")
        assert "(없음)" in text

    def test_keeps_only_recent_turns(self):
        history = [{"role": "user", "content": f"질문{i}"} for i in range(10)]
        text = build_condense_user(history, "최신", max_turns=3)
        assert "질문9" in text
        assert "질문0" not in text

    def test_skips_blank_entries(self):
        history = [
            {"role": "user", "content": "  "},
            {"role": "assistant", "content": "유효"},
        ]
        text = build_condense_user(history, "q")
        assert "유효" in text
        # 공백만 있는 항목은 줄로 추가되지 않음
        assert "사용자:  " not in text


class TestCleanCondensed:
    def test_takes_first_nonblank_line(self):
        assert clean_condensed("\n2023년 자산총계는?\n부연설명", "fb") == "2023년 자산총계는?"

    def test_strips_prefix(self):
        assert clean_condensed("독립 질의: 자산총계는?", "fb") == "자산총계는?"

    def test_strips_wrapping_quotes(self):
        assert clean_condensed('"자산총계는?"', "fb") == "자산총계는?"
        assert clean_condensed("'자산총계는?'", "fb") == "자산총계는?"

    def test_empty_falls_back(self):
        assert clean_condensed("", "원본질의") == "원본질의"
        assert clean_condensed("   \n  ", "원본질의") == "원본질의"

    def test_too_long_falls_back(self):
        long = "가" * 400
        assert clean_condensed(long, "원본질의") == "원본질의"

    def test_already_independent_passthrough(self):
        q = "2023년 영업이익률은 얼마인가?"
        assert clean_condensed(q, "fb") == q
