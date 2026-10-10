"""CDP 탭에서 '사이트가 정확히 열렸는지' 검증 — 주소·로드 상태만으로는 부족하다.

기준서: docs/specs/2026-10-02_app_agent_dispatch.md §9-8
`cdp_tabs.open_tab` 은 "탭 안 페이지가 떴다"까지만 보장한다. 이 모듈은 한 단계 더 본다:
  - 도착 주소가 기대한 사이트인가(다른 사이트로 이동·리다이렉트 포함)
  - 내용이 실제로 그려졌는가(제목·본문 길이·화면 스크린샷 통계 — 빈 화면 감지)
  - 차단·오류·캡차 화면이 아닌가(제목·본문 앞부분의 의심 문구)
  - 로그인을 요구하는 화면인가(사이트는 열린 것이며 실패가 아니다)

개인정보: **본문 내용은 반환·기록하지 않는다**(길이와 의심 문구 일치 여부만). 스크린샷은 파일로 저장하지 않고 메모리에서 통계만 낸다.
소켓은 항상 타임아웃을 명시한다(websocket-client 는 지정하지 않으면 무한 대기할 수 있다).
"""

from __future__ import annotations

import base64
import io
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

OK = "ok"  # 기대한 사이트가 정상적으로 열림
LOGIN = "login_required"  # 사이트는 열렸고 로그인을 요구하는 화면
BLOCKED = "blocked"  # 차단·접근 거부·캡차로 보임
ERROR = "error"  # 오류 페이지(도메인 없음·연결 실패 등)
BLANK = "blank"  # 열렸지만 내용이 비어 있음
WRONG_SITE = "wrong_site"  # 기대한 사이트가 아닌 곳에 도착

MIN_TEXT_CHARS = 30
BLANK_PNG_BYTES = 9_000  # 이 크기 미만이면서 색 다양성이 낮으면 빈 화면(1280x800 흰 화면 PNG 는 약 4~6KB)
_BLOCK_HINTS = (
    "access denied",
    "forbidden",
    "403 error",
    "request blocked",
    "are you a robot",
    "unusual traffic",
    "captcha",
    "접근이 거부",
    "접근 권한이 없",
    "접속이 원활하지",
    "비정상적인 접근",
    "보안문자",
    "자동입력 방지",
    "차단되었",
    "이용이 제한",
)
_ERROR_HINTS = (
    "this site can’t be reached",
    "this site can't be reached",
    "err_name_not_resolved",
    "err_connection",
    "사이트에 연결할 수 없",
    "페이지를 찾을 수 없",
    "404 not found",
)
_LOGIN_PATH_HINTS = ("login", "signin", "sign-in", "logon", "nidlogin", "auth", "accounts", "member/assemble")
_TWO_LEVEL_SECOND = {"co", "or", "go", "ne", "re", "pe", "ac"}


@dataclass(frozen=True)
class PageInfo:
    """탭 안에서 읽은 메타데이터(본문 내용은 담지 않는다)."""

    href: str
    ready: str
    title: str
    text_len: int
    head_lower: str  # 제목+본문 앞부분(소문자) — 판정에만 쓰고 결과에는 싣지 않는다
    has_password: bool
    shot_bytes: int
    shot_colors: int  # 스크린샷의 서로 다른 색 수(축소본 기준). -1 이면 계산 불가


@dataclass(frozen=True)
class Verdict:
    status: str
    reason: str
    href: str = ""
    title: str = ""
    checks: dict[str, Any] = field(default_factory=dict)

    @property
    def opened(self) -> bool:
        """사이트가 열렸는가(정상 + 로그인 요구 화면)."""
        return self.status in (OK, LOGIN)


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def _registrable(host: str) -> str:
    """대략적인 등록 도메인(마지막 두 라벨, co.kr 류는 세 라벨)."""
    parts = host.split(".")
    if len(parts) >= 3 and parts[-2] in _TWO_LEVEL_SECOND and len(parts[-1]) == 2:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def host_matches(host: str, expected: tuple[str, ...]) -> bool:
    host = host.lower()
    return any(host == e or host.endswith("." + e) for e in (x.lower().lstrip(".") for x in expected))


def classify(
    info: PageInfo, url: str, *, expect_hosts: tuple[str, ...] | None = None, expect_text: tuple[str, ...] = ()
) -> Verdict:
    """순수 판정. 우선순위: 오류 → 차단 → 엉뚱한 사이트 → 로그인 → 빈 화면 → 기대 문구 → 정상."""
    expected = expect_hosts or (_registrable(_host(url)),)
    host = _host(info.href)
    checks: dict[str, Any] = {
        "ready": info.ready,
        "host": host,
        "text_len": info.text_len,
        "title_len": len(info.title),
        "screenshot_bytes": info.shot_bytes,
        "screenshot_colors": info.shot_colors,
        "password_field": info.has_password,
    }
    if info.href.startswith("chrome-error://") or any(h in info.head_lower for h in _ERROR_HINTS):
        return Verdict(ERROR, "오류 페이지(연결 실패·도메인 없음 등)", info.href, info.title, checks)
    hit = [h for h in _BLOCK_HINTS if h in info.head_lower]
    if hit:
        checks["block_hints"] = hit
        return Verdict(BLOCKED, f"차단·보안확인으로 보이는 문구 {len(hit)}건 발견", info.href, info.title, checks)
    login_like = info.has_password or any(p in info.href.lower() for p in _LOGIN_PATH_HINTS)
    if not host_matches(host, expected):
        if login_like:
            return Verdict(LOGIN, f"로그인 화면으로 이동({host})", info.href, info.title, checks)
        reason = f"기대한 사이트({', '.join(expected)})가 아닌 {host or '(주소 없음)'} 에 도착"
        return Verdict(WRONG_SITE, reason, info.href, info.title, checks)
    if login_like:
        return Verdict(LOGIN, "사이트는 열렸고 로그인을 요구하는 화면", info.href, info.title, checks)
    low_visual = info.shot_bytes < BLANK_PNG_BYTES and 0 <= info.shot_colors < 8
    if info.text_len < MIN_TEXT_CHARS and (low_visual or info.shot_colors == -1):
        return Verdict(BLANK, "열렸지만 내용이 거의 없음(빈 화면)", info.href, info.title, checks)
    if expect_text:
        missing = [t for t in expect_text if t.lower() not in info.head_lower]
        checks["expect_text_missing"] = len(missing)
        if missing and info.text_len < 2000:
            return Verdict(WRONG_SITE, "기대한 문구가 보이지 않음", info.href, info.title, checks)
    if info.ready not in ("interactive", "complete"):
        return Verdict(ERROR, f"로드가 끝나지 않음({info.ready})", info.href, info.title, checks)
    return Verdict(OK, "기대한 사이트가 정상적으로 열림", info.href, info.title, checks)


# ── 탭에서 읽기 ──────────────────────────────────────────────────────────

_PAGE_JS = (
    "JSON.stringify({href: location.href, ready: document.readyState, title: document.title || '',"
    " text_len: (document.body ? document.body.innerText.length : 0),"
    " head: ((document.title||'') + ' ' + (document.body ? document.body.innerText.slice(0, 600) : '')).toLowerCase(),"
    " pw: !!document.querySelector('input[type=password]')})"
)


def _color_count(png: bytes) -> int:
    """스크린샷(PNG)의 서로 다른 색 수(64x64 축소본). Pillow 가 없거나 해석에 실패하면 -1."""
    try:
        from PIL import Image
    except ImportError:
        return -1
    try:
        img = Image.open(io.BytesIO(png)).convert("RGB").resize((64, 64))
        return len(set(img.getdata()))
    except Exception:  # noqa: BLE001 - 이미지 해석 실패는 '계산 불가' 로 둔다
        return -1


def read_page(ws_url: str, timeout: float = 8.0) -> PageInfo:
    """탭 디버그 소켓으로 메타데이터와 스크린샷 통계를 읽는다(본문 내용은 반환하지 않음)."""
    import websocket  # 의존성: websocket-client(requirements.txt)

    ws = websocket.create_connection(ws_url, timeout=timeout, suppress_origin=True)
    try:

        def call(msg_id: int, method: str, params: dict[str, Any]) -> dict[str, Any]:
            ws.send(json.dumps({"id": msg_id, "method": method, "params": params}))
            while True:
                msg = json.loads(ws.recv())
                if msg.get("id") == msg_id:
                    return msg.get("result", {})

        value = (
            call(1, "Runtime.evaluate", {"expression": _PAGE_JS, "returnByValue": True}).get("result", {}).get("value")
        )
        data = json.loads(value) if value else {}
        shot = call(2, "Page.captureScreenshot", {"format": "png", "fromSurface": True}).get("data", "")
        png = base64.b64decode(shot) if shot else b""
    finally:
        ws.close()
    return PageInfo(
        href=str(data.get("href", "")),
        ready=str(data.get("ready", "")),
        title=str(data.get("title", "")),
        text_len=int(data.get("text_len", 0)),
        head_lower=str(data.get("head", "")),
        has_password=bool(data.get("pw")),
        shot_bytes=len(png),
        shot_colors=_color_count(png) if png else -1,
    )


def verify_tab(
    ws_url: str,
    url: str,
    *,
    expect_hosts: tuple[str, ...] | None = None,
    expect_text: tuple[str, ...] = (),
    reader: Callable[[str], PageInfo] = read_page,
) -> Verdict:
    """열린 탭이 기대한 사이트로 정확히 열렸는지 판정한다. 읽기에 실패하면 성공으로 보지 않는다."""
    try:
        info = reader(ws_url)
    except Exception as e:  # noqa: BLE001 - 읽기 실패(소켓 종료·타임아웃 등)는 '검증 불가' 오류로 돌려준다
        return Verdict(ERROR, f"탭 상태를 읽지 못함({type(e).__name__})")
    return classify(info, url, expect_hosts=expect_hosts, expect_text=expect_text)
