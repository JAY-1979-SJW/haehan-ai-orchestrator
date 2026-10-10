"""Approval-gated Naver Cafe join request preparation.

This module models the cafe join flow separately from read-only article
collection. It may inspect the visible join surface through an existing CDP
target, but final membership submission is always approval-gated.
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any

from scripts.common.gate import check as gate_check
from scripts.naver.cafe import list_collector
from scripts.naver.cafe.member_collect import normalize_cafe_url
from scripts.naver.mail.read import cdp

APPROVAL_CONFIRM_TEXT = "NAVER_APPROVED_CAFE_JOIN"


@dataclass
class CafeJoinField:
    name: str
    label: str = ""
    kind: str = ""
    required: bool = False
    value: str = ""
    placeholder: str = ""
    options: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CafeJoinRequestReport:
    ok: bool
    code: str = "ok"
    cafe_url: str = ""
    href: str = ""
    title: str = ""
    joined_or_blocked: bool = False
    join_available: bool = False
    final_submit_blocked: bool = True
    approval_required: bool = True
    approval_gate: str = "naver_cafe_join_submit"
    nickname: str = ""
    purpose: str = ""
    fields: list[dict[str, Any]] = field(default_factory=list)
    buttons: list[dict[str, Any]] = field(default_factory=list)
    body_sample: str = ""
    messages: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _join_extract_expression() -> str:
    return r"""
JSON.stringify((function(){
  function clean(s){return String(s||'').replace(/\s+/g,' ').trim();}
  var frame = document.getElementById('cafe_main');
  var d = frame && frame.contentDocument ? frame.contentDocument : document;
  function labelFor(el){
    if (!el) return '';
    if (el.id) {
      var direct = d.querySelector('label[for="' + el.id.replace(/"/g, '\\"') + '"]');
      if (direct) return clean(direct.innerText);
    }
    var wrap = el.closest('label,tr,li,div');
    return clean(wrap && wrap.innerText || '').slice(0, 160);
  }
  var fields = Array.prototype.slice.call(d.querySelectorAll('input, textarea, select')).map(function(el){
    var options = el.tagName === 'SELECT'
      ? Array.prototype.slice.call(el.options || []).map(function(o){return clean(o.innerText || o.value);}).filter(Boolean).slice(0, 30)
      : [];
    return {
      name: String(el.name || el.id || ''),
      label: labelFor(el),
      kind: String(el.type || el.tagName || '').toLowerCase(),
      required: !!el.required || /필수|required/i.test(labelFor(el)),
      value: String(el.value || ''),
      placeholder: String(el.placeholder || ''),
      options: options
    };
  }).filter(function(x){return x.name || x.label || x.placeholder;}).slice(0, 80);
  var buttons = Array.prototype.slice.call(d.querySelectorAll('button,a,input[type=button],input[type=submit]')).map(function(el){
    return {
      text: clean(el.innerText || el.value || el.title || ''),
      href: String(el.href || el.getAttribute('href') || ''),
      disabled: !!el.disabled || el.getAttribute('aria-disabled') === 'true'
    };
  }).filter(function(x){return x.text || x.href;}).slice(0, 120);
  var body = clean(d.body && d.body.innerText || document.body && document.body.innerText || '');
  var joinAvailable = buttons.some(function(b){return /가입|신청|동의|확인/.test(b.text);}) || /가입하기|카페 가입|가입 신청/.test(body);
  var joinedOrBlocked = /이미 가입|가입한 카페|가입 승인 대기|활동정지|접근 제한|차단/.test(body);
  return {
    href: location.href,
    title: document.title,
    fields: fields,
    buttons: buttons,
    joinAvailable: joinAvailable,
    joinedOrBlocked: joinedOrBlocked,
    body: body.slice(0, 5000)
  };
})())
""".strip()


def _field_value(name: str, fields: dict[str, str]) -> str:
    return str(fields.get(name, "") or "").strip()


def build_join_plan(
    *,
    cafe_url: str,
    nickname: str = "",
    purpose: str = "",
    answers: dict[str, str] | None = None,
    raw: dict[str, Any] | None = None,
) -> CafeJoinRequestReport:
    cafe_url = normalize_cafe_url(cafe_url)
    answers = answers or {}
    extracted_fields = []
    for item in (raw or {}).get("fields", []):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "")
        extracted_fields.append(
            CafeJoinField(
                name=name,
                label=str(item.get("label") or ""),
                kind=str(item.get("kind") or ""),
                required=bool(item.get("required")),
                value=_field_value(name, answers),
                placeholder=str(item.get("placeholder") or ""),
                options=[str(opt) for opt in item.get("options", []) if str(opt)],
            ).to_dict()
        )

    messages = [
        "Prepared Naver Cafe join request as an approval-gated workflow.",
        "Final join/submit click is blocked unless explicit approval and confirmation text are provided.",
    ]
    if not nickname:
        messages.append("Nickname is empty; operator input is required before a real join submit.")
    if not purpose:
        messages.append("Purpose is empty; operator input may be required for cafes with join questions.")

    return CafeJoinRequestReport(
        ok=True,
        cafe_url=cafe_url,
        href=str((raw or {}).get("href") or f"https://cafe.naver.com/{cafe_url}"),
        title=str((raw or {}).get("title") or ""),
        joined_or_blocked=bool((raw or {}).get("joinedOrBlocked")),
        join_available=bool((raw or {}).get("joinAvailable")),
        nickname=nickname,
        purpose=purpose,
        fields=extracted_fields,
        buttons=[item for item in (raw or {}).get("buttons", []) if isinstance(item, dict)],
        body_sample=str((raw or {}).get("body") or ""),
        messages=messages,
    )


def inspect_join_request_from_target(  # noqa: PLR0913 - 공개 시그니처 유지(동작 변경 금지 리팩터링)
    target_id: str,
    *,
    port: int,
    cafe_url: str,
    nickname: str = "",
    purpose: str = "",
    answers: dict[str, str] | None = None,
    wait_s: float = 2.5,
) -> CafeJoinRequestReport:
    gate_check("scan_page", context="naver_cafe_join_request_inspect")
    cafe_url = normalize_cafe_url(cafe_url)
    cdp.navigate(target_id, f"https://cafe.naver.com/{cafe_url}", port=port)
    time.sleep(max(0.0, wait_s))
    raw = list_collector.evaluate_async(target_id, _join_extract_expression(), port=port, timeout=20.0)
    if isinstance(raw, str):
        raw = __import__("json").loads(raw)
    if not isinstance(raw, dict):
        return CafeJoinRequestReport(ok=False, code="invalid_join_extract_result", cafe_url=cafe_url)
    return build_join_plan(cafe_url=cafe_url, nickname=nickname, purpose=purpose, answers=answers, raw=raw)


def approve_join_submit(
    plan: CafeJoinRequestReport,
    *,
    approved: bool = False,
    confirm: str = "",
    approved_by: str = "operator",
) -> CafeJoinRequestReport:
    force = approved and confirm == APPROVAL_CONFIRM_TEXT
    gate_check(
        "naver_cafe_join_submit",
        risk="approve",
        force=force,
        service="naver_cafe",
        cafe_url=plan.cafe_url,
        approved_by=approved_by,
    )
    out = CafeJoinRequestReport(**plan.to_dict())
    out.messages = [
        *plan.messages,
        "Join submit gate passed. Browser final-click adapter must re-check the visible form immediately before submitting.",
    ]
    out.final_submit_blocked = False
    return out
