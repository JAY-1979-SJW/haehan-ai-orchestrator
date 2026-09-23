"""자동 결정 엔진 — 미결 입력을 어떻게 채울지 결정.

우선순위:
  1. 경로 캐시 (data/login_paths/<host>.json) 의 결정 재사용
  2. 사이트별 프로필 override (form.profile.set_override)
  3. 자격증명 (credentials)
  4. 라벨 키워드 휴리스틱 (유통업체, 약관 동의 등)
  5. 폴백 — RequiresHumanDecision 발생 (호출자가 처리)

결정 결과:
  Resolution(kind, item, action_args)
  - kind: select_radio | check_checkbox | fill_text | choose_select | skip
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from scripts.form.state_scanner import UnsetItem
from scripts.logger import get_logger

log = get_logger(__name__)

ROOT = Path(__file__).resolve().parents[2]
LOGIN_PATHS_DIR = ROOT / "data" / "login_paths"


# 라벨 키워드 → 선호도 (높을수록 우리 선택)
_PREFERRED_KEYWORDS: dict[str, list[str]] = {
    # 우리는 유통업체 (EUM)
    "ko_distributor": ["유통업체", "distributor"],
    # 약관 (필수)
    "agree_required": ["이용약관", "개인정보", "동의", "필수", "agree"],
    # 약관 (마케팅 — 자동 체크 X)
    "marketing": ["마케팅", "광고", "이벤트", "promotion"],
}


_HEURISTIC_FIELD_KEYWORDS: dict[str, list[str]] = {
    "id": ["아이디", "userid", "user_id", "loginid", "username"],
    "email": ["이메일", "email", "메일주소"],
    "password": ["비밀번호", "password", "패스워드"],
    "phone": ["휴대폰", "전화", "phone", "tel"],
}


class RequiresHumanDecision(RuntimeError):
    """결정 못함 — 사용자 입력 필요."""

    def __init__(self, host: str, items: list[UnsetItem], hint: str = ""):
        self.host = host
        self.items = items
        self.hint = hint
        msg = f"휴먼 결정 필요 ({host}): {len(items)} 미결\n"
        for it in items:
            if it.kind == "radio_group":
                opts = " | ".join(f"{o.get('label', '?')}({o.get('id', '')})" for o in it.options)
                msg += f"  [라디오 {it.name}] {opts}\n"
            elif it.kind == "select":
                opts = " | ".join(o.get("label", "?") for o in it.options[:8])
                msg += f"  [select {it.name}] {opts}\n"
            else:
                msg += f"  [{it.kind} {it.name or it.label or it.placeholder}]\n"
        if hint:
            msg += f"\n  힌트: {hint}"
        super().__init__(msg)


@dataclass
class Resolution:
    kind: str  # select_radio | check_checkbox | fill_text | choose_select | skip
    item: UnsetItem
    selector: str = ""
    value: str = ""
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "selector": self.selector,
            "value": ("***" if "password" in self.item.kind else self.value),
            "note": self.note,
        }


# ── 캐시 / 프로필 로드 ─────────────────────────────────────────────


def _load_path_cache(host: str) -> dict:
    fp = LOGIN_PATHS_DIR / f"{host}.json"
    if not fp.exists():
        return {}
    try:
        return json.loads(fp.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _profile_get(field: str, site: str) -> str:
    try:
        from scripts.form.profile import get_value

        return get_value(field, site=site)
    except Exception:
        return ""


def _cred_get(site: str) -> dict:
    try:
        from scripts.credentials import get_cred

        return get_cred(site)
    except Exception:
        return {}


# ── 항목별 결정 ─────────────────────────────────────────────────


def _currently_checked(item: UnsetItem) -> dict | None:
    for o in item.options:
        if o.get("checked"):
            return o
    return None


def _resolve_radio(item: UnsetItem, host: str, site_key: str, cache: dict) -> Resolution | None:
    current = _currently_checked(item)

    def _maybe_skip(preferred_label: str) -> Resolution | None:
        if current and (current.get("label") == preferred_label or current.get("id") == preferred_label):
            return Resolution(kind="skip", item=item, note=f"already_checked:{preferred_label}")
        return None

    # 1) 캐시
    cached = (cache.get("radio_choices") or {}).get(item.name)
    if cached:
        skip = _maybe_skip(cached)
        if skip:
            return skip
        for opt in item.options:
            if opt.get("label") == cached or opt.get("id") == cached:
                sel = f"#{opt.get('id')}" if opt.get("id") else f"input[name='{item.name}'][value='{opt.get('value')}']"
                return Resolution(
                    kind="select_radio", item=item, selector=sel, value=opt.get("label", ""), note=f"cache:{cached}"
                )
    # 2) 프로필 override
    prof_val = _profile_get(f"radio_{item.name}", site_key)
    if prof_val:
        skip = _maybe_skip(prof_val)
        if skip:
            return skip
        for opt in item.options:
            if opt.get("label") == prof_val:
                sel = f"#{opt.get('id')}" if opt.get("id") else f"input[name='{item.name}'][value='{opt.get('value')}']"
                return Resolution(
                    kind="select_radio", item=item, selector=sel, value=prof_val, note=f"profile:{prof_val}"
                )
    # 3) 휴리스틱 — 유통업체 우선
    for opt in item.options:
        lab = (opt.get("label") or "").lower()
        for kw in _PREFERRED_KEYWORDS["ko_distributor"]:
            if kw.lower() in lab:
                if current and current.get("id") == opt.get("id"):
                    return Resolution(kind="skip", item=item, note=f"already:distributor:{opt.get('label')}")
                sel = f"#{opt.get('id')}" if opt.get("id") else f"input[name='{item.name}'][value='{opt.get('value')}']"
                return Resolution(
                    kind="select_radio",
                    item=item,
                    selector=sel,
                    value=opt.get("label", ""),
                    note="heuristic:distributor",
                )
    return None


def _resolve_checkbox(item: UnsetItem, host: str, site_key: str) -> Resolution | None:
    lab = (item.label or "").lower()
    # 마케팅류 — 체크 안 함 (skip)
    if any(kw in lab for kw in _PREFERRED_KEYWORDS["marketing"]):
        return Resolution(kind="skip", item=item, note="marketing_no_consent")
    # 필수 동의 — 체크
    if any(kw in lab for kw in _PREFERRED_KEYWORDS["agree_required"]):
        return Resolution(kind="check_checkbox", item=item, selector=item.selector, note="agree_required")
    if item.required:
        return Resolution(kind="check_checkbox", item=item, selector=item.selector, note="required_flag")
    return None


def _resolve_text(item: UnsetItem, host: str, site_key: str) -> Resolution | None:
    cred = _cred_get(site_key)
    # 비밀번호
    if item.kind == "password":
        if cred.get("pw"):
            return Resolution(kind="fill_text", item=item, selector=item.selector, value=cred["pw"], note="cred.pw")
        return None
    # 매칭 키워드 → 적절한 값
    text_sources = " ".join([item.label or "", item.placeholder or "", item.name or "", item.raw.get("id", "")]).lower()
    for role, kws in _HEURISTIC_FIELD_KEYWORDS.items():
        if any(kw in text_sources for kw in kws):
            if role == "id" and cred.get("id"):
                return Resolution(kind="fill_text", item=item, selector=item.selector, value=cred["id"], note="cred.id")
            val = _profile_get(role, site_key) or _profile_get("default_" + role, site_key)
            if val:
                return Resolution(
                    kind="fill_text", item=item, selector=item.selector, value=val, note=f"profile.{role}"
                )
    return None


def _resolve_select(item: UnsetItem, host: str, site_key: str, cache: dict) -> Resolution | None:
    cached = (cache.get("select_choices") or {}).get(item.name)
    if cached:
        return Resolution(kind="choose_select", item=item, selector=item.selector, value=cached, note=f"cache:{cached}")
    # 휴리스틱 — 라벨에 유통업체
    for opt in item.options:
        for kw in _PREFERRED_KEYWORDS["ko_distributor"]:
            if kw in (opt.get("label") or "").lower():
                return Resolution(
                    kind="choose_select",
                    item=item,
                    selector=item.selector,
                    value=opt.get("value", ""),
                    note=f"heuristic:{opt.get('label')}",
                )
    return None


# ── 공개 API ───────────────────────────────────────────────────


def resolve_state(
    items: list[UnsetItem],
    *,
    host: str = "",
    site_key: str = "",
) -> tuple[list[Resolution], list[UnsetItem]]:
    """미결 항목 → (결정된 것, 결정 못한 것).

    site_key: credentials/profile 조회용 (eum, naver 등)
    host: 캐시 파일 키
    """
    cache = _load_path_cache(host) if host else {}
    resolved: list[Resolution] = []
    unresolved: list[UnsetItem] = []

    for it in items:
        r: Resolution | None = None
        if it.kind == "radio_group":
            r = _resolve_radio(it, host, site_key, cache)
        elif it.kind == "checkbox":
            r = _resolve_checkbox(it, host, site_key)
        elif it.kind in ("text", "password"):
            r = _resolve_text(it, host, site_key)
        elif it.kind == "select":
            r = _resolve_select(it, host, site_key, cache)

        if r:
            resolved.append(r)
        else:
            unresolved.append(it)

    log.info("[auto-resolver] 결정 %d / 미결 %d", len(resolved), len(unresolved))
    return resolved, unresolved


def assert_all_resolved(
    items: list[UnsetItem],
    *,
    host: str = "",
    site_key: str = "",
) -> list[Resolution]:
    """결정 못한 항목 있으면 RequiresHumanDecision 발생."""
    resolved, unresolved = resolve_state(items, host=host, site_key=site_key)
    if unresolved:
        raise RequiresHumanDecision(host, unresolved, hint=f"profile.set_override({site_key}, ...) 로 결정 저장")
    return resolved
