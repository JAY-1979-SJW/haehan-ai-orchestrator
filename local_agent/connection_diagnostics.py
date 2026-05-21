"""로컬 에이전트 연결 진단 — 사용자가 데스크앱/CLI 에서 실패 원인을 즉시 파악.

기능:
  - 서버 URL 정규화 (http→ws / https→wss)
  - 저장된 agent_id 마스킹
  - 연결 상태/마지막 heartbeat/마지막 오류 표시
  - 사용자 조치 안내 텍스트

본 모듈은 device_token 원문을 절대 받지 않는다. 호출자가 token_store 에서
직접 로드해 websocket_client 에 전달하고, 본 모듈은 hash/maskedAgentId 만 처리.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))


# ── 연결 상태 ──────────────────────────────────────────────────────

STATE_NOT_REGISTERED = "NOT_REGISTERED"
STATE_CONNECTING = "CONNECTING"
STATE_AUTHENTICATING = "AUTHENTICATING"
STATE_CONNECTED = "CONNECTED"        # auth_ok 수신 직후
STATE_IDLE = "IDLE"                  # 작업 대기
STATE_BUSY = "BUSY"                  # 작업 처리 중
STATE_DISCONNECTED = "DISCONNECTED"
STATE_AUTH_FAILED = "AUTH_FAILED"    # 4401 발생
STATE_SERVER_UNREACHABLE = "SERVER_UNREACHABLE"
STATE_NETWORK_BLOCKED = "NETWORK_BLOCKED"

ALL_STATES = (
    STATE_NOT_REGISTERED, STATE_CONNECTING, STATE_AUTHENTICATING,
    STATE_CONNECTED, STATE_IDLE, STATE_BUSY, STATE_DISCONNECTED,
    STATE_AUTH_FAILED, STATE_SERVER_UNREACHABLE, STATE_NETWORK_BLOCKED,
)


# ── 오류 코드 → 사용자 메시지 ─────────────────────────────────────

_USER_GUIDANCE = {
    "REG_CODE_EXPIRED": (
        "등록코드가 만료되었습니다. 관리자에게 새 등록코드를 요청하세요."
    ),
    "REG_CODE_INVALID": (
        "등록코드가 유효하지 않습니다. 코드 입력을 다시 확인하세요."
    ),
    "REG_CODE_ALREADY_USED": (
        "이 등록코드는 이미 사용되었습니다. 새 등록코드를 요청하세요."
    ),
    "AUTH_FAILED_4401": (
        "장치 인증 실패(4401). device_token 이 변경되었거나 폐기됐을 수 있습니다. "
        "데스크앱 재등록을 진행하세요."
    ),
    "AUTH_TIMEOUT": (
        "서버 인증 응답 시간 초과. 서버 주소 또는 네트워크를 확인하세요."
    ),
    "SERVER_NOT_REACHABLE": (
        "서버에 접속할 수 없습니다. 서버 URL과 네트워크를 확인하세요."
    ),
    "NETWORK_BLOCKED_PROXY": (
        "WebSocket 이 차단된 것으로 보입니다. 프록시/방화벽 설정을 확인하세요. "
        "관리자에게 nginx proxy 설정(Upgrade/Connection) 확인을 요청하세요."
    ),
    "HEARTBEAT_LOST": (
        "heartbeat 응답이 없어 재연결합니다. 잠시 기다려 주세요."
    ),
    "TOKEN_NOT_STORED": (
        "device_token 이 안전 저장소에 없습니다. 데스크앱을 다시 등록하세요."
    ),
}


def explain_error(code: str) -> str:
    return _USER_GUIDANCE.get(code, "알 수 없는 오류입니다. 로그를 확인하세요.")


# ── 서버 URL 정규화 ──────────────────────────────────────────────

_SERVER_PATH = "/api/v1/local-agents/ws"


def normalize_ws_url(server_base_url: str) -> str:
    """http(s)://host[:port]/path → ws(s)://host[:port]/api/v1/local-agents/ws

    Raises:
        ValueError: server_base_url 이 비어있거나 잘못된 스킴
    """
    if not server_base_url:
        raise ValueError("server_base_url empty")
    url = server_base_url.strip().rstrip("/")
    if url.startswith("https://"):
        ws_url = "wss://" + url[len("https://"):]
    elif url.startswith("http://"):
        ws_url = "ws://" + url[len("http://"):]
    elif url.startswith(("ws://", "wss://")):
        ws_url = url
    else:
        raise ValueError(f"unsupported scheme in {url!r}")
    # path 가 이미 포함됐는지 확인
    if _SERVER_PATH not in ws_url:
        ws_url = ws_url + _SERVER_PATH
    return ws_url


# ── agent_id 마스킹 ──────────────────────────────────────────────


def mask_agent_id(agent_id: str) -> str:
    """la-abc123def456 → la-abc***f456"""
    if not agent_id:
        return ""
    if len(agent_id) <= 7:
        return agent_id[:2] + "***"
    return f"{agent_id[:6]}***{agent_id[-4:]}"


# ── 진단 데이터 ──────────────────────────────────────────────────


@dataclass
class ConnectionDiagnostics:
    server_url_redacted: str
    ws_url_redacted: str
    agent_id_masked: str
    state: str
    last_heartbeat_iso: str = ""
    last_error_code: str = ""
    last_error_message_user: str = ""
    reconnect_count: int = 0
    suggested_actions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _strip_secrets_from_url(url: str) -> str:
    """URL 쿼리/유저인포에 token/secret/auth/session 이 있으면 redacted."""
    if not url:
        return ""
    # userinfo (user:pass@host) 제거
    url = re.sub(r"://[^/@]*@", "://[REDACTED]@", url)
    # query 파라미터 제거 (보안 우선)
    url = re.sub(
        r"([?&])(token|auth|secret|session|sid|sess|key|password|pwd)=[^&]*",
        r"\1\2=[REDACTED]", url, flags=re.IGNORECASE,
    )
    return url


def build_diagnostics(
    *, server_base_url: str, agent_id: str, state: str,
    last_heartbeat_iso: str = "", last_error_code: str = "",
    reconnect_count: int = 0,
) -> ConnectionDiagnostics:
    try:
        ws_url = normalize_ws_url(server_base_url) if server_base_url else ""
    except ValueError:
        ws_url = "[INVALID_URL]"
    return ConnectionDiagnostics(
        server_url_redacted=_strip_secrets_from_url(server_base_url),
        ws_url_redacted=_strip_secrets_from_url(ws_url),
        agent_id_masked=mask_agent_id(agent_id),
        state=state,
        last_heartbeat_iso=last_heartbeat_iso,
        last_error_code=last_error_code,
        last_error_message_user=explain_error(last_error_code) if last_error_code else "",
        reconnect_count=reconnect_count,
        suggested_actions=_suggest_actions(state, last_error_code),
    )


def _suggest_actions(state: str, error_code: str) -> list[str]:
    out: list[str] = []
    if state == STATE_NOT_REGISTERED:
        out.append("관리자에게 등록코드를 요청하고 데스크앱 첫 화면에서 입력하세요.")
    if state == STATE_AUTH_FAILED or error_code == "AUTH_FAILED_4401":
        out.append("데스크앱을 재등록(새 registration_code 발급 → 입력)하세요.")
    if state == STATE_SERVER_UNREACHABLE or error_code == "SERVER_NOT_REACHABLE":
        out.append("서버 URL 과 인터넷/네트워크 연결을 확인하세요.")
    if state == STATE_NETWORK_BLOCKED or error_code == "NETWORK_BLOCKED_PROXY":
        out.append("회사/공유망의 프록시/방화벽이 WebSocket 을 차단하고 있을 수 있습니다.")
        out.append("관리자에게 nginx Upgrade/Connection 헤더 통과 설정을 요청하세요.")
    if not out and error_code:
        out.append(explain_error(error_code))
    return out


# ── render text (사람용 한 줄 진단) ───────────────────────────────


def render_one_line(d: ConnectionDiagnostics) -> str:
    hb = d.last_heartbeat_iso or "-"
    err = d.last_error_code or "-"
    return (
        f"[{d.state}] agent={d.agent_id_masked or '-'} "
        f"server={d.server_url_redacted or '-'} "
        f"last_hb={hb} last_err={err} reconnect={d.reconnect_count}"
    )


def render_user_block(d: ConnectionDiagnostics) -> str:
    lines = [
        "── 로컬 에이전트 연결 상태 ──",
        f"서버: {d.server_url_redacted or '-'}",
        f"WS  : {d.ws_url_redacted or '-'}",
        f"agent_id: {d.agent_id_masked or '(등록 안됨)'}",
        f"상태: {d.state}",
        f"마지막 heartbeat: {d.last_heartbeat_iso or '-'}",
        f"마지막 오류: {d.last_error_code or '-'}",
    ]
    if d.last_error_message_user:
        lines.append(f"안내: {d.last_error_message_user}")
    if d.suggested_actions:
        lines.append("조치:")
        for s in d.suggested_actions:
            lines.append(f"  - {s}")
    return "\n".join(lines)


# ── 토큰/시크릿 leak 자기검증 ──────────────────────────────────


_LEAK_KEYS = ("token", "secret", "device_token", "password",
              "cookie", "authorization", "session=", "x-api-key")


def find_token_leaks(text: str) -> list[str]:
    """다이아그노스틱 문자열 안에 토큰 누출 흔적 검출."""
    if not text:
        return []
    low = text.lower()
    return [k for k in _LEAK_KEYS if k in low]
