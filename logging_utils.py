"""
로그 유틸리티
- 민감정보 마스킹 (api_key, token, password 등)
- 안전한 로그 dict 생성
- 대용량 텍스트 truncate
"""
import json
from typing import Any

_SENSITIVE_KEYS = {
    "api_key", "apikey", "token", "bot_token", "bottoken",
    "password", "passwd", "secret", "authorization", "auth",
    "cookie", "session", "session_id", "sessionid",
    "access_token", "refresh_token", "private_key",
}


def _mask_value(v: Any) -> Any:
    """문자열 값을 prefix 2자 + *** + suffix 2자로 마스킹"""
    if not isinstance(v, str):
        return v
    if len(v) <= 4:
        return "***"
    return v[:2] + "***" + v[-2:]


def mask_sensitive(data: Any) -> Any:
    """dict/list/nested 구조에서 민감 키 값을 재귀적으로 마스킹"""
    if isinstance(data, dict):
        result = {}
        for k, v in data.items():
            if k.lower() in _SENSITIVE_KEYS:
                result[k] = _mask_value(v) if isinstance(v, str) else "***"
            else:
                result[k] = mask_sensitive(v)
        return result
    if isinstance(data, list):
        return [mask_sensitive(item) for item in data]
    return data


def safe_log_dict(**kwargs) -> dict:
    """키워드 인자를 받아 마스킹 후 JSON-safe dict 반환"""
    return mask_sensitive(kwargs)


def truncate_large_text(text: str, max_len: int = 500) -> str:
    """max_len 초과 시 잘라내고 잘린 글자 수 표시"""
    if not isinstance(text, str):
        return str(text)[:max_len]
    if len(text) <= max_len:
        return text
    cut = len(text) - max_len
    return text[:max_len] + f"...[+{cut}chars truncated]"


def safe_json(obj: Any) -> str:
    """JSON 직렬화 불가 객체를 str 변환해서 처리"""
    def _default(o):
        return str(o)
    return json.dumps(obj, ensure_ascii=False, default=_default)
