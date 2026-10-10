"""local_agent 웹 페이지 read-only 분석기 (Stage 1).

이 모듈은 실제 브라우저 조작이나 폼 제출을 하지 않는다. 입력된 HTML
문자열을 static 분석하여 페이지 구조 요약을 생성한다.

결과에 절대 포함되지 않는 것:
  - password / hidden input value
  - cookie / set-cookie / authorization / bearer / session
  - csrf / access_token / refresh_token 원문
  - HTML 원문 전체 (요약/짧은 텍스트만 보관)

본 모듈은 브라우저 자동화 라이브러리(Playwright, Selenium) 를 import 하지
않으며 실제 클릭/입력/제출 API 를 호출하지 않는다.
"""

from __future__ import annotations

import ipaddress
import re
from html.parser import HTMLParser
from typing import Any, ClassVar
from urllib.parse import urljoin, urlparse

from core.agent_runtime.browser.site_mapper import _SENSITIVE_NAME_TOKENS, _is_sensitive_name

# ─── 키워드 테이블 ─────────────────────────────────────────────────────────

# 쓰기/상태 변경 동작을 의미하는 한국어 키워드.
RISK_WRITE_KEYWORDS: tuple[str, ...] = (
    "저장",
    "제출",
    "등록",
    "삭제",
    "수정",
    "승인",
    "전송",
    "결제",
    "확정",
    "마감",
    "신청",
    "취소",
)

# 읽기/조회 전용 한국어 키워드.
SAFE_READ_KEYWORDS: tuple[str, ...] = (
    "조회",
    "검색",
    "보기",
    "목록",
    "상세",
)

# 파일 내려받기/내보내기 — 쓰기는 아니지만 네트워크 side-effect 주의.
MEDIUM_KEYWORDS: tuple[str, ...] = (
    "다운로드",
    "download",
    "export",
    "엑셀",
    "pdf",
)

# 업무 도메인 키워드 (링크/표 헤더 점수화용).
BUSINESS_KEYWORDS: tuple[str, ...] = (
    "기성",
    "청구",
    "정산",
    "계약",
    "현장",
    "내역",
    "견적",
)

# danger_write 로 간주해야 하는 href/링크 텍스트 토큰.
_LINK_DANGER_TOKENS: tuple[str, ...] = (
    "delete",
    "remove",
    "logout",
    "signout",
    "destroy",
    "삭제",
    "탈퇴",
    "로그아웃",
)


# value 를 읽지 않는 input type.
_NO_VALUE_INPUT_TYPES: frozenset[str] = frozenset(
    {
        "password",
        "hidden",
    }
)

_WS_RE = re.compile(r"\s+")


# ─── URL 안전성 검사 ───────────────────────────────────────────────────────


def validate_url_for_readonly_open(
    url: str,
    *,
    allow_private_network: bool = False,
    allow_about_blank: bool = False,
) -> dict[str, Any]:
    """http/https 공개 호스트만 허용. 내부망/loopback/서비스 스킴은 차단.

    Stage 1 에서는 `allow_private_network` 를 사용하지 않는 것이 기본이며,
    향후 허용 필요 시 명시적으로 True 를 지정한 호출만 통과한다.

    `allow_about_blank=True` 일 때만 정확히 ``about:blank`` (대소문자 무시,
    뒤에 다른 토큰 없음) 문자열을 read-only 관찰 후보로 허용한다. 이 게이트는
    Stage 12I controlled browser open 의 첫 후보용이며, ``about:srcdoc`` /
    ``about:config`` 등 다른 ``about:*`` 는 절대 통과시키지 않는다. 호출자가
    명시적으로 True 를 전달하지 않으면 기본 동작(URL_SCHEME_BLOCKED)이 유지된다.
    """
    if not isinstance(url, str) or not url.strip():
        return {"ok": False, "error_code": "URL_EMPTY", "reason": "url 누락"}

    raw = url.strip()

    if allow_about_blank and raw.lower() == "about:blank":
        return {
            "ok": True,
            "scheme": "about",
            "host": "",
            "port": None,
            "path": "blank",
            "about_blank": True,
        }

    try:
        parsed = urlparse(raw)
    except ValueError:
        return {"ok": False, "error_code": "URL_PARSE_FAILED", "reason": "URL 파싱 실패"}

    scheme = (parsed.scheme or "").lower()
    if scheme not in ("http", "https"):
        return {
            "ok": False,
            "error_code": "URL_SCHEME_BLOCKED",
            "reason": f"허용되지 않은 스킴: {scheme or '(missing)'}",
        }

    host = (parsed.hostname or "").lower()
    if not host:
        return {
            "ok": False,
            "error_code": "URL_NO_HOST",
            "reason": "호스트 누락",
        }

    if host in {"localhost", "localhost.localdomain", "ip6-localhost"} and not allow_private_network:
        return {
            "ok": False,
            "error_code": "URL_HOST_BLOCKED",
            "reason": f"localhost 기본 차단: {host}",
        }

    ip_obj = _try_parse_ip(host)
    if (
        ip_obj is not None
        and not allow_private_network
        and (
            ip_obj.is_loopback
            or ip_obj.is_private
            or ip_obj.is_link_local
            or ip_obj.is_multicast
            or ip_obj.is_unspecified
            or ip_obj.is_reserved
        )
    ):
        return {
            "ok": False,
            "error_code": "URL_HOST_BLOCKED",
            "reason": f"내부/loopback IP 기본 차단: {host}",
        }

    return {
        "ok": True,
        "scheme": scheme,
        "host": host,
        "port": parsed.port,
        "path": parsed.path,
    }


def _try_parse_ip(host: str) -> Any | None:
    if not host:
        return None
    candidate = host
    if candidate.startswith("[") and candidate.endswith("]"):
        candidate = candidate[1:-1]
    try:
        return ipaddress.ip_address(candidate)
    except (ValueError, TypeError):
        return None


# ─── HTML 구조 분석 ────────────────────────────────────────────────────────


def analyze_html_structure(
    html: str,
    base_url: str | None = None,
    keyword_hints: list[str] | None = None,
) -> dict[str, Any]:
    """HTML 문자열을 read-only 로 분석해 구조 요약 dict 반환.

    password / hidden input value, cookie, token 류, HTML 원문 전체는 반환
    결과에 포함되지 않는다. base_url 이 주어지면 상대경로 링크는
    normalized_href 에 urljoin 으로 절대화한다.
    """
    if not isinstance(html, str):
        return _empty_result("HTML_INVALID_TYPE")
    if not html.strip():
        result = _empty_result(None)
        result["ok"] = True
        return result

    parser = _StructureParser()
    try:
        parser.feed(html)
        parser.close()
    except Exception:  # pragma: no cover - html.parser 는 관대함  # noqa: S110, BLE001 - html.parser 파싱 중 예외를 무시(이미 pragma no cover 주석 존재) - 파서가 관대하지 않은 입력에 예외를 던져도 지금까지 수집한 부분 결과로 계속 진행, 읽기전용 페이지 읽기
        # 파서가 예외를 던지더라도 지금까지 수집한 상태로 결과 생성
        pass

    hints = [h for h in (keyword_hints or []) if isinstance(h, str) and h.strip()]
    for link in parser.links:
        link["keyword_score"] = _score_keywords(
            link.get("text", ""),
            link.get("raw_href", ""),
            hints,
        )
        link["risk_hint"] = _link_risk_hint(
            link.get("raw_href", ""),
            link.get("text", ""),
        )
        href = link.pop("raw_href", "")
        link["href"] = href
        link["normalized_href"] = urljoin(base_url, href) if base_url and href else href

    # 폼 위험도 보정 — 폼 내부 danger_write 버튼이 있으면 danger_write 로 상향.
    # (파서 단계에서는 버튼과 폼을 독립 수집하므로 후처리로 연결)
    for form in parser.forms:
        if form.get("has_password") and form.get("risk_level") == "unknown":
            form["risk_level"] = "medium"
        if form.get("risk_level") == "unknown" and form.get("method") == "post":
            form["risk_level"] = "medium"

    risky = _collect_risky_elements(
        parser.buttons,
        parser.links,
        parser.forms,
    )
    recommended = _recommend_read_only_actions(
        parser.page_title,
        parser.headings,
        parser.tables,
        parser.links,
    )

    return {
        "ok": True,
        "page_title": parser.page_title[:300],
        "headings": parser.headings,
        "links": parser.links,
        "buttons": parser.buttons,
        "inputs": parser.inputs,
        "selects": parser.selects,
        "textareas": parser.textareas,
        "forms": parser.forms,
        "tables": parser.tables,
        "meta": parser.meta,
        "risky_elements": risky,
        "recommended_actions": recommended,
        "counts": {
            "headings": len(parser.headings),
            "links": len(parser.links),
            "buttons": len(parser.buttons),
            "inputs": len(parser.inputs),
            "forms": len(parser.forms),
            "tables": len(parser.tables),
        },
    }


def classify_button_text(text: str, btype: str = "") -> tuple[str, str]:
    """버튼 텍스트/타입을 보고 위험도와 이유를 반환. (공개 헬퍼)"""
    return _classify_button(text, btype)


# ─── 내부 ───────────────────────────────────────────────────────────────────


def _empty_result(error_code: str | None) -> dict[str, Any]:
    base: dict[str, Any] = {
        "ok": error_code is None,
        "page_title": "",
        "headings": [],
        "links": [],
        "buttons": [],
        "inputs": [],
        "selects": [],
        "textareas": [],
        "forms": [],
        "tables": [],
        "meta": {},
        "risky_elements": [],
        "recommended_actions": [],
        "counts": {
            "headings": 0,
            "links": 0,
            "buttons": 0,
            "inputs": 0,
            "forms": 0,
            "tables": 0,
        },
    }
    if error_code is not None:
        base["error_code"] = error_code
    return base


def _classify_button(text: str, btype: str = "") -> tuple[str, str]:
    """버튼 위험도 분류. 반환값: (risk_level, reason).

    risk_level ∈ {"safe_read", "medium", "danger_write", "unknown"}
    """
    text_clean = (text or "").strip()
    btype_lower = (btype or "").strip().lower()

    for kw in RISK_WRITE_KEYWORDS:
        if kw in text_clean:
            return "danger_write", f"keyword:{kw}"

    # MEDIUM 은 SAFE_READ 보다 먼저 체크 (예: "엑셀다운로드" 가 조회로 잘못 분류되지 않게).
    lowered = text_clean.lower()
    for kw in MEDIUM_KEYWORDS:
        if kw.lower() in lowered:
            return "medium", f"keyword:{kw}"

    for kw in SAFE_READ_KEYWORDS:
        if kw in text_clean:
            return "safe_read", f"keyword:{kw}"

    if btype_lower == "submit":
        return "danger_write", "type:submit"
    if btype_lower == "reset":
        return "medium", "type:reset"
    if btype_lower == "button":
        return "unknown", "type:button"

    return "unknown", ""


def _link_risk_hint(href: str, text: str) -> str:
    combined = f"{href or ''} {text or ''}".lower()
    for kw in _LINK_DANGER_TOKENS:
        if kw in combined:
            return "danger_write"
    for kw in MEDIUM_KEYWORDS:
        if kw.lower() in combined:
            return "medium"
    return "safe_read"


def _score_keywords(text: str, href: str, hints: list[str]) -> int:
    if not hints:
        return 0
    text_l = (text or "").lower()
    href_l = (href or "").lower()
    score = 0
    for kw in hints:
        kw_l = kw.lower()
        if kw in (text or "") or kw_l in text_l:
            score += 2
        elif kw in (href or "") or kw_l in href_l:
            score += 1
    # 업무 키워드 bonus
    for kw in BUSINESS_KEYWORDS:
        if kw in (text or "") or kw in (href or ""):
            score += 1
    return score


def _collect_risky_elements(
    buttons: list[dict],
    links: list[dict],
    forms: list[dict],
) -> list[dict]:
    risky: list[dict] = []
    for b in buttons:
        if b.get("risk_level") == "danger_write":
            risky.append(
                {
                    "kind": "button",
                    "text": b.get("text", ""),
                    "reason": b.get("reason", ""),
                }
            )
    for link in links:
        if link.get("risk_hint") == "danger_write":
            risky.append(
                {
                    "kind": "link",
                    "text": link.get("text", ""),
                    "reason": "danger_href",
                }
            )
    for f in forms:
        if f.get("has_password"):
            risky.append({"kind": "form", "reason": "has_password"})
        if f.get("risk_level") == "danger_write":
            risky.append(
                {
                    "kind": "form",
                    "reason": f"action:{(f.get('action') or '')[:120]}",
                }
            )
    return risky


def _recommend_read_only_actions(
    page_title: str,
    headings: list[dict],
    tables: list[dict],
    links: list[dict],
) -> list[dict]:
    """read-only 권장 액션만 생성. click/submit/save 류는 절대 포함되지 않음."""
    recs: list[dict] = []
    joined = " ".join([page_title or ""] + [h.get("text", "") for h in headings])
    for kw in BUSINESS_KEYWORDS:
        if kw in joined:
            recs.append(
                {
                    "action": "analyze_text",
                    "reason": f"business_keyword:{kw}",
                }
            )
            break
    if tables:
        recs.append(
            {
                "action": "read_table",
                "reason": f"table_count={len(tables)}",
            }
        )
    safe_links = [link for link in links if link.get("risk_hint") != "danger_write"]
    if safe_links:
        recs.append(
            {
                "action": "list_links",
                "reason": f"safe_links={len(safe_links)}",
            }
        )
    return recs


def _collapse_ws(s: str) -> str:
    return _WS_RE.sub(" ", (s or "").strip())



class _StructureParser(HTMLParser):
    """태그 이벤트를 수집해 구조 요약 필드를 채운다.

    실행 중 어떤 속성/텍스트도 값(value)을 그대로 원문 저장하지 않는다.
    특히 password/hidden input 은 value 속성을 읽지 않는다. meta 값은
    name 이 민감 토큰을 포함하면 드롭한다.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.page_title: str = ""
        self.headings: list[dict[str, Any]] = []
        self.links: list[dict[str, Any]] = []
        self.buttons: list[dict[str, Any]] = []
        self.inputs: list[dict[str, Any]] = []
        self.selects: list[dict[str, Any]] = []
        self.textareas: list[dict[str, Any]] = []
        self.forms: list[dict[str, Any]] = []
        self.tables: list[dict[str, Any]] = []
        self.meta: dict[str, str] = {}

        self._title_buf: list[str] | None = None
        self._heading_level: int = 0
        self._heading_buf: list[str] | None = None
        self._a_attrs: dict[str, str] | None = None
        self._a_buf: list[str] | None = None
        self._button_attrs: dict[str, str] | None = None
        self._button_buf: list[str] | None = None
        self._current_form: dict[str, Any] | None = None
        self._current_table: dict[str, Any] | None = None
        self._current_tr_cells: int = 0
        self._in_tr: bool = False
        self._in_th: bool = False
        self._in_td: bool = False
        self._cell_buf: list[str] | None = None
        self._select_attrs: dict[str, str] | None = None
        self._select_options: int = 0
        self._textarea_attrs: dict[str, str] | None = None
        self._textarea_buf: list[str] | None = None

    # ── 시작 태그 ──
    _START_HANDLERS: ClassVar[dict[str, str]] = {
        "title": "_start_title",
        "h1": "_start_heading",
        "h2": "_start_heading",
        "h3": "_start_heading",
        "h4": "_start_heading",
        "h5": "_start_heading",
        "h6": "_start_heading",
        "a": "_start_a",
        "button": "_start_button",
        "input": "_start_input",
        "select": "_start_select",
        "option": "_start_option",
        "textarea": "_start_textarea",
        "form": "_start_form",
        "table": "_start_table",
        "tr": "_start_tr",
        "th": "_start_cell",
        "td": "_start_cell",
        "meta": "_start_meta",
    }
    _END_HANDLERS: ClassVar[dict[str, str]] = {
        "title": "_end_title",
        "h1": "_end_heading",
        "h2": "_end_heading",
        "h3": "_end_heading",
        "h4": "_end_heading",
        "h5": "_end_heading",
        "h6": "_end_heading",
        "a": "_end_a",
        "button": "_end_button",
        "select": "_end_select",
        "textarea": "_end_textarea",
        "form": "_end_form",
        "table": "_end_table",
        "tr": "_end_tr",
        "th": "_end_th",
        "td": "_end_td",
    }

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k: (v or "") for k, v in attrs}
        handler = self._START_HANDLERS.get(tag)
        if handler is not None:
            getattr(self, handler)(tag, a)

    def _start_title(self, tag: str, a: dict[str, str]) -> None:
        self._title_buf = []

    def _start_heading(self, tag: str, a: dict[str, str]) -> None:
        self._heading_level = int(tag[1])
        self._heading_buf = []

    def _start_a(self, tag: str, a: dict[str, str]) -> None:
        self._a_attrs = a
        self._a_buf = []

    def _start_button(self, tag: str, a: dict[str, str]) -> None:
        self._button_attrs = a
        self._button_buf = []

    def _start_input(self, tag: str, a: dict[str, str]) -> None:
        self._handle_input(a)

    def _start_select(self, tag: str, a: dict[str, str]) -> None:
        self._select_attrs = a
        self._select_options = 0

    def _start_option(self, tag: str, a: dict[str, str]) -> None:
        if self._select_attrs is not None:
            self._select_options += 1

    def _start_textarea(self, tag: str, a: dict[str, str]) -> None:
        self._textarea_attrs = a
        self._textarea_buf = []

    def _start_form(self, tag: str, a: dict[str, str]) -> None:
        self._current_form = {
            "method": (a.get("method") or "get").lower(),
            "action": (a.get("action") or "")[:300],
            "field_count": 0,
            "has_password": False,
            "has_hidden": False,
            "risk_level": "unknown",
        }

    def _start_table(self, tag: str, a: dict[str, str]) -> None:
        self._current_table = {
            "headers": [],
            "row_count": 0,
            "column_count": 0,
            "purpose_candidate": [],
            "_max_cols": 0,
        }

    def _start_tr(self, tag: str, a: dict[str, str]) -> None:
        if self._current_table is not None:
            self._in_tr = True
            self._current_tr_cells = 0
            self._current_table["row_count"] += 1

    def _start_cell(self, tag: str, a: dict[str, str]) -> None:
        if self._current_table is None:
            return
        if tag == "th":
            self._in_th = True
        else:
            self._in_td = True
        self._cell_buf = []
        self._current_tr_cells += 1

    def _start_meta(self, tag: str, a: dict[str, str]) -> None:
        name = (a.get("name") or a.get("property") or "").strip()
        content = a.get("content", "")
        if name and not _is_sensitive_name(name):
            # 값 자체도 민감 토큰을 포함하면 드롭
            if not _is_sensitive_name(content):
                self.meta[name[:64]] = content[:200]

    # ── 종료 태그 ──
    def handle_endtag(self, tag: str) -> None:
        handler = self._END_HANDLERS.get(tag)
        if handler is not None:
            getattr(self, handler)()

    def _end_title(self) -> None:
        if self._title_buf is not None:
            self.page_title = _collapse_ws("".join(self._title_buf))
            self._title_buf = None

    def _end_heading(self) -> None:
        if self._heading_buf is not None:
            text = _collapse_ws("".join(self._heading_buf))
            if text:
                self.headings.append(
                    {
                        "level": self._heading_level,
                        "text": text[:200],
                    }
                )
            self._heading_buf = None
            self._heading_level = 0

    def _end_a(self) -> None:
        if self._a_attrs is not None:
            text = _collapse_ws("".join(self._a_buf or []))
            href = (self._a_attrs.get("href") or "")[:500]
            self.links.append(
                {
                    "text": text[:200],
                    "raw_href": href,
                }
            )
            self._a_attrs = None
            self._a_buf = None

    def _end_button(self) -> None:
        if self._button_attrs is not None:
            text = _collapse_ws("".join(self._button_buf or []))
            btype = (self._button_attrs.get("type") or "")[:32]
            risk, reason = _classify_button(text, btype)
            self.buttons.append(
                {
                    "text": text[:200],
                    "type": btype,
                    "risk_level": risk,
                    "reason": reason,
                }
            )
            # 폼 내부 danger_write 버튼은 폼 위험도에도 반영
            if self._current_form is not None and risk == "danger_write":
                self._current_form["risk_level"] = "danger_write"
            self._button_attrs = None
            self._button_buf = None

    def _end_select(self) -> None:
        if self._select_attrs is not None:
            self.selects.append(
                {
                    "name": (self._select_attrs.get("name") or "")[:200],
                    "options_count": self._select_options,
                    "has_multiple": "multiple" in self._select_attrs,
                }
            )
            self._select_attrs = None
            self._select_options = 0

    def _end_textarea(self) -> None:
        if self._textarea_attrs is not None:
            # textarea 의 내부 텍스트는 value 에 해당하므로 저장하지 않는다.
            self.textareas.append(
                {
                    "name": (self._textarea_attrs.get("name") or "")[:200],
                    "placeholder": (self._textarea_attrs.get("placeholder") or "")[:200],
                }
            )
            self._textarea_attrs = None
            self._textarea_buf = None

    def _end_form(self) -> None:
        if self._current_form is not None:
            self.forms.append(self._current_form)
            self._current_form = None

    def _end_table(self) -> None:
        if self._current_table is not None:
            t = self._current_table
            t["column_count"] = t.pop("_max_cols", 0)
            joined_headers = " ".join(t["headers"])
            t["purpose_candidate"] = [kw for kw in BUSINESS_KEYWORDS if kw in joined_headers]
            self.tables.append(t)
            self._current_table = None
            self._in_tr = False
            self._current_tr_cells = 0

    def _end_tr(self) -> None:
        if self._current_table is not None:
            self._current_table["_max_cols"] = max(
                self._current_table.get("_max_cols", 0),
                self._current_tr_cells,
            )
        self._in_tr = False
        self._current_tr_cells = 0

    def _end_th(self) -> None:
        if self._in_th and self._current_table is not None:
            text = _collapse_ws("".join(self._cell_buf or []))
            if text:
                self._current_table["headers"].append(text[:200])
        self._in_th = False
        self._cell_buf = None

    def _end_td(self) -> None:
        self._in_td = False
        self._cell_buf = None

    # ── 텍스트 ──
    def handle_data(self, data: str) -> None:
        if self._title_buf is not None:
            self._title_buf.append(data)
        if self._heading_buf is not None:
            self._heading_buf.append(data)
        if self._a_buf is not None:
            self._a_buf.append(data)
        if self._button_buf is not None:
            self._button_buf.append(data)
        if self._cell_buf is not None:
            self._cell_buf.append(data)
        # textarea 내부 data 는 의도적으로 버린다 (value 저장 금지).

    # ── input 처리 ──
    def _handle_input(self, a: dict[str, str]) -> None:
        itype = (a.get("type") or "text").strip().lower()[:32]
        name = (a.get("name") or "")[:200]
        placeholder = (a.get("placeholder") or "")[:200]
        label = _guess_label(a)[:200]

        # value 는 원칙적으로 읽지 않는다. 단, submit/button/reset 의 value 는
        # 버튼 캡션 (공개 HTML). password / hidden 은 절대 value 를 읽지 않는다.
        caption = ""
        if itype in ("submit", "button", "reset"):
            raw_value = a.get("value") or ""
            if not _is_sensitive_name(name) and not _is_sensitive_name(raw_value):
                caption = raw_value[:80]

        item: dict[str, Any] = {
            "name": name,
            "type": itype,
            "placeholder": placeholder,
            "label": label,
        }
        # value 키 자체를 item 에 만들지 않는다 (password/hidden 포함).
        self.inputs.append(item)

        if itype in ("submit", "button", "reset"):
            risk, reason = _classify_button(caption, itype)
            self.buttons.append(
                {
                    "text": caption[:80] if caption else f"<input:{itype}>",
                    "type": itype,
                    "risk_level": risk,
                    "reason": reason,
                }
            )
            if self._current_form is not None and risk == "danger_write":
                self._current_form["risk_level"] = "danger_write"

        if self._current_form is not None:
            self._current_form["field_count"] += 1
            if itype == "password":
                self._current_form["has_password"] = True
            if itype == "hidden":
                self._current_form["has_hidden"] = True


def _guess_label(attrs: dict[str, str]) -> str:
    for key in ("aria-label", "data-label", "title", "placeholder"):
        v = attrs.get(key)
        if v:
            return v
    return ""


__all__ = [
    "BUSINESS_KEYWORDS",
    "MEDIUM_KEYWORDS",
    "RISK_WRITE_KEYWORDS",
    "SAFE_READ_KEYWORDS",
    "analyze_html_structure",
    "classify_button_text",
    "validate_url_for_readonly_open",
]
