"""F-4G-1 — controlled site action planner (dry-run only).

목적:
  사용자가 직접 로그인한 브라우저 세션에서 AI 가 안전한 조회 / 메뉴 이동 /
  다운로드 후보를 "분류" 하기 위한 정책 엔진. 본 모듈은 어떤 경우에도
  실제 브라우저를 열거나 클릭/입력/다운로드를 수행하지 않는다. observer
  결과(dict) 만 받아 candidate 분류 + dry-run plan 만 산출한다.

본 모듈에서 절대 수행하지 않는 것:
  - ``page.click`` / ``page.fill`` / ``page.type`` / ``page.press``
  - ``page.keyboard.*`` / ``page.mouse.*``
  - ``page.set_input_files`` / ``page.select_option``
  - 폼 ``submit`` / 파일 다운로드 / 보안프로그램 자동 설치
  - ID / PW / 인증서 비밀번호 입력
  - 쿠키 / storage_state / localStorage / sessionStorage / cookies 접근
  - 브라우저 launch / Playwright import
  - cookie / session / storage_state / secret / env 값 출력

분류 정책 (3단계):
  1) blocked         — 신고/납부/제출/발행/이체/변경/삭제 등 위험 액션
  2) approval_required — 다운로드/엑셀/PDF/저장 — 승인 후 실행 가능
  3) read_only       — 조회/검색/열람/내역/상세/보기/미리보기

분류 우선순위 (높음→낮음):
  blocked > approval_required > read_only > unknown

page_state 가드 (plan-level 중단 신호):
  - login_required / authenticated 가 아닌 unknown / public_page → 그대로 진행
  - login_required / sensitive_submission → manual_action_required (사용자가
    먼저 로그인 / 위험 페이지 회피 필요)
  - security_program_required / keyboard_security_required /
    certificate_plugin_required / browser_not_supported /
    manual_install_required → manual_action_required (사용자가 직접 설치/조치)
  - captcha_or_bot_check → manual_action_required (사용자가 직접 통과)
  - access_denied / not_found / server_error → unrecoverable, plan 중단
"""
from __future__ import annotations

import re
from typing import Any, Optional
from urllib.parse import urlparse


# ─── 차단 / 다운로드 / 읽기 토큰 ─────────────────────────────────────────

# 위험 액션 — 자금 이동 / 신고 제출 / 발행 / 정보 변경 / 위임 / 삭제 / 신청
# 등. 단독 광범위 단어("발급", "신고") 만으로는 차단하지 않고, 동사 결합
# / 강한 신호 토큰만 포함한다 — hometax adapter 의 _SENSITIVE_TOKENS 보다
# 보수적이지만 동등하거나 더 폭넓다.
_BLOCKED_TOKENS: tuple[str, ...] = (
    # 제출 계열
    "최종 제출", "신고서 제출", "신고 제출", "제출하기", "확인 후 제출",
    "최종 확인",
    "제출",                 # 단독 — 본 정책에서는 차단 (대표가 직접 한다)
    # 납부 / 결제 / 이체 / 송금
    "납부하기", "납부", "전자납부",
    "결제하기", "결제",
    "이체", "계좌이체", "송금",
    # 발행 / 발급 — 강한 결합형
    "발행하기", "발행",
    "전자세금계산서 발행", "전자세금계산서 발급", "세금계산서 발행",
    "세금계산서 발급", "현금영수증 발행",
    # 전송 — 동사 결합형
    "전송하기", "최종전송",
    # 정보 변경 / 권한 변경 / 위임 / 수임 / 해지 / 삭제 / 취소 / 신청
    "사업자정보 변경", "사업자등록정보 변경", "정보 변경", "권한 변경",
    "위임/수임 변경", "위임 변경", "수임 변경", "위임", "수임",
    "해지", "삭제", "취소",
    "정정신고", "신고하기", "신청하기",
)

# 다운로드 / 저장 — 사용자 승인 후 실행 가능. 강한 신호 토큰만.
_DOWNLOAD_TOKENS: tuple[str, ...] = (
    "다운로드", "내려받기",
    "엑셀", "Excel",
    "PDF",
    "인쇄", "저장",
    ".csv", ".xls", ".xlsx",
)

# 읽기 / 조회 — 안전 후보.
_READ_ONLY_TOKENS: tuple[str, ...] = (
    "조회", "검색", "확인", "내역", "목록", "상세", "보기", "열람", "미리보기",
)


# page_state 가드.
_MANUAL_ACTION_PAGE_STATES: frozenset[str] = frozenset({
    "login_required",
    "sensitive_submission",
    "security_program_required",
    "keyboard_security_required",
    "certificate_plugin_required",
    "browser_not_supported",
    "manual_install_required",
    "captcha_or_bot_check",
})

_UNRECOVERABLE_PAGE_STATES: frozenset[str] = frozenset({
    "access_denied", "not_found", "server_error",
})


# 출력 길이 상한 (observer / hometax adapter 와 동일 수준).
_OUT_TEXT_CAP = 200
_OUT_HREF_CAP = 300
_OUT_RISK_CAP = 40

_QUERY_FRAG_RE = re.compile(r"[?#].*$")


# ─── 단일 candidate 분류 ────────────────────────────────────────────────

def classify_site_action_candidate(
    candidate: Any,
) -> dict[str, Any]:
    """단일 candidate(link/button/form 한 개) 를 분류.

    입력 dict 의 가능한 키:
      text / href / action / type / risk_hint / risk_level / has_password

    출력 (항상 동일 schema):
      {
        "allowed":               bool,
        "risk_level":            "read_only" | "download" | "blocked"
                                  | "dangerous" | "unknown",
        "reason":                str,
        "matched_blocked_tokens": [str, ...],
        "matched_download_tokens": [str, ...],
        "matched_read_tokens":    [str, ...],
        "requires_approval":     bool,
        "warnings":              [str, ...],
      }

    정책:
      1) candidate dict 가 아니거나 빈 dict 면 unknown / not allowed.
      2) password 입력 폼은 "dangerous" — read 후보로 절대 잡지 않는다.
      3) blocked 토큰 매칭 → blocked, allowed=False, requires_approval=False.
      4) download 토큰 매칭 → download, allowed=True, requires_approval=True.
      5) read-only 토큰 매칭 → read_only, allowed=True, requires_approval=False.
      6) 어디에도 매칭 안 되면 unknown / allowed=False — 명시적 신호 없는
         후보는 임의 실행 금지.

    어떤 경우에도 입력 candidate 의 raw value / password / cookie 필드를
    출력에 포함하지 않는다.
    """
    if not isinstance(candidate, dict):
        return _empty_candidate_result(
            risk_level="unknown",
            reason="candidate_not_dict",
            warnings=["candidate_not_dict"],
        )

    warnings: list[str] = []

    text = _safe_str(candidate.get("text"))
    href = _safe_str(candidate.get("href") or candidate.get("action"))
    href = _strip_query_fragment(href)
    btn_type = _safe_str(candidate.get("type"))
    has_password = bool(candidate.get("has_password"))

    # password 입력 폼은 무조건 dangerous (사용자가 직접 입력해야 한다).
    if has_password:
        return {
            "allowed": False,
            "risk_level": "dangerous",
            "reason": "password_input_form",
            "matched_blocked_tokens": [],
            "matched_download_tokens": [],
            "matched_read_tokens": [],
            "requires_approval": False,
            "warnings": warnings + ["password_input_form"],
        }

    blob = " ".join([text, href, btn_type])
    if not blob.strip():
        return _empty_candidate_result(
            risk_level="unknown",
            reason="empty_candidate_text",
            warnings=warnings + ["empty_candidate_text"],
        )

    blob_lower = blob.lower()

    matched_blocked = _matched_tokens(blob_lower, _BLOCKED_TOKENS)
    matched_download = _matched_tokens(blob_lower, _DOWNLOAD_TOKENS)
    matched_read = _matched_tokens(blob_lower, _READ_ONLY_TOKENS)

    if matched_blocked:
        return {
            "allowed": False,
            "risk_level": "blocked",
            "reason": "blocked_action_token",
            "matched_blocked_tokens": matched_blocked,
            "matched_download_tokens": matched_download,
            "matched_read_tokens": matched_read,
            "requires_approval": False,
            "warnings": warnings,
        }

    if matched_download:
        return {
            "allowed": True,
            "risk_level": "download",
            "reason": "download_token",
            "matched_blocked_tokens": [],
            "matched_download_tokens": matched_download,
            "matched_read_tokens": matched_read,
            "requires_approval": True,
            "warnings": warnings,
        }

    if matched_read:
        return {
            "allowed": True,
            "risk_level": "read_only",
            "reason": "read_only_token",
            "matched_blocked_tokens": [],
            "matched_download_tokens": [],
            "matched_read_tokens": matched_read,
            "requires_approval": False,
            "warnings": warnings,
        }

    return _empty_candidate_result(
        risk_level="unknown",
        reason="no_token_match",
        warnings=warnings,
    )


# ─── 전체 plan 빌더 ─────────────────────────────────────────────────────

def build_controlled_action_plan(
    observer_result: Any,
    *,
    site_key: str = "",
) -> dict[str, Any]:
    """observer 결과를 받아 controlled action plan 을 생성.

    출력 schema:
      {
        "site_key":               str,
        "page_state":             str,
        "manual_action_required": bool,
        "unrecoverable":          bool,
        "safe_read_candidates":   [ {kind, text, href, matched_tokens}, ... ],
        "download_candidates":    [ {kind, text, href, matched_tokens}, ... ],
        "blocked_candidates":     [ {kind, text, href, matched_tokens}, ... ],
        "dangerous_candidates":   [ {kind, text, href}, ... ],
        "warnings":               [str, ...],
      }

    page_state 가드:
      - login_required / sensitive_submission / security_* / captcha_*
        / browser_not_supported / manual_install_required
        → manual_action_required=True, candidates 분류는 진행하되
          warnings 에 명시.
      - access_denied / not_found / server_error
        → unrecoverable=True, candidates 모두 빈 리스트.
    """
    if not isinstance(observer_result, dict):
        return _empty_plan_result(
            site_key=_safe_str(site_key),
            page_state="",
            warnings=["observer_result_not_dict"],
        )

    warnings: list[str] = []

    page_state = _safe_str(observer_result.get("page_state"))
    site_key_safe = _safe_str(site_key) or _infer_site_key(observer_result)

    # unrecoverable — plan 중단.
    if page_state in _UNRECOVERABLE_PAGE_STATES:
        warnings.append(f"page_state_unrecoverable:{page_state}")
        return {
            "site_key": site_key_safe,
            "page_state": page_state,
            "manual_action_required": False,
            "unrecoverable": True,
            "safe_read_candidates": [],
            "download_candidates": [],
            "blocked_candidates": [],
            "dangerous_candidates": [],
            "warnings": warnings,
        }

    manual_action_required = page_state in _MANUAL_ACTION_PAGE_STATES
    if manual_action_required:
        warnings.append(f"manual_action_required:{page_state}")

    links = observer_result.get("links")
    if not isinstance(links, list):
        if links is not None:
            warnings.append("links_not_list")
        links = []

    buttons = observer_result.get("buttons")
    if not isinstance(buttons, list):
        if buttons is not None:
            warnings.append("buttons_not_list")
        buttons = []

    forms = observer_result.get("forms")
    if not isinstance(forms, list):
        if forms is not None:
            warnings.append("forms_not_list")
        forms = []

    safe_read: list[dict[str, Any]] = []
    download: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    dangerous: list[dict[str, Any]] = []

    for link in links:
        if not isinstance(link, dict):
            continue
        verdict = classify_site_action_candidate(link)
        entry = _build_candidate_entry(kind="link", source=link, verdict=verdict)
        _route_entry(verdict, entry, safe_read, download, blocked, dangerous)

    for btn in buttons:
        if not isinstance(btn, dict):
            continue
        verdict = classify_site_action_candidate(btn)
        entry = _build_candidate_entry(kind="button", source=btn, verdict=verdict)
        _route_entry(verdict, entry, safe_read, download, blocked, dangerous)

    for form in forms:
        if not isinstance(form, dict):
            continue
        verdict = classify_site_action_candidate(form)
        entry = _build_candidate_entry(kind="form", source=form, verdict=verdict)
        _route_entry(verdict, entry, safe_read, download, blocked, dangerous)

    return {
        "site_key": site_key_safe,
        "page_state": page_state,
        "manual_action_required": bool(manual_action_required),
        "unrecoverable": False,
        "safe_read_candidates": safe_read,
        "download_candidates": download,
        "blocked_candidates": blocked,
        "dangerous_candidates": dangerous,
        "warnings": warnings,
    }


# ─── 사전 검증 ────────────────────────────────────────────────────────────

def validate_controlled_action(action: Any) -> dict[str, Any]:
    """실제 실행 전 단일 action 의 안전성 사전 검증 (dry-run 의 입력 게이트).

    입력 action dict 예:
      {
        "kind":      "link" | "button" | "form",
        "text":      "...",
        "href":      "...",
        "risk_level": "read_only" | "download" | ...,
      }

    출력:
      {
        "ok":         bool,
        "error_code": str,        # ok=True 이면 빈 문자열
        "warnings":   [str, ...],
      }

    정책:
      - dict 아님 / 빈 dict → ACTION_NOT_DICT.
      - kind 미지정 / 허용외 → ACTION_KIND_INVALID.
      - text / href 둘 다 비어있음 → ACTION_EMPTY.
      - href 가 http/https 가 아닌 scheme (javascript:, data:, file:) →
        ACTION_HREF_SCHEME_BLOCKED.
      - classify_site_action_candidate 결과가 blocked / dangerous → ACTION_BLOCKED.
      - read_only 면 ok=True.
      - download 는 ok=True + warnings 에 approval_required.
      - unknown 은 ACTION_UNKNOWN.
    """
    if not isinstance(action, dict):
        return _validation_err("ACTION_NOT_DICT", ["action_not_dict"])

    kind = _safe_str(action.get("kind")).lower()
    if kind not in ("link", "button", "form"):
        return _validation_err(
            "ACTION_KIND_INVALID", [f"action_kind_invalid:{kind or 'none'}"],
        )

    text = _safe_str(action.get("text"))
    href = _safe_str(action.get("href") or action.get("action"))
    if not text.strip() and not href.strip():
        return _validation_err("ACTION_EMPTY", ["action_empty"])

    if href.strip():
        scheme_check = _check_href_scheme(href)
        if scheme_check is not None:
            return _validation_err(
                "ACTION_HREF_SCHEME_BLOCKED",
                [f"href_scheme_blocked:{scheme_check}"],
            )

    verdict = classify_site_action_candidate(action)
    risk = verdict.get("risk_level", "unknown")

    if risk == "blocked":
        return _validation_err(
            "ACTION_BLOCKED",
            [
                "action_blocked",
                *(f"blocked_token:{t}"
                  for t in verdict.get("matched_blocked_tokens", [])),
            ],
        )
    if risk == "dangerous":
        return _validation_err(
            "ACTION_DANGEROUS", [f"action_dangerous:{verdict.get('reason')}"],
        )
    if risk == "unknown":
        return _validation_err("ACTION_UNKNOWN", ["action_unknown"])
    if risk == "download":
        return {
            "ok": True,
            "error_code": "",
            "warnings": ["approval_required"],
        }
    if risk == "read_only":
        return {"ok": True, "error_code": "", "warnings": []}

    # 알 수 없는 risk 분류 — 안전 차단.
    return _validation_err(
        "ACTION_RISK_UNRECOGNIZED", [f"risk_unrecognized:{risk}"],
    )


# ─── dry-run 실행 ─────────────────────────────────────────────────────────

def execute_controlled_action_dry_run(action: Any) -> dict[str, Any]:
    """dry-run only — 실제 클릭/입력/다운로드를 절대 수행하지 않는다.

    validate_controlled_action 으로 게이트 통과 시 "실행 가능 여부 + 사유"
    만 반환한다. 본 단계에서는 어떤 Playwright API 도 호출하지 않는다.

    출력:
      {
        "executed":              False,             # 항상 False
        "would_execute":         bool,              # 실제 실행 가능 여부
        "ok":                    bool,              # validation 결과
        "error_code":            str,
        "warnings":              [str, ...],
        "risk_level":            str,
        "requires_approval":     bool,
        "matched_blocked_tokens": [str, ...],
        "matched_download_tokens": [str, ...],
        "matched_read_tokens":    [str, ...],
      }
    """
    validation = validate_controlled_action(action)
    if not validation.get("ok"):
        return {
            "executed": False,
            "would_execute": False,
            "ok": False,
            "error_code": validation.get("error_code", ""),
            "warnings": list(validation.get("warnings", [])),
            "risk_level": "blocked",
            "requires_approval": False,
            "matched_blocked_tokens": [],
            "matched_download_tokens": [],
            "matched_read_tokens": [],
        }

    verdict = classify_site_action_candidate(action)
    return {
        "executed": False,
        "would_execute": True,
        "ok": True,
        "error_code": "",
        "warnings": list(validation.get("warnings", [])),
        "risk_level": verdict.get("risk_level", "unknown"),
        "requires_approval": bool(verdict.get("requires_approval")),
        "matched_blocked_tokens": list(
            verdict.get("matched_blocked_tokens", []),
        ),
        "matched_download_tokens": list(
            verdict.get("matched_download_tokens", []),
        ),
        "matched_read_tokens": list(verdict.get("matched_read_tokens", [])),
    }


# ─── 내부 helpers ────────────────────────────────────────────────────────

def _empty_candidate_result(
    *, risk_level: str, reason: str, warnings: list[str],
) -> dict[str, Any]:
    return {
        "allowed": False,
        "risk_level": risk_level,
        "reason": reason,
        "matched_blocked_tokens": [],
        "matched_download_tokens": [],
        "matched_read_tokens": [],
        "requires_approval": False,
        "warnings": list(warnings),
    }


def _empty_plan_result(
    *, site_key: str, page_state: str, warnings: list[str],
) -> dict[str, Any]:
    return {
        "site_key": site_key,
        "page_state": page_state,
        "manual_action_required": False,
        "unrecoverable": False,
        "safe_read_candidates": [],
        "download_candidates": [],
        "blocked_candidates": [],
        "dangerous_candidates": [],
        "warnings": list(warnings),
    }


def _build_candidate_entry(
    *, kind: str, source: dict[str, Any], verdict: dict[str, Any],
) -> dict[str, Any]:
    text = _safe_str(source.get("text"))[:_OUT_TEXT_CAP]
    href_raw = _safe_str(source.get("href") or source.get("action"))
    href = _strip_query_fragment(href_raw)[:_OUT_HREF_CAP]
    matched: list[str] = []
    matched.extend(verdict.get("matched_blocked_tokens", []))
    matched.extend(verdict.get("matched_download_tokens", []))
    matched.extend(verdict.get("matched_read_tokens", []))
    entry: dict[str, Any] = {
        "kind": kind,
        "text": text,
        "href": href,
        "matched_tokens": matched,
        "risk_level": verdict.get("risk_level", "unknown"),
        "requires_approval": bool(verdict.get("requires_approval")),
    }
    # form 인 경우 method / has_password 메타데이터만 부착 (input value 미포함).
    if kind == "form":
        method = _safe_str(source.get("method"))[:10]
        try:
            input_count = int(source.get("input_count") or 0)
        except (TypeError, ValueError):
            input_count = 0
        entry["method"] = method
        entry["has_password"] = bool(source.get("has_password"))
        entry["input_count"] = input_count
    return entry


def _route_entry(
    verdict: dict[str, Any],
    entry: dict[str, Any],
    safe_read: list[dict[str, Any]],
    download: list[dict[str, Any]],
    blocked: list[dict[str, Any]],
    dangerous: list[dict[str, Any]],
) -> None:
    risk = verdict.get("risk_level")
    if risk == "blocked":
        blocked.append(entry)
    elif risk == "dangerous":
        dangerous.append(entry)
    elif risk == "download":
        download.append(entry)
    elif risk == "read_only":
        safe_read.append(entry)
    # unknown 은 어디에도 라우팅하지 않는다 — 명시적 신호 없는 후보 차단.


def _matched_tokens(blob_lower: str, tokens: tuple[str, ...]) -> list[str]:
    if not blob_lower:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for tok in tokens:
        if not tok:
            continue
        if tok.lower() in blob_lower and tok not in seen:
            seen.add(tok)
            out.append(tok)
    return out


def _validation_err(code: str, warnings: list[str]) -> dict[str, Any]:
    return {"ok": False, "error_code": code, "warnings": list(warnings)}


def _check_href_scheme(href: str) -> Optional[str]:
    """위험 scheme 검출. 정상이면 None, 위험하면 scheme 문자열 반환.

    허용: http, https, 빈 문자열 / relative path (/foo, foo, ../foo).
    차단: javascript, data, file, ftp, vbscript 등.
    """
    s = href.strip()
    if not s:
        return None
    if "://" not in s and not s.startswith("javascript:") \
            and not s.startswith("data:") and not s.startswith("file:") \
            and not s.startswith("vbscript:"):
        # relative path — 허용.
        return None
    try:
        parsed = urlparse(s)
    except Exception:  # noqa: BLE001
        return "parse_failed"
    scheme = (parsed.scheme or "").lower()
    if scheme in ("http", "https", ""):
        return None
    return scheme


def _safe_str(value: Any) -> str:
    if isinstance(value, str):
        return value
    return ""


def _strip_query_fragment(href: str) -> str:
    if not isinstance(href, str):
        return ""
    return _QUERY_FRAG_RE.sub("", href.strip())


def _infer_site_key(observer_result: dict[str, Any]) -> str:
    """site_key 미지정 시 final_url_host_path / target_url 에서 host 추정."""
    final_host_path = _safe_str(observer_result.get("final_url_host_path"))
    if final_host_path:
        return final_host_path.split("/", 1)[0][:_OUT_TEXT_CAP]
    target_url = _safe_str(observer_result.get("target_url"))
    if target_url:
        try:
            parsed = urlparse(target_url)
        except Exception:  # noqa: BLE001
            return ""
        return (parsed.hostname or "")[:_OUT_TEXT_CAP]
    return ""


__all__ = [
    "classify_site_action_candidate",
    "build_controlled_action_plan",
    "validate_controlled_action",
    "execute_controlled_action_dry_run",
]
