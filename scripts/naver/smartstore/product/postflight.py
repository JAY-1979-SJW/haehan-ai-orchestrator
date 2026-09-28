"""저장 직전 폼 전수 점검 — '빠뜨린 것' 을 사람 기억이 아니라 코드가 확인한다.

배경 (2026-08-15). 하루에 같은 오판을 네 번 했다:
    검색태그 / 옵션 / 배송비 / 예약구매
    전부 **접히거나 숨겨진 것을 '없다'고 판단**한 경우였고,
    앞의 셋은 실제로는 이미 설정돼 있었다.

    특히 예약구매는 반대 방향의 사고였다. vm.isPreOrderOn 이 켜져 있는 것을
    아무도 몰랐다. 그대로 저장했다면 일반 판매가 아니라 **예약구매 상품**으로
    등록됐을 것이다. 화면을 안 보고 넘어가면 이런 것이 조용히 지나간다.

그래서 순서를 강제한다:
    (1) 모든 섹션을 펼친다  — 접힌 섹션의 입력요소는 DOM 에 아예 없다
    (2) 그 다음에 읽는다     — ng-invalid-required 로 '필수인데 빈' 항목을 뽑는다
    (3) 위험 설정을 따로 본다 — 조용히 상품 성격을 바꾸는 값들

주의: 이 모듈은 읽기 위주지만 (1) 은 화면 상태를 바꾼다(펼치기).
      값 자체는 바꾸지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# 토글은 <a> 와 <button> 양쪽에 있고 '메뉴토글' / '메뉴 토글' 로 표기가 갈린다.
# 기존 구현이 <a> + 공백 없는 표기만 봐서 배송 섹션을 못 펼쳤고,
# 그 탓에 이미 설정된 배송비 3,000원을 '미설정'으로 오판했다(2026-08-15 실측).
_EXPAND_JS = r"""
() => {
  const tg = [...document.querySelectorAll('a,button')]
      .filter(e => /메뉴\s*토글/.test(e.innerText || ''));
  let n = 0;
  tg.forEach(e => {
    if (!/active/.test(e.className || '')) {
      try { e.click(); n++; } catch (err) {}
    }
  });
  return {clicked: n, total: tg.length};
}
"""

# 섹션 구조(실측): .form-section > .title-line > .input-content > .set-option(토글)
# 제목은 h3 가 아니라 .title-line 안의 label 이다. h3 로 찾으면 19개 중 2개만 잡힌다.
_SECTIONS_JS = r"""
() => {
  const clean = s => (s || '').trim().replace(/\s+/g, ' ');
  const vis = e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const out = [];
  for (const sec of document.querySelectorAll('.form-section')) {
    const tl = sec.querySelector(':scope > .title-line');
    if (!tl) continue;
    const lab = tl.querySelector('label, .control-label, h3, strong');
    const title = clean(lab ? lab.innerText : tl.innerText).slice(0, 24);
    if (!title) continue;
    const fields = [...sec.querySelectorAll('input,select,textarea')]
        .filter(e => e.type !== 'hidden');
    const filled = fields.filter(e =>
      (e.type === 'radio' || e.type === 'checkbox')
        ? e.checked : String(e.value ?? '').trim() !== '');
    const bad = fields.filter(e => /ng-invalid-required/.test(e.className || ''));
    const sum = sec.querySelector('.set-option .text');
    out.push({
      title,
      visible: vis(sec),
      fields: fields.length,
      filled: filled.length,
      invalid_required: bad.length,
      summary: sum ? clean(sum.innerText).slice(0, 70) : '',
    });
  }
  return out;
}
"""

_MISSING_JS = r"""
() => {
  const clean = s => (s || '').trim().replace(/\s+/g, ' ');
  const vis = e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const sectionOf = e => {
    let n = e;
    for (let i = 0; i < 12 && n.parentElement; i++) {
      n = n.parentElement;
      if (/form-section/.test(n.className || '')) {
        const t = n.querySelector(':scope > .title-line label, :scope > .title-line');
        return clean(t ? t.innerText : '').slice(0, 22);
      }
    }
    return '';
  };
  const labelOf = e => {
    let n = e;
    for (let i = 0; i < 6 && n.parentElement; i++) {
      n = n.parentElement;
      const l = n.querySelector(':scope > label, :scope > .control-label');
      if (l && clean(l.innerText)) return clean(l.innerText).slice(0, 50);
    }
    return '';
  };
  return [...document.querySelectorAll('.ng-invalid-required')]
    .filter(e => ['INPUT', 'SELECT', 'TEXTAREA'].includes(e.tagName))
    .map(e => ({
      ng: (e.getAttribute('ng-model') || '').slice(0, 60),
      label: labelOf(e),
      section: sectionOf(e),
      visible: vis(e),
      disabled: !!e.disabled,
    }));
}
"""

# 조용히 상품 성격을 바꾸는 설정들.
# 실측: vm.isPreOrderOn 이 켜진 줄 모르고 저장할 뻔했다 — 예약구매 상품이 될 뻔했다.
_RISKY_JS = r"""
() => {
  const pick = (ng) => [...document.querySelectorAll(`input[ng-model="${ng}"]`)]
      .filter(e => e.type === 'radio')
      .map(e => ({value: e.value, checked: e.checked}));
  return {
    preOrder: pick('vm.isPreOrderOn'),
  };
}
"""


@dataclass
class SectionState:
    title: str
    fields: int
    filled: int
    invalid_required: int
    summary: str = ""
    visible: bool = True


@dataclass
class MissingField:
    ng: str
    label: str
    section: str
    visible: bool
    disabled: bool

    @property
    def actionable(self) -> bool:
        """화면에 보이고 활성인 것만 사람이 실제로 채울 수 있다.

        숨김/비활성 항목도 ng-invalid-required 로 잡히지만, 그 섹션을 쓰지 않으면
        저장 검증에서 빠지는 경우가 많다. 구분해서 보여줘야 목록이 신뢰를 잃지 않는다.
        """
        return self.visible and not self.disabled

    def to_dict(self) -> dict:
        return {
            "ng": self.ng,
            "label": self.label,
            "section": self.section,
            "visible": self.visible,
            "disabled": self.disabled,
            "actionable": self.actionable,
        }


@dataclass
class PostflightReport:
    sections: list[SectionState] = field(default_factory=list)
    missing: list[MissingField] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    expanded: int = 0

    @property
    def actionable_missing(self) -> list[MissingField]:
        return [m for m in self.missing if m.actionable]

    @property
    def ready(self) -> bool:
        """채울 수 있는 필수 항목이 남아 있지 않고, 위험 설정 경고도 없는 상태."""
        return not self.actionable_missing and not self.warnings

    def summary(self) -> str:
        parts = [f"섹션 {len(self.sections)}개"]
        if self.missing:
            parts.append(f"필수미입력 {len(self.missing)}건(조치가능 {len(self.actionable_missing)})")
        if self.warnings:
            parts.append(f"경고 {len(self.warnings)}건")
        return " / ".join(parts) if len(parts) > 1 else parts[0] + " — 이상 없음"

    def to_dict(self) -> dict:
        return {
            "sections": [s.__dict__ for s in self.sections],
            "missing": [m.to_dict() for m in self.missing],
            "warnings": list(self.warnings),
            "ready": self.ready,
        }


def expand_all_sections(page: Any, *, max_rounds: int = 4, settle_ms: int = 2200) -> int:
    """접힌 섹션을 모두 펼친다. 읽기 전에 반드시 먼저 호출한다."""
    total = 0
    for _ in range(max_rounds):
        try:
            r = page.evaluate(_EXPAND_JS)
        except Exception:  # noqa: BLE001 - 상품등록 후 화면 검증(섹션/누락필드/위험옵션 읽기전용) - 실패 시 빈 목록 반환
            break
        n = (r or {}).get("clicked", 0)
        total += n
        try:
            page.wait_for_timeout(settle_ms)
        except Exception:  # noqa: BLE001 - 상품등록 후 화면 검증(섹션/누락필드/위험옵션 읽기전용) - 실패 시 빈 목록 반환
            pass
        if not n:
            break
    return total


def read_sections(page: Any) -> list[SectionState]:
    try:
        raw = page.evaluate(_SECTIONS_JS) or []
    except Exception:  # noqa: BLE001 - 상품등록 후 화면 검증(섹션/누락필드/위험옵션 읽기전용) - 실패 시 빈 목록 반환
        return []
    return [
        SectionState(
            title=s.get("title", ""),
            fields=s.get("fields", 0),
            filled=s.get("filled", 0),
            invalid_required=s.get("invalid_required", 0),
            summary=s.get("summary", ""),
            visible=bool(s.get("visible", True)),
        )
        for s in raw
    ]


def read_missing(page: Any) -> list[MissingField]:
    try:
        raw = page.evaluate(_MISSING_JS) or []
    except Exception:  # noqa: BLE001 - 상품등록 후 화면 검증(섹션/누락필드/위험옵션 읽기전용) - 실패 시 빈 목록 반환
        return []
    return [
        MissingField(
            ng=m.get("ng", ""),
            label=m.get("label", ""),
            section=m.get("section", ""),
            visible=bool(m.get("visible")),
            disabled=bool(m.get("disabled")),
        )
        for m in raw
    ]


def read_risky_settings(page: Any) -> list[str]:
    """조용히 상품 성격을 바꾸는 설정을 경고로 올린다."""
    try:
        r = page.evaluate(_RISKY_JS) or {}
    except Exception:  # noqa: BLE001 - 상품등록 후 화면 검증(섹션/누락필드/위험옵션 읽기전용) - 실패 시 빈 목록 반환
        return []
    warnings: list[str] = []
    for opt in r.get("preOrder") or []:
        if opt.get("value") == "true" and opt.get("checked"):
            warnings.append(
                "예약구매가 켜져 있음(vm.isPreOrderOn=true) — "
                "이대로 저장하면 일반 판매가 아니라 예약구매 상품으로 등록된다"
            )
    return warnings


def postflight(page: Any, *, expand: bool = True) -> PostflightReport:
    """저장 직전 점검. 펼치고 → 읽고 → 위험 설정을 확인한다."""
    rep = PostflightReport()
    if expand:
        rep.expanded = expand_all_sections(page)
    rep.sections = read_sections(page)
    rep.missing = read_missing(page)
    rep.warnings = read_risky_settings(page)
    return rep
