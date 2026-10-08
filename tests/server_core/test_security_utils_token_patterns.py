"""ai_orchestrator.core.security_utils 값-패턴 토큰 마스킹 (키 이름 없이 값만으로 드러나는 발급 토큰)."""

from __future__ import annotations

from ai_orchestrator.core.security_utils import safe_preview


def test_openai_key_masked():
    raw = "sk-" + "a" * 30
    text = safe_preview(f"key={raw}")
    assert raw not in text
    assert "[TOKEN_REDACTED]" in text


def test_github_token_masked():
    for prefix in ("ghp_", "gho_", "ghu_", "ghs_", "ghr_", "github_pat_"):
        raw = f"{prefix}{'a' * 25}"
        text = safe_preview(f"token: {raw}")
        assert raw not in text, f"{prefix} 미마스킹"
        assert "[TOKEN_REDACTED]" in text


def test_slack_token_masked():
    for prefix in ("xoxb-", "xoxp-", "xoxa-", "xoxr-", "xoxs-"):
        raw = f"{prefix}1234567890-abcdefghij"
        text = safe_preview(raw)
        assert raw not in text, f"{prefix} 미마스킹"
        assert "[TOKEN_REDACTED]" in text


def test_aws_key_masked():
    raw = "AKIA" + "A" * 16
    text = safe_preview(f"access key {raw}")
    assert raw not in text
    assert "[TOKEN_REDACTED]" in text


def test_jwt_masked():
    part = "a" * 20
    raw = f"eyJ{part}.eyJ{part}.{part}"
    text = safe_preview(f"authorization: Bearer {raw}")
    assert raw not in text
    assert "[TOKEN_REDACTED]" in text


def test_short_sk_like_string_not_falsely_masked():
    # 너무 짧으면(흔한 단어 오탐 방지) 마스킹 대상이 아니다
    text = safe_preview("sk-123 is just a short code, not a key")
    assert "[TOKEN_REDACTED]" not in text
    assert "sk-123" in text


def test_normal_text_unaffected():
    text = safe_preview("정상적인 감사 메모입니다. 별다른 비밀정보 없음.")
    assert text == "정상적인 감사 메모입니다. 별다른 비밀정보 없음."
