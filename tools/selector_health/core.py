"""셀렉터 헬스체크 코어 — 코드에 박힌 셀렉터가 실제 사이트에서 아직 유효한지 실측.

배경(2026-08-14~15):
    네이버는 CSS 모듈 해시(adProduct_item__T7utB)와 UI 구조를 자주 바꾼다.
    코드의 셀렉터는 작성 시점엔 맞았지만 이후 조용히 죽고, 아무도 모르다가
    실제 작업 중에 드러난다. 실제로 하루에만 아래가 전부 이 원인이었다:
      - 태그 입력창이 발행 패널 안으로 이동 → set_tags 사망
      - 대표이미지가 input[type=file] → 모달 방식으로 변경 → upload_main_image 사망
      - 에디터가 같은 탭 → 별도 탭으로 변경 → _click_editor_btn 사망

핵심 설계:
    일부 셀렉터는 **특정 UI 상태에서만** 존재한다(예: 태그 입력창은 발행 패널을
    열어야 나타남). 그래서 단순 존재 확인이 아니라 `requires`(선행조건)를 두고,
    해당 상태를 만든 뒤에 검사한다. 이게 없으면 "정상인데 없다"고 오판한다.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

# 검사 결과 상태
OK = "ok"  # 기대대로 존재(및 가시)
HIDDEN = "hidden"  # DOM 에는 있으나 보이지 않음
MISSING = "missing"  # DOM 에 없음 → 드리프트 의심
SKIPPED = "skipped"  # 선행조건 미충족으로 검사 못 함
ERROR = "error"  # 검사 중 예외


@dataclass(frozen=True)
class SelectorCheck:
    """검사 대상 셀렉터 1건."""

    name: str
    selector: str
    requires: str | None = None  # 선행조건 키 (preconditions 의 키)
    expect: str = "visible"  # "visible" | "present"
    note: str = ""  # 사람이 읽을 설명


@dataclass
class CheckResult:
    name: str
    selector: str
    status: str
    count: int = 0
    visible_count: int = 0
    detail: str = ""
    note: str = ""

    @property
    def is_problem(self) -> bool:
        return self.status in (MISSING, ERROR) or (self.status == HIDDEN and self.expect_visible)

    expect_visible: bool = True


@dataclass
class SiteSpec:
    """사이트 1개의 헬스체크 명세."""

    key: str
    title: str
    url: str
    checks: list[SelectorCheck]
    # 선행조건: {키: (page) -> bool}  — True 면 상태 진입 성공
    preconditions: dict[str, Callable[[Any], bool]] = field(default_factory=dict)
    # 페이지 로드 후 대기(초)
    settle_s: float = 4.0
    # 페이지 진입 직후 1회 실행(공지/복원 팝업 닫기 등). 실패해도 검사는 계속한다.
    setup: Callable[[Any], None] | None = None


_MAX_VIS_PROBE = 20  # 가시성 확인은 상위 N개까지만 (성능)


def _probe(page: Any, selector: str) -> tuple[int, int]:
    """셀렉터의 (전체 개수, 보이는 개수) 반환.

    Playwright locator 로 조회한다 — 실제 자동화 코드가 쓰는 방식과 동일해야
    같은 결과가 나온다. querySelectorAll 로 하면 `:has-text()` 같은 Playwright
    전용 문법이 CSS 파싱 오류로 죽는다(2026-08-15 실제 발생).
    """
    loc = page.locator(selector)
    total = loc.count()
    if total == 0:
        return 0, 0
    visible = 0
    for i in range(min(total, _MAX_VIS_PROBE)):
        try:
            if loc.nth(i).is_visible(timeout=500):
                visible += 1
        except Exception:  # noqa: BLE001 - UI 셀렉터 존재여부 헬스체크(읽기전용) — 가시성 확인/선행조건 확인/셀렉터 조회 실패 시 모두 ERROR/SKIPPED 상태로 명확히 표시되어 '정상'으로 오판되지 않음.
            pass
    return total, visible


def _check_precondition(spec, page, req, _say):
    satisfied = True
    if req:
        fn = spec.preconditions.get(req)
        if fn is None:
            satisfied = False
            _say(f"  [선행조건 미정의] {req}")
        else:
            try:
                satisfied = bool(fn(page))
            except Exception as e:  # noqa: BLE001 - UI 셀렉터 존재여부 헬스체크(읽기전용) — 가시성 확인/선행조건 확인/셀렉터 조회 실패 시 모두 ERROR/SKIPPED 상태로 명확히 표시되어 '정상'으로 오판되지 않음.
                satisfied = False
                _say(f"  [선행조건 실패] {req}: {type(e).__name__}")
            if not satisfied:
                _say(f"  [선행조건 미충족] {req} — 관련 셀렉터 검사 skip")
    return satisfied


def _run_one_check(page, c, req, satisfied) -> CheckResult:
    if not satisfied:
        return CheckResult(
            c.name,
            c.selector,
            SKIPPED,
            note=c.note,
            detail=f"선행조건 '{req}' 미충족",
            expect_visible=(c.expect == "visible"),
        )
    try:
        total, vis = _probe(page, c.selector)
    except Exception as e:  # noqa: BLE001 - UI 셀렉터 존재여부 헬스체크(읽기전용) — 가시성 확인/선행조건 확인/셀렉터 조회 실패 시 모두 ERROR/SKIPPED 상태로 명확히 표시되어 '정상'으로 오판되지 않음.
        return CheckResult(
            c.name,
            c.selector,
            ERROR,
            detail=type(e).__name__,
            note=c.note,
            expect_visible=(c.expect == "visible"),
        )

    if total == 0:
        status = MISSING
    elif c.expect == "visible" and vis == 0:
        status = HIDDEN
    else:
        status = OK
    return CheckResult(c.name, c.selector, status, total, vis, note=c.note, expect_visible=(c.expect == "visible"))


def run_site_checks(page: Any, spec: SiteSpec, *, log=None) -> list[CheckResult]:
    """한 사이트의 셀렉터를 순서대로 검사.

    선행조건이 같은 검사끼리 묶어 상태 전환을 최소화한다.
    """

    def _say(msg: str) -> None:
        if log:
            log(msg)

    page.goto(spec.url, wait_until="domcontentloaded", timeout=40000)
    page.wait_for_timeout(int(spec.settle_s * 1000))

    if spec.setup is not None:
        try:
            spec.setup(page)
        except Exception as e:  # noqa: BLE001 - UI 셀렉터 존재여부 헬스체크(읽기전용) — 가시성 확인/선행조건 확인/셀렉터 조회 실패 시 모두 ERROR/SKIPPED 상태로 명확히 표시되어 '정상'으로 오판되지 않음.
            _say(f"  [setup 실패, 검사는 계속] {type(e).__name__}: {str(e)[:80]}")

    # 선행조건 없는 것 먼저, 그다음 조건별로 묶어서
    groups: dict[str | None, list[SelectorCheck]] = {}
    for c in spec.checks:
        groups.setdefault(c.requires, []).append(c)

    results: list[CheckResult] = []
    for req in sorted(groups, key=lambda k: (k is not None, k or "")):
        satisfied = _check_precondition(spec, page, req, _say)

        for c in groups[req]:
            results.append(_run_one_check(page, c, req, satisfied))
    return results


_ICON = {OK: "✅", HIDDEN: "⚠️ ", MISSING: "❌", SKIPPED: "⏭️ ", ERROR: "💥"}


def format_report(spec: SiteSpec, results: list[CheckResult]) -> str:
    lines = [f"── {spec.title} ({spec.url})", ""]
    for r in results:
        icon = _ICON.get(r.status, "?")
        cnt = f"({r.count}개, 보임 {r.visible_count})" if r.count else ""
        lines.append(f"  {icon} {r.name:<28} {cnt}")
        lines.append(f"       {r.selector[:80]}")
        if r.detail:
            lines.append(f"       → {r.detail}")
        if r.status in (MISSING, HIDDEN) and r.note:
            lines.append(f"       ※ {r.note}")
    problems = [r for r in results if r.is_problem]
    lines.append("")
    lines.append(f"  총 {len(results)}건 / 문제 {len(problems)}건")
    return "\n".join(lines)
