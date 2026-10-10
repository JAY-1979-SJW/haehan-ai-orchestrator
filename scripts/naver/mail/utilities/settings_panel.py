"""Naver Mail settings/support panel helpers.

This module treats the mail settings area separately from mailbox folders.
It may inspect settings tabs and prepare draft changes, but saving settings is
approval-gated via ``naver_mail_settings_save``.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Any, Protocol

from scripts.common.gate import check as gate_check


SETTINGS_MENU_NAMES = frozenset({
    "환경설정",
    "외부메일 가져오기",
    "메일용량",
    "고객센터",
})

BLOCKED_MENU_NAMES = frozenset({
    "로그아웃",
})


class _Actions(Protocol):
    def evaluate(self, expr: str) -> Any: ...
    def wait_dom(self, expr_truthy: str, timeout_s: float = 8.0) -> bool: ...


@dataclass
class SettingsMenuItem:
    name: str
    href: str = ""
    support: bool = True
    action: str = "inspect"
    blocked: bool = False
    reason: str = ""


@dataclass
class SettingsPanel:
    url: str = ""
    title: str = ""
    tabs: list[str] = field(default_factory=list)
    buttons: list[str] = field(default_factory=list)
    inputs_count: int = 0
    checkboxes_count: int = 0
    save_controls: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SettingsField:
    label: str
    kind: str
    name: str = ""
    value_present: bool = False
    required: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SettingsActionPlan:
    action: str
    menu_name: str
    mode: str = "prepare"
    fields: dict[str, Any] = field(default_factory=dict)
    steps: list[str] = field(default_factory=list)
    approval_gate: str = "naver_mail_settings_save"
    approval_required: bool = True
    final_submit_blocked: bool = True
    safe_to_prepare: bool = True
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


MENU_EXPR = r"""
JSON.stringify((function(){
  const rows = Array.from(document.querySelectorAll('.lnb .mailbox_item.support, .lnb .mailbox_item'));
  const out = [];
  for (const row of rows) {
    const label = row.querySelector('.mailbox_label, a, button');
    if (!label) continue;
    const name = (label.innerText || label.textContent || '').trim().replace(/\s+/g, ' ');
    if (!name) continue;
    out.push({
      name,
      href: label.getAttribute('href') || '',
      support: /\bsupport\b/.test(row.className || ''),
    });
  }
  return out;
})())
"""


def _click_menu_expr(name: str) -> str:
    safe = name.replace("\\", "\\\\").replace("'", "\\'")
    return (
        "(function(){"
        "const rows=Array.from(document.querySelectorAll('.lnb .mailbox_item.support, .lnb .mailbox_item'));"
        "for(const row of rows){"
        "const label=row.querySelector('.mailbox_label, a, button');"
        "if(!label) continue;"
        "const text=(label.innerText||label.textContent||'').trim().replace(/\\s+/g,' ');"
        f"if(text==='{safe}'){{label.click(); return true;}}"
        "}"
        "return false;"
        "})()"
    )


PANEL_EXPR = r"""
JSON.stringify((function(){
  const root = document.querySelector('[class*="setting"], [class*="option"], main, #content') || document.body;
  const textOf = (el) => (el.innerText || el.textContent || '').trim().replace(/\s+/g, ' ');
  const tabs = Array.from(root.querySelectorAll('[role="tab"], .tab a, .tabs a, a[class*="tab"], button[class*="tab"]'))
    .map(textOf).filter(Boolean).slice(0, 40);
  const buttons = Array.from(root.querySelectorAll('button, input[type="button"], input[type="submit"]'))
    .map(el => textOf(el) || el.value || el.getAttribute('aria-label') || '')
    .map(s => String(s).trim()).filter(Boolean).slice(0, 80);
  const saveControls = buttons.filter(t => /저장|확인|적용|변경|등록/.test(t));
  return {
    url: location.href,
    title: document.title,
    tabs,
    buttons,
    inputs_count: root.querySelectorAll('input, textarea, select').length,
    checkboxes_count: root.querySelectorAll('input[type="checkbox"], input[type="radio"]').length,
    save_controls: saveControls,
  };
})())
"""


DETAIL_EXPR = r"""
JSON.stringify((function(){
  const root = document.querySelector('[class*="setting"], [class*="option"], main, #content') || document.body;
  const textOf = (el) => (el.innerText || el.textContent || '').trim().replace(/\s+/g, ' ');
  const fields = Array.from(root.querySelectorAll('input, textarea, select')).map((el) => {
    const id = el.getAttribute('id') || '';
    const name = el.getAttribute('name') || '';
    let label = '';
    if (id) {
      const labelEl = root.querySelector('label[for="' + CSS.escape(id) + '"]');
      if (labelEl) label = textOf(labelEl);
    }
    if (!label) {
      const wrap = el.closest('label, .row, .field, tr, li, [class*="field"], [class*="row"]');
      if (wrap) label = textOf(wrap).slice(0, 120);
    }
    return {
      label,
      kind: (el.tagName || '').toLowerCase() + (el.type ? ':' + el.type : ''),
      name,
      value_present: !!(el.value || el.checked),
      required: !!el.required,
    };
  }).slice(0, 100);
  const links = Array.from(root.querySelectorAll('a, button'))
    .map((el) => textOf(el) || el.getAttribute('aria-label') || el.getAttribute('title') || '')
    .map((s) => String(s).trim()).filter(Boolean).slice(0, 120);
  return {
    url: location.href,
    title: document.title,
    text_sample: textOf(root).slice(0, 2000),
    fields,
    links,
  };
})())
"""


def list_settings_menus(actions: _Actions) -> list[SettingsMenuItem]:
    raw = actions.evaluate(MENU_EXPR) or []
    out: list[SettingsMenuItem] = []
    for row in raw if isinstance(raw, list) else []:
        name = str(row.get("name") or "").strip()
        if name not in SETTINGS_MENU_NAMES and name not in BLOCKED_MENU_NAMES:
            continue
        blocked = name in BLOCKED_MENU_NAMES
        out.append(SettingsMenuItem(
            name=name,
            href=str(row.get("href") or ""),
            support=bool(row.get("support", True)),
            action="blocked" if blocked else "inspect",
            blocked=blocked,
            reason="session_end_action" if blocked else "",
        ))
    return out


def open_settings_panel(actions: _Actions, name: str = "환경설정") -> SettingsPanel:
    if name in BLOCKED_MENU_NAMES:
        raise ValueError(f"BLOCKED_SETTINGS_MENU: {name}")
    if name not in SETTINGS_MENU_NAMES:
        raise ValueError(f"UNKNOWN_SETTINGS_MENU: {name}")
    clicked = actions.evaluate(_click_menu_expr(name))
    if not clicked:
        raise RuntimeError(f"SETTINGS_MENU_NOT_FOUND: {name}")
    actions.wait_dom("document.body && document.body.innerText.length > 20", timeout_s=8.0)
    payload = actions.evaluate(PANEL_EXPR) or {}
    return SettingsPanel(
        url=str(payload.get("url") or ""),
        title=str(payload.get("title") or ""),
        tabs=list(payload.get("tabs") or []),
        buttons=list(payload.get("buttons") or []),
        inputs_count=int(payload.get("inputs_count") or 0),
        checkboxes_count=int(payload.get("checkboxes_count") or 0),
        save_controls=list(payload.get("save_controls") or []),
    )


def inspect_settings_detail(actions: _Actions, name: str = "환경설정") -> dict[str, Any]:
    """Open a settings/support menu and return a read-only control inventory."""
    panel = open_settings_panel(actions, name)
    payload = actions.evaluate(DETAIL_EXPR) or {}
    raw_fields = payload.get("fields") if isinstance(payload, dict) else []
    fields = [
        SettingsField(
            label=str(row.get("label") or ""),
            kind=str(row.get("kind") or ""),
            name=str(row.get("name") or ""),
            value_present=bool(row.get("value_present")),
            required=bool(row.get("required")),
        ).to_dict()
        for row in (raw_fields if isinstance(raw_fields, list) else [])
        if isinstance(row, dict)
    ]
    return {
        "menu_name": name,
        "panel": panel.to_dict(),
        "url": str(payload.get("url") or "") if isinstance(payload, dict) else "",
        "title": str(payload.get("title") or "") if isinstance(payload, dict) else "",
        "text_sample": str(payload.get("text_sample") or "") if isinstance(payload, dict) else "",
        "fields": fields,
        "links": list(payload.get("links") or []) if isinstance(payload, dict) else [],
    }


def build_settings_action_plan(action: str, menu_name: str, **fields: Any) -> SettingsActionPlan:
    clean = {k: v for k, v in fields.items() if v not in (None, "")}
    steps = [
        f"open menu: {menu_name}",
        f"prepare fields for: {action}",
        "stop before save/apply/register/delete",
        "require explicit approval for final settings change",
    ]
    warnings: list[str] = []
    if action in {"external_mail_add", "external_mail_update"}:
        warnings.append("external mail credentials must be entered by the user or a secure local secret path; never store raw password")
    if action in {"external_mail_delete", "mailbox_cleanup"}:
        warnings.append("destructive settings operation; approval required before final action")
    return SettingsActionPlan(
        action=action,
        menu_name=menu_name,
        fields=clean,
        steps=steps,
        warnings=warnings,
    )


def prepare_external_mail_import(
    *,
    provider: str = "",
    email_address: str = "",
    server_type: str = "pop3",
    server_host: str = "",
    port: int | None = None,
    use_ssl: bool = True,
) -> SettingsActionPlan:
    return build_settings_action_plan(
        "external_mail_add",
        "외부메일 가져오기",
        provider=provider,
        email_address=email_address,
        server_type=server_type,
        server_host=server_host,
        port=port,
        use_ssl=use_ssl,
    )


def prepare_external_mail_update(
    *,
    account_hint: str,
    server_host: str = "",
    port: int | None = None,
    use_ssl: bool | None = None,
) -> SettingsActionPlan:
    return build_settings_action_plan(
        "external_mail_update",
        "외부메일 가져오기",
        account_hint=account_hint,
        server_host=server_host,
        port=port,
        use_ssl=use_ssl,
    )


def prepare_external_mail_delete(*, account_hint: str) -> SettingsActionPlan:
    return build_settings_action_plan(
        "external_mail_delete",
        "외부메일 가져오기",
        account_hint=account_hint,
    )


def prepare_signature_update(*, signature_name: str, body_preview: str) -> SettingsActionPlan:
    return build_settings_action_plan(
        "signature_update",
        "환경설정",
        signature_name=signature_name,
        body_preview=body_preview[:500],
    )


def prepare_quick_reply_update(*, template_name: str, body_preview: str) -> SettingsActionPlan:
    return build_settings_action_plan(
        "quick_reply_update",
        "환경설정",
        template_name=template_name,
        body_preview=body_preview[:500],
    )


def prepare_auto_classification_rule(
    *,
    rule_name: str,
    sender_contains: str = "",
    subject_contains: str = "",
    target_folder: str = "",
) -> SettingsActionPlan:
    return build_settings_action_plan(
        "auto_classification_rule",
        "환경설정",
        rule_name=rule_name,
        sender_contains=sender_contains,
        subject_contains=subject_contains,
        target_folder=target_folder,
    )


def prepare_forwarding_rule(
    *,
    forwarding_address: str,
    keep_original: bool = True,
) -> SettingsActionPlan:
    return build_settings_action_plan(
        "forwarding_rule",
        "환경설정",
        forwarding_address=forwarding_address,
        keep_original=keep_original,
    )


def prepare_vacation_reply(
    *,
    enabled: bool,
    subject: str = "",
    body_preview: str = "",
) -> SettingsActionPlan:
    return build_settings_action_plan(
        "vacation_reply",
        "환경설정",
        enabled=enabled,
        subject=subject,
        body_preview=body_preview[:500],
    )


def prepare_spam_policy_update(
    *,
    blocked_sender: str = "",
    blocked_domain: str = "",
    allow_sender: str = "",
) -> SettingsActionPlan:
    return build_settings_action_plan(
        "spam_policy_update",
        "환경설정",
        blocked_sender=blocked_sender,
        blocked_domain=blocked_domain,
        allow_sender=allow_sender,
    )


def prepare_mailbox_management(
    *,
    folder_name: str,
    operation: str = "create_or_rename",
    new_name: str = "",
) -> SettingsActionPlan:
    return build_settings_action_plan(
        "mailbox_management",
        "환경설정",
        folder_name=folder_name,
        operation=operation,
        new_name=new_name,
    )


def prepare_capacity_cleanup(*, target: str = "trash", delete_scope: str = "review_only") -> SettingsActionPlan:
    return build_settings_action_plan(
        "mailbox_cleanup",
        "메일용량",
        target=target,
        delete_scope=delete_scope,
    )


def execute_settings_action_plan(plan: SettingsActionPlan, *, force: bool = False) -> dict[str, Any]:
    """Validate approval for the final settings mutation.

    The actual click/save is intentionally not implemented here; callers must
    perform the site-specific final action only after this gate passes.
    """
    assert_settings_save_allowed(force=force, action=plan.action, menu_name=plan.menu_name)
    data = plan.to_dict()
    data["final_submit_blocked"] = False
    data["approval_granted"] = True
    return data


def assert_settings_save_allowed(*, force: bool = False, **metadata: Any) -> None:
    gate_check("naver_mail_settings_save", force=force, **metadata)
