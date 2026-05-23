"""Server Proxy AI Chat 클라이언트 (상용 기본 모드).

흐름:
  데스크앱 (agent_id + device_token) → 서버 /agent-ai/chat → 서버가 OpenAI 호출 →
  응답 → 데스크앱

policy:
  - 사용자 PC 에 OpenAI API key 0
  - device_token 은 token_store 에서 로드, 헤더에만, 로그 0
  - raw chat history 디스크 저장 0
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

from . import connection_diagnostics as cd
from . import gui_state as gs
from . import network_bypass as nb
from . import token_store as ts

logger = logging.getLogger("haehan_server_proxy_chat")


PROXY_PATH_CHAT = "/api/v1/agent-ai/chat"
PROXY_PATH_HEALTH = "/api/v1/agent-ai/health"


# 오류 코드 (openai_chat_client 와 호환)
ERR_API_KEY_NOT_SET = "API_KEY_NOT_SET"        # 서버 env 미설정
ERR_API_KEY_INVALID = "API_KEY_INVALID"
ERR_AUTH_FAILED = "AUTH_FAILED_4401"
ERR_AGENT_ID_MISSING = "AGENT_ID_MISSING"
ERR_DEVICE_TOKEN_MISSING = "DEVICE_TOKEN_MISSING"
ERR_API_QUOTA_EXCEEDED = "API_QUOTA_EXCEEDED"
ERR_RATE_LIMITED = "RATE_LIMITED"
ERR_NETWORK_ERROR = "NETWORK_ERROR"
ERR_REQUEST_TIMEOUT = "REQUEST_TIMEOUT"
ERR_PROVIDER_ERROR = "PROVIDER_ERROR"
ERR_RESPONSE_EMPTY = "RESPONSE_EMPTY"
ERR_SERVER_NOT_REACHABLE = "SERVER_NOT_REACHABLE"


@dataclass
class ProxyChatResponse:
    ok: bool
    text_redacted: str = ""
    error_code: str = ""
    user_message_kr: str = ""
    model: str = ""
    usage_summary: dict = field(default_factory=dict)
    external_call_count: int = 0       # 서버가 OpenAI 호출한 횟수
    duration_ms: int = 0


def _build_url(server_base_url: str, path: str) -> str:
    base = (server_base_url or "").rstrip("/")
    return base + path


class ServerProxyChatClient:
    """데스크앱 서버 proxy chat client."""

    def __init__(self, *, server_url: str, agent_id: str,
                  default_timeout: int = 30):
        self.server_url = server_url
        self.agent_id = agent_id
        self.default_timeout = default_timeout

    # ── public ──────────────────────────────────────────

    def is_configured(self) -> bool:
        """agent_id 와 device_token 둘 다 있어야 사용 가능."""
        if not self.agent_id or not self.server_url:
            return False
        try:
            return ts.has_device_token(server_url=self.server_url,
                                          agent_id=self.agent_id)
        except Exception:
            return False

    def health_check(self, *, timeout: int = 10) -> ProxyChatResponse:
        return self._request(method="GET", path=PROXY_PATH_HEALTH,
                              body=None, timeout=timeout)

    def chat(self, message: str, *, model: str | None = None,
              timeout: int | None = None,
              _opener=None) -> ProxyChatResponse:
        if not message or not message.strip():
            return self._err(ERR_RESPONSE_EMPTY,
                              user_msg="메시지가 비어 있습니다.")
        body = {
            "message": message,
            "client_mode": "SERVER_PROXY",
        }
        if model:
            body["model"] = model
        return self._request(
            method="POST", path=PROXY_PATH_CHAT,
            body=body, timeout=timeout or self.default_timeout,
            _opener=_opener,
        )

    # ── internal ────────────────────────────────────────

    def _load_token(self) -> str:
        return ts.load_device_token(server_url=self.server_url,
                                      agent_id=self.agent_id) or ""

    def _request(self, *, method: str, path: str,
                  body: dict | None, timeout: int,
                  _opener=None) -> ProxyChatResponse:
        if not self.agent_id:
            return self._err(ERR_AGENT_ID_MISSING,
                              "agent_id 가 없습니다. 먼저 등록하세요.")
        token = self._load_token()
        if not token:
            return self._err(ERR_DEVICE_TOKEN_MISSING,
                              "device_token 이 없습니다. 재등록하세요.")
        url = _build_url(self.server_url, path)
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Agent-Id": self.agent_id,
            "Authorization": f"Bearer {token}",
        }
        token = ""   # 즉시 폐기
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, headers=headers,
                                       method=method)
        ctx = ssl.create_default_context()
        t0 = time.time()
        try:
            opener = _opener or nb.urlopen_for_server
            if _opener is None:
                rctx = opener(self.server_url, req, timeout=timeout, context=ctx)
            else:
                rctx = opener(req, timeout=timeout, context=ctx)
            with rctx as r:
                raw = r.read()
                status = r.status
        except urllib.error.HTTPError as e:
            return self._classify_http_error(e,
                                               duration=int((time.time() - t0) * 1000))
        except urllib.error.URLError:
            return self._err(ERR_SERVER_NOT_REACHABLE,
                              "서버에 접속할 수 없습니다.",
                              duration=int((time.time() - t0) * 1000))
        except TimeoutError:
            return self._err(ERR_REQUEST_TIMEOUT,
                              "요청 시간이 초과되었습니다.")
        except http.client.HTTPException:
            return self._err(ERR_PROVIDER_ERROR, "서버 응답 오류.")
        except Exception:
            return self._err(ERR_SERVER_NOT_REACHABLE,
                              "서버 통신 실패.")
        dur = int((time.time() - t0) * 1000)
        try:
            jd = json.loads(raw.decode("utf-8"))
        except Exception:
            return self._err(ERR_PROVIDER_ERROR, "응답 파싱 실패.",
                              duration=dur)
        return self._parse_success(jd, duration=dur)

    def _parse_success(self, jd: dict, *,
                        duration: int) -> ProxyChatResponse:
        if jd.get("ok") is False:
            return self._err(jd.get("error_code", ERR_PROVIDER_ERROR),
                              jd.get("user_message_kr", "응답 오류"),
                              duration=duration)
        text = jd.get("text", "")
        # redact 1차 (echo back 보호)
        from . import ai_chat_client as _aic
        text_red = _aic.redact_input(text or "")
        # health check 응답 (text 없고 ok=True 면 ok 만)
        if not text_red and jd.get("ok") is True:
            return ProxyChatResponse(
                ok=True, text_redacted="",
                model=jd.get("model", ""),
                duration_ms=duration,
                external_call_count=0,
            )
        return ProxyChatResponse(
            ok=True, text_redacted=text_red,
            model=jd.get("model", ""),
            usage_summary=jd.get("usage_summary", {}),
            external_call_count=jd.get("external_call_count", 1),
            duration_ms=duration,
        )

    def _classify_http_error(self, e: urllib.error.HTTPError,
                              *, duration: int) -> ProxyChatResponse:
        code = e.code
        try:
            body = e.read().decode("utf-8", errors="replace")[:300]
            jd = json.loads(body)
        except Exception:
            jd = {}
        detail = jd.get("detail") if isinstance(jd, dict) else None
        d_code = ""
        d_msg = ""
        if isinstance(detail, dict):
            d_code = detail.get("code", "")
            d_msg = detail.get("message", "")
        if code in (401, 403):
            return self._err(ERR_AUTH_FAILED, d_msg or "장치 인증 실패",
                              duration=duration)
        if code == 429:
            return self._err(ERR_RATE_LIMITED, "요청 한도 초과",
                              duration=duration)
        if code == 422:
            return self._err(ERR_RESPONSE_EMPTY, "요청 형식 오류",
                              duration=duration)
        if 500 <= code < 600:
            return self._err(ERR_PROVIDER_ERROR,
                              "서버 오류", duration=duration)
        return self._err(ERR_PROVIDER_ERROR, d_msg or f"HTTP {code}",
                          duration=duration)

    def _err(self, code: str, user_msg: str = "",
              *, duration: int = 0) -> ProxyChatResponse:
        return ProxyChatResponse(
            ok=False, error_code=code, user_message_kr=user_msg,
            external_call_count=0, duration_ms=duration,
        )


__all__ = (
    "ServerProxyChatClient", "ProxyChatResponse",
    "PROXY_PATH_CHAT", "PROXY_PATH_HEALTH",
    "ERR_API_KEY_NOT_SET", "ERR_AUTH_FAILED",
    "ERR_AGENT_ID_MISSING", "ERR_DEVICE_TOKEN_MISSING",
    "ERR_SERVER_NOT_REACHABLE", "ERR_PROVIDER_ERROR",
    "ERR_NETWORK_ERROR",
)
