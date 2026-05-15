"""폼 상태 스캐너 — visible 미결 입력을 전수 수집.

수집 대상:
  - radio group: 그룹 내 어느 것도 체크 안 됨 → 미결
  - 필수 checkbox: required 또는 라벨에 "동의"/"필수" 포함된 미체크
  - text/password: 빈 값 + visible + 필수 추정
  - select: 옵션이 있으나 미선택 또는 placeholder 같은 첫 옵션

반환 구조는 auto_resolver 가 그대로 소비.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from scripts.logger import get_logger

log = get_logger(__name__)


@dataclass
class UnsetItem:
    kind: str             # radio_group | checkbox | text | password | select
    name: str             # name 속성 (라디오 그룹 식별자)
    options: list[dict] = field(default_factory=list)  # radio/select 후보 [{id, value, label}]
    label: str = ""       # 단일 항목 라벨
    selector: str = ""    # CSS selector 권장값
    required: bool = False
    placeholder: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "kind": self.kind, "name": self.name, "label": self.label,
            "options": self.options, "selector": self.selector,
            "required": self.required, "placeholder": self.placeholder,
        }


_SCAN_JS = r"""
() => {
  // 1) radio groups
  const radioGroups = {};
  document.querySelectorAll('input[type=radio]').forEach(el => {
    const r = el.getBoundingClientRect();
    if (!(r.width > 0 && r.height > 0) || el.offsetParent === null) return;
    const grp = el.name || `__anon_${Math.random()}`;
    if (!radioGroups[grp]) radioGroups[grp] = {options: [], any_checked: false};
    let labelText = '';
    if (el.id) {
      const lab = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (lab) labelText = (lab.innerText || '').trim();
    }
    if (!labelText) {
      const parentL = el.closest('label');
      if (parentL) labelText = (parentL.innerText || '').trim();
    }
    radioGroups[grp].options.push({
      id: el.id, value: el.value || '', label: labelText.slice(0, 80),
      checked: el.checked,
    });
    if (el.checked) radioGroups[grp].any_checked = true;
  });
  // 2) checkboxes
  const checkboxes = [];
  document.querySelectorAll('input[type=checkbox]').forEach(el => {
    const r = el.getBoundingClientRect();
    if (!(r.width > 0 && r.height > 0) || el.offsetParent === null) return;
    let labelText = '';
    if (el.id) {
      const lab = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (lab) labelText = (lab.innerText || '').trim();
    }
    if (!labelText) {
      const parentL = el.closest('label');
      if (parentL) labelText = (parentL.innerText || '').trim();
    }
    if (!labelText) {
      // 부모 li/div
      const p = el.closest('li, div, p');
      if (p) labelText = (p.innerText || '').trim().slice(0, 200);
    }
    checkboxes.push({
      id: el.id, name: el.name || '', label: labelText.slice(0, 200),
      checked: el.checked, required: el.required || /필수|required/i.test(labelText),
    });
  });
  // 3) text/password (visible, 빈 값)
  const texts = [];
  document.querySelectorAll('input[type=text], input[type=search], input[type=email], input[type=tel], input[type=password], input:not([type]), textarea').forEach(el => {
    const r = el.getBoundingClientRect();
    if (!(r.width > 0 && r.height > 0) || el.offsetParent === null) return;
    if (el.value) return;  // 이미 값 있음
    let labelText = '';
    if (el.id) {
      const lab = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (lab) labelText = (lab.innerText || '').trim();
    }
    if (!labelText) {
      const parentL = el.closest('label');
      if (parentL) labelText = (parentL.innerText || '').trim();
    }
    texts.push({
      type: el.type || el.tagName.toLowerCase(),
      name: el.name || '', id: el.id || '',
      placeholder: el.placeholder || '',
      label: labelText.slice(0, 80),
      required: el.required || false,
    });
  });
  // 4) select (미선택 또는 placeholder 같은 첫 옵션)
  const selects = [];
  document.querySelectorAll('select').forEach(el => {
    const r = el.getBoundingClientRect();
    if (!(r.width > 0 && r.height > 0) || el.offsetParent === null) return;
    const opts = Array.from(el.options).map(o => ({value: o.value, label: (o.text || '').trim()}));
    let labelText = '';
    if (el.id) {
      const lab = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (lab) labelText = (lab.innerText || '').trim();
    }
    selects.push({
      id: el.id || '', name: el.name || '',
      label: labelText.slice(0, 80),
      selected_value: el.value, selected_idx: el.selectedIndex,
      options: opts.slice(0, 20),
      required: el.required || false,
    });
  });
  return {radio_groups: radioGroups, checkboxes, texts, selects};
}
"""


def scan_state(page) -> list[UnsetItem]:
    """현재 페이지의 visible 미결 입력을 모두 수집."""
    try:
        data = page.evaluate(_SCAN_JS)
    except Exception as e:
        log.warning("[state-scanner] evaluate 실패: %s", e)
        return []

    items: list[UnsetItem] = []

    # 라디오 그룹 — 모든 visible 그룹 (기본값과 다를 수 있어 항상 결정 대상)
    for name, grp in (data.get("radio_groups") or {}).items():
        if not grp.get("options"):
            continue
        items.append(UnsetItem(
            kind="radio_group", name=name,
            options=grp["options"],
            selector=f"input[type=radio][name='{name}']",
            required=True,
            raw={"group": grp, "any_checked": grp.get("any_checked", False)},
        ))

    # 체크박스 — required 만 (마케팅류 자동 체크 안 함)
    for chk in data.get("checkboxes", []) or []:
        if not chk.get("checked") and chk.get("required"):
            sel = f"#{chk['id']}" if chk.get("id") else f"input[name='{chk.get('name','')}']"
            items.append(UnsetItem(
                kind="checkbox", name=chk.get("name", ""),
                label=chk.get("label", ""), selector=sel,
                required=True, raw=chk,
            ))

    # text/password — 빈 값 (모든 visible)
    for t in data.get("texts", []) or []:
        sel = (f"#{t['id']}" if t.get("id") else
               f"input[name='{t['name']}']" if t.get("name") else
               f"input[placeholder='{t.get('placeholder','')}']" if t.get("placeholder") else "")
        items.append(UnsetItem(
            kind=t["type"] if t["type"] in ("password",) else "text",
            name=t.get("name", ""), label=t.get("label", ""),
            placeholder=t.get("placeholder", ""),
            selector=sel, required=bool(t.get("required")),
            raw=t,
        ))

    # select — 첫 옵션이 placeholder("선택하세요")거나 selected_idx=0 + value 비었으면 미결
    for s in data.get("selects", []) or []:
        if (s.get("selected_idx", -1) <= 0 and not s.get("selected_value")):
            sel = f"#{s['id']}" if s.get("id") else f"select[name='{s.get('name','')}']"
            items.append(UnsetItem(
                kind="select", name=s.get("name", ""),
                label=s.get("label", ""),
                options=s.get("options", []),
                selector=sel, required=bool(s.get("required")),
                raw=s,
            ))

    log.info("[state-scanner] 미결 입력 %d개: %s",
             len(items), [i.kind for i in items])
    return items
