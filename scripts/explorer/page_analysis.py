"""페이지 스냅샷 분석 — 요소 역할, 셀렉터 안정성, 페이지 상태, 위험 동작.

`scripts.explorer.page_snapshot.snapshot()` 이 만든 dict 를 읽어 분석 결과를 돌려주는 **순수 함수** 모듈이다.
브라우저·네트워크·파일 쓰기를 하지 않는다(CLI 의 입력 파일 읽기만 예외). 입력을 수정하지 않는다.

기준서: docs/specs/2026-09-30_page_analysis_layer.md (v3, A단계)

주의
- 분석 결과에는 화면 문구 전체나 입력값을 담지 않는다. 라벨(짧은 버튼/입력 이름)과 판정 근거의 규칙 이름만 담는다.
- 위험 분류는 표시만 한다. 자동 클릭 판단에 쓰지 않는다(승인 게이트는 기존 것을 그대로 사용).
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

# 스크립트로 직접 실행해도(python scripts/explorer/page_analysis.py) 프로젝트 모듈을 import 할 수 있게 한다.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.agent_runtime.runtime.universal.generic_selector_discovery import _RISK_BUTTON_KEYWORDS  # noqa: E402

logger = logging.getLogger(__name__)

# 위험 키워드 표는 기존 것을 그대로 재사용한다(projects/CLAUDE.md §1: 중복 금지).
RISK_KEYWORD_SOURCE = _RISK_BUTTON_KEYWORDS

_MAX_LABEL = 40  # 결과에 담는 라벨 길이 상한(문구 전체를 담지 않기 위해)
_ROLE_NAME_MAX = 30  # 역할 기반 로케이터에 쓰는 이름의 최대 길이
_STABLE_ROLE_SCORE = 92  # 이름이 유일한 역할 기반 로케이터(Playwright 권장 방식)
_DUPLICATE_ROLE_SCORE = 55

# ── 셀렉터 안정성 ─────────────────────────────────────────────────────────

_HASH_SUFFIX = re.compile(r"__[A-Za-z0-9]{5,}\b")  # publish_btn__m9KHH
_MIXED_RANDOM = re.compile(r"^(?=.*\d)(?=.*[a-z])(?=.*[A-Z])[A-Za-z0-9]{8,}$")  # aB3dE9x2 류
_HEX_LIKE = re.compile(r"^(?=.*\d)(?=.*[a-f])[0-9a-f]{8,}$")  # 8f3a9c2d7e1b 류(16진수 해시, 숫자 필수)
_LONG_DIGITS = re.compile(r"\d{6,}")
_FRAMEWORK_ATTR = re.compile(r"\[(?:ng-|data-v-|_ngcontent|v-)[^\]]*\]")
_POSITIONAL = re.compile(r":nth-(?:child|of-type)\(|:first-child|:last-child")
_TEXT_BASED = re.compile(r":has-text\(|:text\(|text=")
_ARIA_ATTR = re.compile(r"\[(?:aria-label|role)=")
_DATA_ATTR = re.compile(r"\[data-(?!v-)[\w-]+=")
_NAME_ATTR = re.compile(r"\[name=")
_HREF_ATTR = re.compile(r"\[href[\^=]")
_ID_SEL = re.compile(r"#([A-Za-z_][\w-]*)")
_CLASS_SEL = re.compile(r"\.([A-Za-z_][\w-]*)")

_SCORE_HASHED = 15
_SCORE_POSITIONAL = 20
_SCORE_FRAMEWORK = 35
_SCORE_UNKNOWN_CLASS = 40
_SCORE_TEXT = 50
_SCORE_HREF = 60
_SCORE_DATA = 70
_SCORE_ARIA = 75
_SCORE_NAME = 80
_SCORE_ID = 90


def looks_hashed(token: str) -> bool:
    """빌드마다 바뀌는 해시/난수 토큰으로 보이는가."""
    return bool(
        _HASH_SUFFIX.search(token) or _MIXED_RANDOM.match(token) or _HEX_LIKE.match(token) or _LONG_DIGITS.search(token)
    )


def _score_ids(selector: str) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for token in _ID_SEL.findall(selector):
        hashed = looks_hashed(token)
        out.append((_SCORE_HASHED, "해시가 붙은 id") if hashed else (_SCORE_ID, "안정적인 id"))
    return out


def _score_classes(selector: str) -> list[tuple[int, str]]:
    # 속성 값 안의 점(.)이 클래스로 잡히지 않도록 [ ... ] 안쪽은 제거하고 본다
    bare = re.sub(r"\[[^\]]*\]", "", selector)
    bare = re.sub(r"\(.*?\)", "", bare)
    out: list[tuple[int, str]] = []
    for token in _CLASS_SEL.findall(bare):
        hashed = looks_hashed(token)
        out.append((_SCORE_HASHED, "빌드 해시 클래스") if hashed else (_SCORE_UNKNOWN_CLASS, "클래스 기반(분류 불명)"))
    return out


def _score_attributes(selector: str) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    checks = (
        (_FRAMEWORK_ATTR, _SCORE_FRAMEWORK, "프레임워크 내부 속성"),
        (_POSITIONAL, _SCORE_POSITIONAL, "위치 기반"),
        (_TEXT_BASED, _SCORE_TEXT, "문구 의존"),
        (_HREF_ATTR, _SCORE_HREF, "링크 주소(href)"),
        (_ARIA_ATTR, _SCORE_ARIA, "접근성 속성"),
        (_DATA_ATTR, _SCORE_DATA, "data 속성"),
        (_NAME_ATTR, _SCORE_NAME, "name 속성"),
    )
    for pattern, score, reason in checks:
        if pattern.search(selector):
            out.append((score, reason))
    return out


def score_selector(selector: str) -> tuple[int, str]:
    """CSS 셀렉터의 안정성 점수(0~100, 높을수록 안정)와 근거. 복합 셀렉터는 가장 취약한 부분을 따른다."""
    parts = _score_ids(selector) + _score_classes(selector) + _score_attributes(selector)
    if not parts:
        return _SCORE_UNKNOWN_CLASS, "태그/구조 기반(분류 불명)"
    return min(parts, key=lambda p: p[0])


# ── 역할 분류 ─────────────────────────────────────────────────────────────

# 먼저 나온 역할이 우선한다(예: "임시저장" 이 "저장" 보다, "발행" 이 "등록" 류보다 먼저).
_BUTTON_ROLES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("login", ("로그인", "sign in", "signin", "log in", "login")),
    ("logout", ("로그아웃", "sign out", "signout", "log out", "logout")),
    ("account", ("내정보", "내 정보", "내 블로그", "마이페이지", "my page", "mypage", "my account")),
    ("publish", ("발행", "게시", "공개", "publish")),
    ("save", ("임시저장", "저장", "save", "draft")),
    ("write", ("글쓰기", "작성", "새 글", "write", "compose")),
    ("search", ("검색", "search")),
    ("next", ("다음", "next", "계속")),
    ("close", ("닫기", "close", "x 닫기")),
    ("confirm", ("확인", "ok", "동의")),
    ("cancel", ("취소", "cancel")),
)
_INPUT_ROLES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("search", ("검색", "search")),
    ("username", ("아이디", "username", "user id", "userid", "이메일", "email")),
    ("title", ("제목", "title")),
    ("body", ("내용", "본문", "content", "body")),
)


def _match_role(table: tuple[tuple[str, tuple[str, ...]], ...], text: str) -> str:
    lowered = text.lower()
    for role, words in table:
        if any(w in lowered for w in words):
            return role
    return "other"


def classify_role(kind: str, text: str, *, input_type: str = "") -> str:
    """요소의 역할. kind 는 button/link/input/select. 모호하면 other."""
    if kind == "input" and input_type.lower() == "password":
        return "password"
    if not text:
        return "other"
    table = _INPUT_ROLES if kind in ("input", "select") else _BUTTON_ROLES
    return _match_role(table, text)


# ── 위험 동작 ─────────────────────────────────────────────────────────────

# 기존 표의 카테고리 → 이 모듈의 위험 분류
_RISK_CATEGORY_MAP = {
    "payment": "payment",
    "transfer": "payment",
    "delete": "destructive",
    "sign": "legal",
    "bid": "legal",
    "legal_submit": "legal",
}
# 기존 표에 없는 범주만 덧붙인다(기존 모듈은 수정하지 않는다)
_EXTRA_RISK: tuple[tuple[str, str], ...] = (
    ("구매", "payment"),
    ("주문하기", "payment"),
    ("purchase", "payment"),
    ("탈퇴", "destructive"),
    ("해지", "destructive"),
    ("초기화", "destructive"),
    ("delete", "destructive"),
    ("remove", "destructive"),
    ("발행", "publish"),
    ("게시", "publish"),
    ("공개", "publish"),
    ("publish", "publish"),
    ("전송", "send"),
    ("발송", "send"),
    ("보내기", "send"),
    ("send", "send"),
    ("submit", "send"),
)
# 우선순위: 금전 > 법적 효력 > 삭제 > 발행 > 전송
_RISK_ORDER = ("payment", "legal", "destructive", "publish", "send")


def classify_risk(text: str) -> str:
    """버튼/링크 문구의 위험 분류. payment/legal/destructive/publish/send 또는 safe."""
    if not text:
        return "safe"
    lowered = text.lower()
    found: set[str] = set()
    for keyword, category in RISK_KEYWORD_SOURCE:
        if keyword.lower() in lowered:
            found.add(_RISK_CATEGORY_MAP.get(category, "legal"))
    for keyword, category in _EXTRA_RISK:
        if keyword in lowered:
            found.add(category)
    for level in _RISK_ORDER:
        if level in found:
            return level
    return "safe"


# ── 페이지 상태 ───────────────────────────────────────────────────────────

_LOGIN_URL_HINTS = (
    "nidlogin",
    "/login",
    "/signin",
    "accounts.google.com",
    "accounts.commerce.naver.com",
)
_CAPTCHA_WORDS = ("보안문자", "자동입력 방지", "자동 입력 방지", "captcha", "2단계 인증", "2차 인증", "일회용", "otp")
_DENIED_WORDS = ("권한이 없", "접근할 수 없", "접근 권한", "관리자만", "forbidden", "access denied", "403")


def _frames(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    frames = snapshot.get("frames") if isinstance(snapshot, dict) else None
    if not isinstance(frames, list):
        return []
    return [f for f in frames if isinstance(f, dict) and not f.get("error")]


def _page_texts(snapshot: dict[str, Any]) -> list[str]:
    """상태 판정에만 쓰는 문구 모음(제목·머리글·버튼·링크). 결과로는 내보내지 않는다."""
    texts = [str(snapshot.get("title", ""))]
    for frame in _frames(snapshot):
        texts += [str(h.get("text", "")) for h in frame.get("headings") or []]
        texts += [str(b.get("text", "")) for b in frame.get("buttons") or []]
        texts += [str(item.get("text", "")) for item in (frame.get("links") or [])[:50]]
    return [t.lower() for t in texts if t]


def _has_password_input(snapshot: dict[str, Any]) -> bool:
    for frame in _frames(snapshot):
        for field in frame.get("inputs") or []:
            if str(field.get("type", "")).lower() == "password" and field.get("visible", True):
                return True
    return False


_CAPTCHA_FIELD_HINT = ("captcha", "캡차", "보안문자")


def _captcha_texts(snapshot: dict[str, Any]) -> list[str]:
    """캡차 판정에 쓰는 문구 — 화면을 막는 곳(제목·머리글·보이는 다이얼로그)만. 링크·일반 버튼은 제외한다.
    (로그인 화면의 '일회용 로그인' 같은 대체 수단 링크가 캡차로 오판되던 문제, 2026-09-30 실제 화면 검증)"""
    texts = [str(snapshot.get("title", ""))]
    for frame in _frames(snapshot):
        texts += [str(h.get("text", "")) for h in frame.get("headings") or []]
        texts += [str(d.get("text", "")) for d in frame.get("dialogs") or [] if d.get("visible", True)]
    return [t.lower() for t in texts if t]


def _has_captcha_field(snapshot: dict[str, Any]) -> bool:
    """캡차 입력칸(이름·id 에 captcha)이 화면에 보이면 캡차 화면이다."""
    for frame in _frames(snapshot):
        for field in frame.get("inputs") or []:
            hay = f"{field.get('name', '')} {field.get('id', '')} {field.get('placeholder', '')}".lower()
            if field.get("visible", True) and any(h in hay for h in _CAPTCHA_FIELD_HINT):
                return True
    return False


def _has_visible_dialog(snapshot: dict[str, Any]) -> bool:
    return any(d.get("visible", True) for frame in _frames(snapshot) for d in frame.get("dialogs") or [])


def _count_elements(snapshot: dict[str, Any]) -> int:
    return sum(len(f.get(k) or []) for f in _frames(snapshot) for k in ("buttons", "inputs", "links"))


def _match_words(texts: list[str], words: tuple[str, ...]) -> bool:
    return any(w in t for t in texts for w in words)


def _login_evidence(snapshot: dict[str, Any]) -> list[str]:
    url = str(snapshot.get("url", "")).lower()
    hits = (("login_url", any(h in url for h in _LOGIN_URL_HINTS)), ("password_input", _has_password_input(snapshot)))
    return [name for name, hit in hits if hit]


def _blocking_state(snapshot: dict[str, Any], texts: list[str]) -> dict[str, Any] | None:
    """캡차 > 권한 없음 > 로그인 요구 > 팝업 순으로 화면을 막는 상태를 찾는다. 없으면 None."""
    if _has_captcha_field(snapshot):
        return {"state": "captcha", "evidence": ["captcha_field"]}
    if _match_words(_captcha_texts(snapshot), _CAPTCHA_WORDS):
        return {"state": "captcha", "evidence": ["captcha_keyword"]}
    if _match_words(texts, _DENIED_WORDS):
        return {"state": "permission_denied", "evidence": ["denied_keyword"]}
    evidence = _login_evidence(snapshot)
    if evidence:
        return {"state": "login_required", "evidence": evidence}
    if _has_visible_dialog(snapshot):
        return {"state": "popup_blocking", "evidence": ["visible_dialog"]}
    return None


def classify_page_state(snapshot: dict[str, Any]) -> dict[str, Any]:
    """페이지 상태와 판정 근거(규칙 이름만, 화면 문구 원문은 담지 않음)."""
    if not isinstance(snapshot, dict):
        return {"state": "unknown", "evidence": ["no_elements"]}
    blocked = _blocking_state(snapshot, _page_texts(snapshot))
    if blocked:
        return blocked
    if _count_elements(snapshot) > 0:
        return {"state": "ok", "evidence": ["has_elements"]}
    return {"state": "unknown", "evidence": ["no_elements"]}


# ── 팝업 ──────────────────────────────────────────────────────────────────

_POPUP_TEXT_MAX = 200
# 종류 판정 우선순위: 먼저 나온 것이 우선(문구 키워드). 못 정하면 버튼 구성으로, 그것도 아니면 notice.
_POPUP_KINDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("error", ("오류", "에러", "실패", "error", "failed", "장애")),
    ("warning", ("경고", "주의", "불가", "제한", "차단", "warning", "확인해 주세요", "올바르지")),
    ("consent", ("쿠키", "cookie", "약관", "개인정보", "동의", "consent", "privacy")),
    ("ad", ("이벤트", "할인", "프로모션", "쿠폰", "오늘 하루", "다시 보지", "광고", "sale", "promotion")),
)
_CLOSE_ROLES = ("close", "cancel")  # 안전하게 닫는 버튼: 위험하지 않은 close/cancel 우선, 다음이 confirm


def _popup_kind(text: str, roles: list[str]) -> str:
    lowered = text.lower()
    for kind, words in _POPUP_KINDS:
        if any(w in lowered for w in words):
            return kind
    if "confirm" in roles and "cancel" in roles:
        return "confirm"
    return "notice"


def _popup_buttons(raw: list[dict[str, Any]]) -> list[dict[str, str]]:
    out = []
    for b in raw or []:
        label = _label(str(b.get("text", "")), str(b.get("aria", "")))
        if label:
            out.append({"label": label, "role": classify_role("button", label), "risk": classify_risk(label)})
    return out


def _safe_close(buttons: list[dict[str, str]]) -> dict[str, str] | None:
    """위험하지 않은 버튼 중 close > cancel > confirm 순으로 하나를 고른다. 없으면 None."""
    safe = [b for b in buttons if b["risk"] == "safe"]
    for role in (*_CLOSE_ROLES, "confirm"):
        for button in safe:
            if button["role"] == role:
                return button
    return None


def _analyze_popup(order: int, dlg: dict[str, Any]) -> dict[str, Any]:
    text = " ".join(str(dlg.get("text", "")).split())[:_POPUP_TEXT_MAX]
    buttons = _popup_buttons(dlg.get("buttons") or [])
    roles = [b["role"] for b in buttons]
    close = _safe_close(buttons)
    dangerous = any(b["risk"] != "safe" for b in buttons)
    return {
        "order": order,
        "kind": _popup_kind(text, roles),
        "text": text,
        "role": str(dlg.get("role", "")),
        "path": str(dlg.get("path", "")),
        "z": int(dlg.get("z", 0) or 0),
        "cover": float(dlg.get("cover", 0) or 0),
        "buttons": buttons,
        "safe_close": close,
        # 버튼이 있는데 안전하게 누를 것이 없으면 사람이 봐야 한다. 버튼이 아예 없으면 Esc 로 닫아 볼 수 있다.
        "needs_review": bool(buttons) and close is None,
        "escape_ok": not buttons,
        "has_dangerous_button": dangerous,
    }


def analyze_popups(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """스냅샷의 보이는 팝업을 맨 위(z-index 큰 것)부터 분석한다. 숨김 팝업은 제외."""
    dialogs = [
        d
        for frame in _frames(snapshot if isinstance(snapshot, dict) else {})
        for d in frame.get("dialogs") or []
        if isinstance(d, dict) and d.get("visible", True)
    ]
    dialogs.sort(key=lambda d: (-int(d.get("z", 0) or 0), -float(d.get("cover", 0) or 0)))
    return [_analyze_popup(i, d) for i, d in enumerate(dialogs)]


# ── 요소·후보 셀렉터 ──────────────────────────────────────────────────────


def _q(value: str) -> str:
    """Playwright 로케이터 문자열용 따옴표 이스케이프."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _label(*candidates: str) -> str:
    for text in candidates:
        cleaned = " ".join((text or "").split())
        if cleaned:
            return cleaned[:_MAX_LABEL]
    return ""


_MAX_HREF = 100  # 이보다 긴 주소는 세션·추적 값이 섞였을 가능성이 커서 후보로 쓰지 않는다


def _href_selector(href: str) -> str | None:
    """링크 주소로 만드는 CSS 후보. 쓸모없거나 불안정한 주소면 None."""
    if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")) or len(href) > _MAX_HREF:
        return None
    path = href.split("?", 1)[0].split("#", 1)[0]
    if path in ("", "/") or any(looks_hashed(seg) for seg in path.split("/") if seg):
        return None
    return f'a[href^="{path}"]' if "?" in href else f'a[href="{href}"]'


def _attr_selectors(tag: str, kind: str, item: dict[str, Any]) -> list[str]:
    raw: list[str] = []
    if item.get("id"):
        raw.append(f"#{item['id']}")
    for attr, key in (("name", "name"), ("aria-label", "aria"), ("placeholder", "placeholder")):
        if item.get(key):
            raw.append(f'{tag}[{attr}="{item[key]}"]')
    if item.get("text") and kind == "button":
        raw.append(f'button:has-text("{_label(str(item["text"]))}")')
    if kind == "link":
        href_css = _href_selector(str(item.get("href", "")))
        if href_css:
            raw.append(href_css)
    return raw


def _css_candidates(kind: str, item: dict[str, Any]) -> list[dict[str, Any]]:
    tag = {"button": "button", "link": "a"}.get(kind, str(item.get("tag", "input")).lower() or "input")
    raw = _attr_selectors(tag, kind, item) + [f"{tag}.{cls}" for cls in str(item.get("cls", "")).split()[:3]]
    out = []
    for css in raw:
        score, reason = score_selector(css)
        out.append({"kind": "css", "css": css, "stability": score, "reason": reason})
    return out


def _role_candidate(kind: str, item: dict[str, Any], name: str, duplicate: bool) -> dict[str, Any] | None:
    if not name or len(name) > _ROLE_NAME_MAX:
        return None
    if kind == "button":
        locator = f'get_by_role("button", name="{_q(name)}")'
    elif kind == "link":
        locator = f'get_by_role("link", name="{_q(name)}")'
    elif item.get("aria") or item.get("placeholder"):
        locator = f'get_by_label("{_q(name)}")' if item.get("aria") else f'get_by_placeholder("{_q(name)}")'
    else:
        return None
    if duplicate:
        return {
            "kind": "role",
            "locator": locator,
            "stability": _DUPLICATE_ROLE_SCORE,
            "reason": "역할+이름(화면에 중복된 이름 — 다른 후보와 함께 사용)",
        }
    return {"kind": "role", "locator": locator, "stability": _STABLE_ROLE_SCORE, "reason": "역할+이름(접근성 기반)"}


def _element_name(kind: str, item: dict[str, Any]) -> str:
    if kind in ("button", "link"):
        return _label(str(item.get("text", "")), str(item.get("aria", "")))
    return _label(
        str(item.get("aria", "")), str(item.get("placeholder", "")), str(item.get("name", "")), str(item.get("id", ""))
    )


def _iter_items(frame: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    pairs: list[tuple[str, dict[str, Any]]] = []
    for kind, key in (("button", "buttons"), ("input", "inputs"), ("link", "links")):
        for item in frame.get(key) or []:
            if isinstance(item, dict):
                kind_name = "select" if str(item.get("tag", "")).upper() == "SELECT" else kind
                pairs.append((kind_name, item))
    return pairs


def _build_element(frame_idx: int, kind: str, item: dict[str, Any], counts: Counter[tuple[str, str]]) -> dict[str, Any]:
    name = _element_name(kind, item)
    duplicate = counts[(kind if kind != "select" else "input", name)] > 1
    cands = _css_candidates(kind, item)
    role_cand = _role_candidate(kind, item, name, duplicate)
    if role_cand:
        cands.append(role_cand)
    cands.sort(key=lambda c: c["stability"], reverse=True)
    risk_text = _label(str(item.get("text", "")), str(item.get("aria", "")), str(item.get("id", "")))
    return {
        "frame": frame_idx,
        "kind": kind,
        "role": classify_role(kind, name, input_type=str(item.get("type", ""))),
        "label": name,
        "visible": bool(item.get("visible", True)),
        "risk": classify_risk(risk_text) if kind in ("button", "link") else "safe",
        "selectors": cands,
    }


def _name_counts(frames: list[dict[str, Any]]) -> Counter[tuple[str, str]]:
    """(종류, 이름)별 등장 횟수 — 중복 이름 판정용."""
    counts: Counter[tuple[str, str]] = Counter()
    for frame in frames:
        for kind, item in _iter_items(frame):
            counts[("input" if kind == "select" else kind, _element_name(kind, item))] += 1
    return counts


def _summarize(elements: list[dict[str, Any]]) -> dict[str, int]:
    fragile = sum(1 for e in elements if e["selectors"] and e["selectors"][0]["stability"] <= _SCORE_TEXT)
    return {
        "elements": len(elements),
        "fragile_only": fragile,
        "risky": sum(1 for e in elements if e["risk"] != "safe" and e["visible"]),
        "risky_hidden": sum(1 for e in elements if e["risk"] != "safe" and not e["visible"]),
    }


def analyze_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """스냅샷 dict → 분석 dict. 입력은 수정하지 않는다."""
    if not isinstance(snapshot, dict):
        snapshot = {}
    frames = _frames(snapshot)
    popups = analyze_popups(snapshot)
    counts = _name_counts(frames)
    elements = [
        _build_element(int(frame.get("idx", 0)), kind, item, counts)
        for frame in frames
        for kind, item in _iter_items(frame)
    ]
    return {
        "url": snapshot.get("url", ""),
        "title": _label(str(snapshot.get("title", ""))),
        "page_state": classify_page_state(snapshot),
        "elements": elements,
        "popups": popups,
        "summary": {**_summarize(elements), "popups": len(popups)},
    }


# ── 로그인 상태 근거(눈에 보이는 요소만) ──────────────────────────────────

_SIGNAL_LABEL_MAX = 20  # 이보다 긴 라벨은 문장·캘린더 링크 등이라 로그인 버튼으로 세지 않는다
# "로그인"이라는 글자만 들어 있고 로그인 동작이 아닌 링크 — 예: 로그인된 화면의 "로그인 보호 설정"(2026-09-30 실제 화면에서 확인)
_NOT_A_LOGIN_ACTION = ("보호", "설정", "도움", "유지", "찾기", "안내", "방법", "실패", "오류", "약관", "기록", "내역")


def _signal_group(el: dict[str, Any]) -> str:
    """로그인 상태 근거로 셀 요소의 묶음: "login"(로그인 버튼) / "in"(로그아웃·계정) / ""(세지 않음)."""
    label = str(el.get("label", ""))
    if el.get("kind") not in ("button", "link") or len(label) > _SIGNAL_LABEL_MAX:
        return ""
    role = el.get("role")
    if role == "login":
        return "" if any(token in label for token in _NOT_A_LOGIN_ACTION) else "login"
    return "in" if role in ("logout", "account") else ""


def element_login_signals(analysis: dict[str, Any]) -> dict[str, Any]:
    """분석 결과에서 로그인 상태 근거를 센다. 숨은 요소(visible=False)는 세지 않는다.

    반환: {login_visible, in_visible, login_hidden, in_hidden, labels:{login,in}}
    상태(in/out)를 확정하는 건 호출자 몫 — 쿠키 등 독립 신호와 합쳐 판단해야 하기 때문.
    """
    count = {"login": [0, 0], "in": [0, 0]}  # [보임, 숨김]
    labels: dict[str, list[str]] = {"login": [], "in": []}
    for el in analysis.get("elements", []):
        group = _signal_group(el)
        if not group:
            continue
        idx = 0 if el.get("visible") else 1
        count[group][idx] += 1
        if idx == 0 and len(labels[group]) < 3:
            labels[group].append(str(el.get("label", "")))
    return {
        "login_visible": count["login"][0],
        "in_visible": count["in"][0],
        "login_hidden": count["login"][1],
        "in_hidden": count["in"][1],
        "labels": labels,
    }


# ── CLI ───────────────────────────────────────────────────────────────────


def _format_summary(result: dict[str, Any]) -> str:
    state = result["page_state"]
    lines = [
        f"url: {result['url']}",
        f"page_state: {state['state']} ({', '.join(state['evidence'])})",
        f"elements: {result['summary']['elements']}  fragile_only: {result['summary']['fragile_only']}  risky: {result['summary']['risky']}  risky_hidden: {result['summary']['risky_hidden']}",
    ]
    for el in result["elements"]:
        best = el["selectors"][0] if el["selectors"] else None
        pick = (best.get("locator") or best.get("css")) if best else "-"
        risk = f" risk={el['risk']}" if el["risk"] != "safe" else ""
        lines.append(
            f"  [{el['kind']}] {el['role']:<9} {el['label'] or '(이름 없음)'}{risk} -> {pick} ({best['stability'] if best else 0})"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """`python scripts/explorer/page_analysis.py <snapshot.json> [--json]` — 저장하지 않고 출력만 한다."""
    parser = argparse.ArgumentParser(description="페이지 스냅샷 분석(읽기 전용)")
    parser.add_argument("snapshot", help="page_snapshot 이 저장한 JSON 파일")
    parser.add_argument("--json", action="store_true", help="전체 분석 결과를 JSON 으로 출력")
    args = parser.parse_args(argv)
    # 한국어 Windows 는 파이프·리다이렉트 출력이 cp949 라 한글이 깨진다 — 프로젝트 CLI 관례대로 UTF-8 로 맞춘다.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    path = Path(args.snapshot)
    try:
        snapshot = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.error("스냅샷을 읽을 수 없음: %s (%s)", path, type(exc).__name__)
        return 2
    result = analyze_snapshot(snapshot)
    sys.stdout.write(
        (json.dumps(result, ensure_ascii=False, indent=2) if args.json else _format_summary(result)) + "\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
