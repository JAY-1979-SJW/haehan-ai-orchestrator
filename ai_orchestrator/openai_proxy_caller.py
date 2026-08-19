"""서버측 OpenAI Chat Completions 호출 (proxy 용).

policy:
  - OPENAI_API_KEY 는 서버 env 에서만 (사용자 PC 0)
  - key 변수는 호출 직후 폐기
  - 로그에 key/응답 전문 0
  - usage summary / 응답 길이 / preview 80자 만 호출자에게 반환
"""

from __future__ import annotations

import http.client
import json
import logging
import os
import ssl
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from ai_orchestrator.app_llm import APP_LLM_QUALITY_MODEL
from ai_orchestrator.openai_guard import assert_openai_allowed

logger = logging.getLogger("haehan_openai_proxy")


DEFAULT_API_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_MODEL = APP_LLM_QUALITY_MODEL  # 앱 표준=GPT (app_llm 단일 출처)
DEFAULT_MAX_TOKENS = 400
DEFAULT_TIMEOUT_SEC = 30
MAX_INPUT_CHARS = 8000


# server-side 오류 코드 (desktop 오류 코드와 매핑 호환)
ERR_API_KEY_NOT_SET = "API_KEY_NOT_SET"
ERR_API_KEY_INVALID = "API_KEY_INVALID"
ERR_API_QUOTA_EXCEEDED = "API_QUOTA_EXCEEDED"
ERR_RATE_LIMITED = "RATE_LIMITED"
ERR_NETWORK_ERROR = "NETWORK_ERROR"
ERR_MODEL_NOT_AVAILABLE = "MODEL_NOT_AVAILABLE"
ERR_REQUEST_TIMEOUT = "REQUEST_TIMEOUT"
ERR_PROVIDER_ERROR = "PROVIDER_ERROR"
ERR_RESPONSE_EMPTY = "RESPONSE_EMPTY"


@dataclass
class ProxyCallResult:
    ok: bool
    text: str = ""
    error_code: str = ""
    finish_reason: str = ""
    usage_summary: dict | None = None
    duration_ms: int = 0
    model_used: str = ""


def has_server_openai_key() -> bool:
    v = os.environ.get("OPENAI_API_KEY", "").strip()
    return bool(v) and len(v) >= 20


def get_default_model() -> str:
    return os.environ.get("OPENAI_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL


def call_openai_chat(
    *,
    message: str,
    model: str | None = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    timeout: int = DEFAULT_TIMEOUT_SEC,
    _opener=None,
    _api_url: str = DEFAULT_API_URL,
) -> ProxyCallResult:
    """env OPENAI_API_KEY 사용. 변수는 함수 scope 안에서만."""
    assert_openai_allowed("openai_proxy_caller.py:call_openai_chat")
    if not message or not message.strip():
        return ProxyCallResult(ok=False, error_code=ERR_RESPONSE_EMPTY)
    if len(message) > MAX_INPUT_CHARS:
        return ProxyCallResult(ok=False, error_code=ERR_PROVIDER_ERROR)

    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key or len(api_key) < 20:
        return ProxyCallResult(ok=False, error_code=ERR_API_KEY_NOT_SET)

    body = json.dumps(
        {
            "model": (model or get_default_model()),
            "messages": [{"role": "user", "content": message}],
            "max_tokens": int(max_tokens),
            "temperature": 0.2,
        }
    ).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    request = urllib.request.Request(  # noqa: S310
        _api_url,
        data=body,
        headers=headers,
        method="POST",
    )
    ctx = ssl.create_default_context()
    t0 = time.time()
    try:
        opener = _opener or urllib.request.urlopen
        with opener(request, timeout=timeout, context=ctx) as r:
            raw = r.read()
    except urllib.error.HTTPError as e:
        api_key = ""
        dur = int((time.time() - t0) * 1000)
        return _classify_http_error(e, duration=dur)
    except urllib.error.URLError:
        api_key = ""
        return ProxyCallResult(ok=False, error_code=ERR_NETWORK_ERROR)
    except TimeoutError:
        api_key = ""
        return ProxyCallResult(ok=False, error_code=ERR_REQUEST_TIMEOUT)
    except http.client.HTTPException:
        api_key = ""
        return ProxyCallResult(ok=False, error_code=ERR_PROVIDER_ERROR)
    except Exception:
        api_key = ""
        return ProxyCallResult(ok=False, error_code=ERR_NETWORK_ERROR)
    finally:
        api_key = ""

    dur = int((time.time() - t0) * 1000)
    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception:
        return ProxyCallResult(ok=False, error_code=ERR_PROVIDER_ERROR, duration_ms=dur)
    return _parse_success(data, dur)


def call_openai_agent(
    *,
    messages: list[dict],
    tools: list[dict] | None = None,
    model: str | None = None,
    max_tokens: int = 700,
    timeout: int = 60,
    _opener=None,
    _api_url: str = DEFAULT_API_URL,
) -> dict:
    """OpenAI function-calling 1턴 호출. assistant 메시지(content/tool_calls)를 반환.

    자율 도구호출 에이전트(free_agent)용. 기존 call_openai_chat은 보존.
    반환: {"ok": bool, "message": {...}|None, "error_code": str, "model": str}
    """
    assert_openai_allowed("openai_proxy_caller.py:call_openai_agent")
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key or len(api_key) < 20:
        return {"ok": False, "error_code": ERR_API_KEY_NOT_SET}
    payload: dict = {
        "model": (model or get_default_model()),
        "messages": messages,
        "max_tokens": int(max_tokens),
        "temperature": 0.2,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    request = urllib.request.Request(_api_url, data=body, headers=headers, method="POST")  # noqa: S310
    ctx = ssl.create_default_context()
    try:
        opener = _opener or urllib.request.urlopen
        with opener(request, timeout=timeout, context=ctx) as r:
            raw = r.read()
    except urllib.error.HTTPError as e:
        api_key = ""
        return {"ok": False, "error_code": _classify_http_error(e, duration=0).error_code}
    except (urllib.error.URLError, TimeoutError):
        api_key = ""
        return {"ok": False, "error_code": ERR_NETWORK_ERROR}
    except Exception:
        api_key = ""
        return {"ok": False, "error_code": ERR_PROVIDER_ERROR}
    finally:
        api_key = ""
    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception:
        return {"ok": False, "error_code": ERR_PROVIDER_ERROR}
    choices = data.get("choices") or []
    if not choices:
        return {"ok": False, "error_code": ERR_RESPONSE_EMPTY}
    return {
        "ok": True,
        "message": choices[0].get("message") or {},
        "finish_reason": choices[0].get("finish_reason", ""),
        "model": data.get("model", ""),
    }


def _parse_success(data: dict, dur: int) -> ProxyCallResult:
    choices = data.get("choices") or []
    if not choices:
        return ProxyCallResult(ok=False, error_code=ERR_RESPONSE_EMPTY, duration_ms=dur)
    msg = choices[0].get("message") or {}
    text = (msg.get("content") or "").strip()
    if not text:
        return ProxyCallResult(ok=False, error_code=ERR_RESPONSE_EMPTY, duration_ms=dur)
    usage = data.get("usage") or {}
    return ProxyCallResult(
        ok=True,
        text=text,
        finish_reason=choices[0].get("finish_reason", ""),
        usage_summary={
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "total_tokens": usage.get("total_tokens"),
        },
        duration_ms=dur,
        model_used=data.get("model", ""),
    )


def _classify_http_error(e: urllib.error.HTTPError, *, duration: int) -> ProxyCallResult:
    code = e.code
    try:
        body = e.read().decode("utf-8", errors="replace")[:200].lower()
    except Exception:
        body = ""
    if code == 401:
        ec = ERR_API_KEY_INVALID
    elif code == 429:
        ec = ERR_API_QUOTA_EXCEEDED if ("quota" in body or "insufficient" in body) else ERR_RATE_LIMITED
    elif code == 404:
        ec = ERR_MODEL_NOT_AVAILABLE if "model" in body else ERR_PROVIDER_ERROR
    elif code in (408, 504):
        ec = ERR_REQUEST_TIMEOUT
    elif 500 <= code < 600:
        ec = ERR_PROVIDER_ERROR
    else:
        ec = ERR_PROVIDER_ERROR
    return ProxyCallResult(ok=False, error_code=ec, duration_ms=duration)


__all__ = (
    "DEFAULT_MODEL",
    "MAX_INPUT_CHARS",
    "ProxyCallResult",
    "call_openai_chat",
    "get_default_model",
    "has_server_openai_key",
)
