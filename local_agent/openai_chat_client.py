"""OpenAI 직접 호출 client — Developer Test Mode 전용.

policy:
  - load_dev_key() 로 Credential Manager 에서 key 로드
  - 호출 직후 변수에서 즉시 폐기 (Authorization 헤더만 사용)
  - API key 원문 stdout/stderr/log/report/exception 미노출
  - 응답 전문 디스크 저장 0 (chat history file 0)
  - timeout / max_output / retry 제한
  - SDK 의존성 회피 — urllib 만 사용 (이미 stdlib)

상용화 기본은 server proxy mode — 본 client 는 DEVELOPER_TEST_KEY 모드에서만 사용.
"""
from __future__ import annotations

import http.client
import json
import logging
import ssl
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from . import openai_key_store as ks

logger = logging.getLogger("haehan_openai_chat")
KST = timezone(timedelta(hours=9))


# ── 설정 ─────────────────────────────────────────────────────

DEFAULT_API_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_MAX_TOKENS = 400
DEFAULT_TIMEOUT_SEC = 30
DEFAULT_RETRY = 0   # 본 공정은 retry 0 (비용 통제)
MAX_INPUT_CHARS = 8000


# ── 오류 코드 ────────────────────────────────────────────────

ERR_API_KEY_NOT_SET = "API_KEY_NOT_SET"
ERR_API_KEY_INVALID = "API_KEY_INVALID"
ERR_API_QUOTA_EXCEEDED = "API_QUOTA_EXCEEDED"
ERR_RATE_LIMITED = "RATE_LIMITED"
ERR_NETWORK_ERROR = "NETWORK_ERROR"
ERR_MODEL_NOT_AVAILABLE = "MODEL_NOT_AVAILABLE"
ERR_REQUEST_TIMEOUT = "REQUEST_TIMEOUT"
ERR_PROVIDER_ERROR = "PROVIDER_ERROR"
ERR_RESPONSE_EMPTY = "RESPONSE_EMPTY"
ERR_KEY_STORE_ERROR = "KEY_STORE_ERROR"

_USER_MSG = {
    ERR_API_KEY_NOT_SET: "OpenAI API key 가 설정되지 않았습니다. AI 설정에서 입력하세요.",
    ERR_API_KEY_INVALID: "API key 가 거부되었습니다. 키를 확인하거나 교체하세요.",
    ERR_API_QUOTA_EXCEEDED: "OpenAI 할당량 초과. 결제 정보를 확인하세요.",
    ERR_RATE_LIMITED: "요청 한도를 초과했습니다. 잠시 후 다시 시도하세요.",
    ERR_NETWORK_ERROR: "네트워크 오류가 발생했습니다. 인터넷/프록시를 확인하세요.",
    ERR_MODEL_NOT_AVAILABLE: "선택된 모델을 사용할 수 없습니다. 다른 모델을 시도하세요.",
    ERR_REQUEST_TIMEOUT: "요청 시간이 초과되었습니다. 짧은 입력으로 다시 시도하세요.",
    ERR_PROVIDER_ERROR: "OpenAI 서비스 응답 오류. 잠시 후 다시 시도하세요.",
    ERR_RESPONSE_EMPTY: "응답이 비어 있습니다. 잠시 후 다시 시도하세요.",
    ERR_KEY_STORE_ERROR: "API key 저장소 접근 실패.",
}


# ── 데이터 ───────────────────────────────────────────────────


@dataclass
class OpenAiChatRequest:
    text: str
    model: str = DEFAULT_MODEL
    max_tokens: int = DEFAULT_MAX_TOKENS
    timeout: int = DEFAULT_TIMEOUT_SEC


@dataclass
class OpenAiChatResponse:
    ok: bool
    text_redacted: str = ""
    error_code: str = ""
    user_message_kr: str = ""
    finish_reason: str = ""
    external_call_count: int = 0
    duration_ms: int = 0
    # usage 요약 (raw 응답 포함 안 함)
    usage_summary: dict = field(default_factory=dict)


# ── 호출 전 redact 통과 (요청 텍스트의 위험 패턴 marker) ─────

def _looks_clean(text: str) -> bool:
    """outbound text 가 secret 형태를 포함하는지 안전 검증.
    예방 차원 — sk-..., Bearer, device_token= 등이 있으면 caller 가 cleanup 권장.
    """
    if not text:
        return True
    low = text.lower()
    bad = ("device_token=", "registration_code=",
            "authorization: bearer", "x-api-key:",
            "openai_api_key=")
    return not any(b in low for b in bad)


# ── 핵심 client ──────────────────────────────────────────────


class OpenAiDirectTestClient:
    """OpenAI Chat Completions 직접 호출 (Dev Test 모드 전용)."""

    def __init__(self, *, model: str = DEFAULT_MODEL,
                  api_url: str = DEFAULT_API_URL,
                  account: str = ks.ACCOUNT_DEFAULT):
        self.model = model
        self.api_url = api_url
        self.account = account
        self._external_call_count = 0

    @property
    def external_call_count(self) -> int:
        return self._external_call_count

    # ── public API ──────────────────────────────────────────

    def is_configured(self) -> bool:
        try:
            return ks.has_dev_key(account=self.account)
        except Exception:
            return False

    def get_key_fingerprint(self) -> str:
        try:
            return ks.get_key_fingerprint(account=self.account)
        except Exception:
            return ""

    def health_check(self, *, timeout: int = 10) -> OpenAiChatResponse:
        """짧은 ping. 응답 길이 > 0 이면 OK."""
        return self.chat(OpenAiChatRequest(
            text="ping - 한 단어로만 응답해 주세요.",
            max_tokens=20, timeout=timeout,
        ))

    def chat(self, req: OpenAiChatRequest,
              *, _opener=None) -> OpenAiChatResponse:
        """단발성 chat completion. timeout / retry 0."""
        if not req.text or not req.text.strip():
            return self._err(ERR_RESPONSE_EMPTY, "입력이 비어 있습니다.")
        if len(req.text) > MAX_INPUT_CHARS:
            return self._err(ERR_PROVIDER_ERROR, "입력이 너무 깁니다.")

        # key 로드 (호출 직후 폐기)
        try:
            api_key = ks.load_dev_key(account=self.account)
        except Exception:
            return self._err(ERR_KEY_STORE_ERROR)
        if not api_key:
            return self._err(ERR_API_KEY_NOT_SET)

        body = json.dumps({
            "model": req.model or self.model,
            "messages": [
                {"role": "user", "content": req.text},
            ],
            "max_tokens": int(req.max_tokens),
            "temperature": 0.2,
        }).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        # API key 변수는 헤더 dict 안에만. 호출 후 즉시 폐기.
        request = urllib.request.Request(
            self.api_url, data=body, headers=headers, method="POST",
        )
        # 변수 폐기 시점은 호출 직후
        ctx = ssl.create_default_context()

        t0 = time.time()
        try:
            opener = _opener or urllib.request.urlopen
            with opener(request, timeout=req.timeout, context=ctx) as r:
                raw = r.read()
                status = r.status
        except urllib.error.HTTPError as e:
            api_key = ""
            duration = int((time.time() - t0) * 1000)
            return self._classify_http_error(e, duration)
        except urllib.error.URLError as e:
            api_key = ""
            return self._err(ERR_NETWORK_ERROR,
                              extra=str(e.reason)[:80])
        except TimeoutError:
            api_key = ""
            return self._err(ERR_REQUEST_TIMEOUT)
        except http.client.HTTPException as e:
            api_key = ""
            return self._err(ERR_PROVIDER_ERROR,
                              extra=type(e).__name__)
        except Exception as e:
            api_key = ""
            return self._err(ERR_NETWORK_ERROR,
                              extra=type(e).__name__)
        finally:
            api_key = ""

        duration = int((time.time() - t0) * 1000)
        self._external_call_count += 1
        try:
            data = json.loads(raw.decode("utf-8"))
        except Exception:
            return self._err(ERR_PROVIDER_ERROR,
                              extra="json_parse",
                              duration=duration)
        return self._parse_success(data, status=status, duration=duration)

    # ── 내부 helpers ────────────────────────────────────────

    def _parse_success(self, data: dict, *, status: int,
                        duration: int) -> OpenAiChatResponse:
        try:
            choices = data.get("choices") or []
            if not choices:
                return self._err(ERR_RESPONSE_EMPTY,
                                  duration=duration)
            msg = choices[0].get("message") or {}
            text = (msg.get("content") or "").strip()
            if not text:
                return self._err(ERR_RESPONSE_EMPTY,
                                  duration=duration)
            finish = choices[0].get("finish_reason", "")
            usage = data.get("usage") or {}
            summary = {
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                "total_tokens": usage.get("total_tokens"),
                "model": data.get("model"),
            }
            # redact 1차 (echo back 보호)
            from . import ai_chat_client as _aic
            text_red = _aic.redact_input(text)
            return OpenAiChatResponse(
                ok=True, text_redacted=text_red,
                finish_reason=finish, external_call_count=1,
                duration_ms=duration, usage_summary=summary,
            )
        except Exception:
            return self._err(ERR_PROVIDER_ERROR,
                              extra="parse",
                              duration=duration)

    def _classify_http_error(self, e: urllib.error.HTTPError,
                              duration: int) -> OpenAiChatResponse:
        code = e.code
        # body 본문은 디스크 저장 0 — 분류용으로 짧게 읽고 즉시 폐기
        try:
            body_excerpt = e.read().decode("utf-8", errors="replace")[:200]
        except Exception:
            body_excerpt = ""
        ec = None
        if code == 401:
            ec = ERR_API_KEY_INVALID
        elif code == 429:
            low = body_excerpt.lower()
            if "quota" in low or "insufficient" in low:
                ec = ERR_API_QUOTA_EXCEEDED
            else:
                ec = ERR_RATE_LIMITED
        elif code == 404:
            if "model" in body_excerpt.lower():
                ec = ERR_MODEL_NOT_AVAILABLE
            else:
                ec = ERR_PROVIDER_ERROR
        elif code in (408, 504):
            ec = ERR_REQUEST_TIMEOUT
        elif 500 <= code < 600:
            ec = ERR_PROVIDER_ERROR
        else:
            ec = ERR_PROVIDER_ERROR
        # body_excerpt 는 보고서/예외에 절대 노출 안 함
        return self._err(ec, duration=duration)

    def _err(self, code: str, message_kr: str | None = None,
              *, extra: str = "", duration: int = 0
              ) -> OpenAiChatResponse:
        return OpenAiChatResponse(
            ok=False, error_code=code,
            user_message_kr=message_kr or _USER_MSG.get(code, "오류 발생"),
            external_call_count=0,
            duration_ms=duration,
        )


# ── live smoke helper ───────────────────────────────────────


def live_smoke(*, account: str = ks.ACCOUNT_DEFAULT,
                model: str = DEFAULT_MODEL) -> dict:
    """짧은 OpenAI 호출 1회. report 용 dict 반환 (redacted)."""
    client = OpenAiDirectTestClient(model=model, account=account)
    if not client.is_configured():
        return {
            "ok": False, "error_code": ERR_API_KEY_NOT_SET,
            "external_call_count": 0,
            "note": "no key in Credential Manager (haehan-openai-dev)",
        }
    fp = client.get_key_fingerprint()
    t0 = time.time()
    resp = client.health_check(timeout=20)
    elapsed = int((time.time() - t0) * 1000)
    # text_redacted 일부만 (80자 cap)
    preview = (resp.text_redacted or "")[:80]
    return {
        "ok": resp.ok,
        "error_code": resp.error_code,
        "external_call_count": client.external_call_count,
        "duration_ms": elapsed,
        "model": model,
        "fingerprint": fp,
        "response_preview_redacted": preview,
        "response_length": len(resp.text_redacted),
        "usage_summary": resp.usage_summary,
        "finish_reason": resp.finish_reason,
        "user_message_kr": resp.user_message_kr,
    }


__all__ = (
    "OpenAiDirectTestClient", "OpenAiChatRequest", "OpenAiChatResponse",
    "live_smoke",
    "DEFAULT_MODEL", "DEFAULT_MAX_TOKENS", "DEFAULT_TIMEOUT_SEC",
    "ERR_API_KEY_NOT_SET", "ERR_API_KEY_INVALID",
    "ERR_API_QUOTA_EXCEEDED", "ERR_RATE_LIMITED",
    "ERR_NETWORK_ERROR", "ERR_MODEL_NOT_AVAILABLE",
    "ERR_REQUEST_TIMEOUT", "ERR_PROVIDER_ERROR",
    "ERR_RESPONSE_EMPTY", "ERR_KEY_STORE_ERROR",
)
