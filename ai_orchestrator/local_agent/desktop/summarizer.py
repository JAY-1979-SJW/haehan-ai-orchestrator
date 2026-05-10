"""Claude API 기반 메시지 요약."""
from __future__ import annotations

import os

try:
    import anthropic
    _CLIENT = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    _AVAILABLE = True
except Exception:
    _CLIENT = None
    _AVAILABLE = False

_MODEL = "claude-haiku-4-5-20251001"
_MAX_TOKENS = 1024


def _msgs_to_text(messages: list[dict]) -> str:
    lines = []
    for m in messages:
        sender = m.get("sender", "?")
        text = m.get("text", "")
        date = m.get("date", "")
        time_ = m.get("time", "")
        lines.append(f"[{date} {time_}] {sender}: {text}")
    return "\n".join(lines)


def summarize_messages(messages: list[dict],
                       model: str = _MODEL) -> str:
    """메시지 목록 → 핵심 내용 요약 (Claude API)."""
    if not _AVAILABLE or not messages:
        return _fallback_summary(messages)

    chat_text = _msgs_to_text(messages)
    prompt = (
        "다음은 카카오 채팅 대화 내용입니다. "
        "핵심 내용을 3~5문장으로 요약해 주세요. "
        "중요한 결정사항, 요청사항, 공유된 정보를 중심으로 요약하세요.\n\n"
        f"{chat_text}"
    )
    try:
        resp = _CLIENT.messages.create(
            model=model,
            max_tokens=_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text.strip()
    except Exception as e:
        return f"[요약 실패: {e}]\n{_fallback_summary(messages)}"


def extract_action_items(messages: list[dict],
                         model: str = _MODEL) -> list[str]:
    """메시지에서 할 일/요청 항목 추출."""
    if not _AVAILABLE or not messages:
        return []
    chat_text = _msgs_to_text(messages)
    prompt = (
        "다음 채팅에서 할 일, 요청, 확인 필요 항목을 추출하세요. "
        "각 항목을 한 줄씩 '- '로 시작해 나열하세요.\n\n"
        f"{chat_text}"
    )
    try:
        resp = _CLIENT.messages.create(
            model=model,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        lines = resp.content[0].text.strip().splitlines()
        return [l.lstrip("- ").strip() for l in lines if l.strip()]
    except Exception:
        return []


def _fallback_summary(messages: list[dict]) -> str:
    """API 없을 때 단순 텍스트 요약 (최근 5개)."""
    recent = messages[-5:]
    lines = [f"{m.get('sender','?')}: {m.get('text','')}" for m in recent]
    return f"최근 {len(messages)}건 중 마지막 {len(recent)}건:\n" + "\n".join(lines)
