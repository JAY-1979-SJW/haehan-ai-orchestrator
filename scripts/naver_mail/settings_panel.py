"""Naver Mail settings/support panel helpers.

This module treats the mail settings area separately from mailbox folders.
It may inspect settings tabs and prepare draft changes, but saving settings is
approval-gated via ``naver_mail_settings_save``.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Any, Protocol

from scripts.gate import check as gate_check


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


def assert_settings_save_allowed(*, force: bool = False, **metadata: Any) -> None:
    gate_check("naver_mail_settings_save", force=force, **metadata)
