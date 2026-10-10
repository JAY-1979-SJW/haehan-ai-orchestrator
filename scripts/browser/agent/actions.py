"""CDP 기반 브라우저 액션 실행기.

모든 액션은 3단계로 처리된다:
  1. action_gate → AUTO / NOTIFY / APPROVE 분류
  2. 실제 Playwright 액션 실행
  3. audit_log 기록

사용자 승인이 필요한 액션(APPROVE)은 GateApprovalRequired 예외를 발생시키고,
호출자가 사용자 확인 후 force=True로 재호출해야 한다.
자격증명(비밀번호·카드번호·OTP·주민번호 등)도 사용자 승인 후 입력 가능하다.

지원 액션
=========
navigate, click, type_text, select_option, upload_file,
screenshot, scroll, get_text, get_attribute, wait_for_selector,
accept_dialog, fill_form
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from scripts.browser.agent.action_gate import (
    GATE_APPROVE,
    GateResult,
    classify_action,
)
from scripts.browser.agent.audit_log import log_action
from scripts.browser.agent.intent_token import IntentToken

# ── 예외 ────────────────────────────────────────────────────────────────────


class GateApprovalRequired(RuntimeError):
    """APPROVE 액션 — 사용자 확인 필요."""

    def __init__(self, gate: GateResult, action_type: str, label: str):
        super().__init__(f"[APPROVAL_REQUIRED] {action_type} '{label}' → {gate.reason}")
        self.gate = gate
        self.action_type = action_type
        self.label = label

    def approval_prompt(self) -> str:
        cat = self.gate.category or ""
        kw = self.gate.matched_keyword or ""
        return (
            f"[승인 필요] {self.action_type.upper()}: {self.label}\n"
            f"  카테고리: {cat}  |  키워드: {kw}\n"
            f"  이유: {self.gate.reason}\n"
            f"  진행하시겠습니까? (y/n)"
        )


# ── 결과 ────────────────────────────────────────────────────────────────────


@dataclass
class ActionResult:
    action: str
    ok: bool
    verdict: str = "AUTO"
    value: Any = None  # 텍스트 추출, screenshot bytes 등
    error: str = ""
    extra: dict = field(default_factory=dict)


# ── 내부 헬퍼 ───────────────────────────────────────────────────────────────


def _gate_check(
    action_type: str,
    label: str,
    url: str,
    intent: IntentToken | None,
    params: dict,
    force: bool,
) -> GateResult:
    """gate 분류 → APPROVE면 force 없을 때 GateApprovalRequired 예외."""
    gate = classify_action(
        action_type=action_type,
        label=label,
        url=url,
        intent=intent,
        params=params,
    )
    if gate.verdict == GATE_APPROVE and not force:
        raise GateApprovalRequired(gate, action_type, label)
    return gate


def _current_url(page) -> str:
    try:
        return page.url or ""
    except Exception:  # noqa: BLE001 - 감사로그 완비된 브라우저 액션 실행기 — 모든 액션이 성공/실패 모두 log_action()으로 감사기록(risk_level·audit_path 포함), 실패는 ActionResult(ok=False, error) 로 반환, 아무것도 숨기지 않음(2026-09-28 검토)
        return ""


# ── 공개 액션 함수 ─────────────────────────────────────────────────────────


def navigate(  # noqa: PLR0913 - 공개 시그니처 유지(키워드 인자 호환)
    page,
    url: str,
    *,
    intent: IntentToken | None = None,
    audit_path: Path | None = None,
    wait_until: str = "domcontentloaded",
    timeout_ms: int = 30_000,
    force: bool = False,
) -> ActionResult:
    """URL 탐색."""
    gate = _gate_check("navigate", "", url, intent, {}, force)
    try:
        page.goto(url, wait_until=wait_until, timeout=timeout_ms)
        log_action("navigate", url=url, result="ok", risk_level=gate.verdict, audit_path=audit_path)
        return ActionResult("navigate", ok=True, verdict=gate.verdict, value=url)
    except Exception as e:  # noqa: BLE001 - 감사로그 완비된 브라우저 액션 실행기 — 모든 액션이 성공/실패 모두 log_action()으로 감사기록(risk_level·audit_path 포함), 실패는 ActionResult(ok=False, error) 로 반환, 아무것도 숨기지 않음(2026-09-28 검토)
        log_action(
            "navigate", url=url, result="error", error=str(e)[:300], risk_level=gate.verdict, audit_path=audit_path
        )
        return ActionResult("navigate", ok=False, verdict=gate.verdict, error=str(e))


def click(  # noqa: PLR0913 - 공개 시그니처 유지(키워드 인자 호환)
    page,
    selector: str,
    *,
    label: str = "",
    intent: IntentToken | None = None,
    audit_path: Path | None = None,
    timeout_ms: int = 10_000,
    force: bool = False,
) -> ActionResult:
    """요소 클릭."""
    url = _current_url(page)
    gate = _gate_check("click", label, url, intent, {}, force)
    try:
        page.click(selector, timeout=timeout_ms)
        log_action(
            "click",
            url=url,
            selector=selector[:200],
            result="ok",
            risk_level=gate.verdict,
            extra={"label": label},
            audit_path=audit_path,
        )
        return ActionResult("click", ok=True, verdict=gate.verdict)
    except Exception as e:  # noqa: BLE001 - 감사로그 완비된 브라우저 액션 실행기 — 모든 액션이 성공/실패 모두 log_action()으로 감사기록(risk_level·audit_path 포함), 실패는 ActionResult(ok=False, error) 로 반환, 아무것도 숨기지 않음(2026-09-28 검토)
        log_action(
            "click",
            url=url,
            selector=selector[:200],
            result="error",
            error=str(e)[:300],
            risk_level=gate.verdict,
            audit_path=audit_path,
        )
        return ActionResult("click", ok=False, verdict=gate.verdict, error=str(e))


def type_text(  # noqa: PLR0913 - 공개 시그니처 유지(키워드 인자 호환)
    page,
    selector: str,
    value: str,
    *,
    label: str = "",
    intent: IntentToken | None = None,
    audit_path: Path | None = None,
    delay_ms: int = 30,
    clear_first: bool = True,
    force: bool = False,
) -> ActionResult:
    """텍스트 입력 (비밀번호 필드 자동 차단)."""
    url = _current_url(page)
    gate = _gate_check("type", label, url, intent, {label or selector: value}, force)
    try:
        if clear_first:
            page.fill(selector, "")
        page.type(selector, value, delay=delay_ms)
        log_action(
            "type",
            url=url,
            selector=selector[:200],
            result="ok",
            risk_level=gate.verdict,
            params={"label": label, "length": len(value)},
            audit_path=audit_path,
        )
        return ActionResult("type", ok=True, verdict=gate.verdict)
    except Exception as e:  # noqa: BLE001 - 감사로그 완비된 브라우저 액션 실행기 — 모든 액션이 성공/실패 모두 log_action()으로 감사기록(risk_level·audit_path 포함), 실패는 ActionResult(ok=False, error) 로 반환, 아무것도 숨기지 않음(2026-09-28 검토)
        log_action(
            "type",
            url=url,
            selector=selector[:200],
            result="error",
            error=str(e)[:300],
            risk_level=gate.verdict,
            audit_path=audit_path,
        )
        return ActionResult("type", ok=False, verdict=gate.verdict, error=str(e))


def select_option(  # noqa: PLR0913 - 공개 시그니처 유지(키워드 인자 호환)
    page,
    selector: str,
    value: str,
    *,
    label: str = "",
    intent: IntentToken | None = None,
    audit_path: Path | None = None,
    force: bool = False,
) -> ActionResult:
    """드롭다운/select 선택."""
    url = _current_url(page)
    gate = _gate_check("select", label, url, intent, {}, force)
    try:
        page.select_option(selector, value)
        log_action(
            "select",
            url=url,
            selector=selector[:200],
            result="ok",
            risk_level=gate.verdict,
            extra={"value": value, "label": label},
            audit_path=audit_path,
        )
        return ActionResult("select", ok=True, verdict=gate.verdict, value=value)
    except Exception as e:  # noqa: BLE001 - 감사로그 완비된 브라우저 액션 실행기 — 모든 액션이 성공/실패 모두 log_action()으로 감사기록(risk_level·audit_path 포함), 실패는 ActionResult(ok=False, error) 로 반환, 아무것도 숨기지 않음(2026-09-28 검토)
        log_action(
            "select", url=url, result="error", error=str(e)[:300], risk_level=gate.verdict, audit_path=audit_path
        )
        return ActionResult("select", ok=False, verdict=gate.verdict, error=str(e))


def upload_file(  # noqa: PLR0913 - 공개 시그니처 유지(키워드 인자 호환)
    page,
    selector: str,
    file_path: str | Path,
    *,
    label: str = "",
    intent: IntentToken | None = None,
    audit_path: Path | None = None,
    force: bool = False,
) -> ActionResult:
    """파일 업로드 (input[type=file] 또는 파일 선택 다이얼로그).

    기본 분류: NOTIFY — 어떤 파일을 올리는지 사용자에게 알림.
    force=True 이면 알림 후 진행.
    """
    url = _current_url(page)
    fp = Path(file_path)
    gate = _gate_check("file_upload", label or fp.name, url, intent, {}, force)
    try:
        page.set_input_files(selector, str(fp))
        log_action(
            "file_upload",
            url=url,
            selector=selector[:200],
            result="ok",
            risk_level=gate.verdict,
            extra={"filename": fp.name, "size_bytes": fp.stat().st_size if fp.exists() else -1},
            audit_path=audit_path,
        )
        return ActionResult("file_upload", ok=True, verdict=gate.verdict, value=str(fp))
    except Exception as e:  # noqa: BLE001 - 감사로그 완비된 브라우저 액션 실행기 — 모든 액션이 성공/실패 모두 log_action()으로 감사기록(risk_level·audit_path 포함), 실패는 ActionResult(ok=False, error) 로 반환, 아무것도 숨기지 않음(2026-09-28 검토)
        log_action(
            "file_upload", url=url, result="error", error=str(e)[:300], risk_level=gate.verdict, audit_path=audit_path
        )
        return ActionResult("file_upload", ok=False, verdict=gate.verdict, error=str(e))


def screenshot(
    page,
    save_path: Path,
    *,
    intent: IntentToken | None = None,
    audit_path: Path | None = None,
    full_page: bool = False,
    force: bool = False,
) -> ActionResult:
    """페이지 스크린샷 저장."""
    url = _current_url(page)
    gate = _gate_check("screenshot", "", url, intent, {}, force)
    try:
        save_path.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(save_path), full_page=full_page)
        log_action(
            "screenshot",
            url=url,
            result="ok",
            risk_level=gate.verdict,
            extra={"path": str(save_path)},
            audit_path=audit_path,
        )
        return ActionResult("screenshot", ok=True, verdict=gate.verdict, value=str(save_path))
    except Exception as e:  # noqa: BLE001 - 감사로그 완비된 브라우저 액션 실행기 — 모든 액션이 성공/실패 모두 log_action()으로 감사기록(risk_level·audit_path 포함), 실패는 ActionResult(ok=False, error) 로 반환, 아무것도 숨기지 않음(2026-09-28 검토)
        log_action(
            "screenshot", url=url, result="error", error=str(e)[:300], risk_level=gate.verdict, audit_path=audit_path
        )
        return ActionResult("screenshot", ok=False, verdict=gate.verdict, error=str(e))


def scroll(
    page,
    *,
    direction: str = "down",
    amount: int = 500,
    intent: IntentToken | None = None,
    audit_path: Path | None = None,
    force: bool = False,
) -> ActionResult:
    """페이지 스크롤."""
    url = _current_url(page)
    gate = _gate_check("scroll", direction, url, intent, {}, force)
    try:
        dy = amount if direction == "down" else -amount
        page.evaluate(f"window.scrollBy(0, {dy})")
        log_action(
            "scroll",
            url=url,
            result="ok",
            risk_level=gate.verdict,
            extra={"direction": direction, "amount": amount},
            audit_path=audit_path,
        )
        return ActionResult("scroll", ok=True, verdict=gate.verdict)
    except Exception as e:  # noqa: BLE001 - 감사로그 완비된 브라우저 액션 실행기 — 모든 액션이 성공/실패 모두 log_action()으로 감사기록(risk_level·audit_path 포함), 실패는 ActionResult(ok=False, error) 로 반환, 아무것도 숨기지 않음(2026-09-28 검토)
        log_action(
            "scroll", url=url, result="error", error=str(e)[:300], risk_level=gate.verdict, audit_path=audit_path
        )
        return ActionResult("scroll", ok=False, verdict=gate.verdict, error=str(e))


def get_text(
    page,
    selector: str,
    *,
    intent: IntentToken | None = None,
    audit_path: Path | None = None,
    force: bool = False,
) -> ActionResult:
    """요소 텍스트 추출."""
    url = _current_url(page)
    gate = _gate_check("get_text", selector, url, intent, {}, force)
    try:
        text = page.inner_text(selector)
        log_action(
            "get_text", url=url, selector=selector[:200], result="ok", risk_level=gate.verdict, audit_path=audit_path
        )
        return ActionResult("get_text", ok=True, verdict=gate.verdict, value=text)
    except Exception as e:  # noqa: BLE001 - 감사로그 완비된 브라우저 액션 실행기 — 모든 액션이 성공/실패 모두 log_action()으로 감사기록(risk_level·audit_path 포함), 실패는 ActionResult(ok=False, error) 로 반환, 아무것도 숨기지 않음(2026-09-28 검토)
        log_action(
            "get_text", url=url, result="error", error=str(e)[:300], risk_level=gate.verdict, audit_path=audit_path
        )
        return ActionResult("get_text", ok=False, verdict=gate.verdict, error=str(e))


def get_attribute(
    page,
    selector: str,
    attribute: str,
    *,
    intent: IntentToken | None = None,
    audit_path: Path | None = None,
    force: bool = False,
) -> ActionResult:
    """요소 속성값 추출."""
    url = _current_url(page)
    gate = _gate_check("get_text", selector, url, intent, {}, force)
    try:
        val = page.get_attribute(selector, attribute)
        log_action(
            "get_attribute",
            url=url,
            selector=selector[:200],
            result="ok",
            risk_level=gate.verdict,
            extra={"attribute": attribute},
            audit_path=audit_path,
        )
        return ActionResult("get_attribute", ok=True, verdict=gate.verdict, value=val)
    except Exception as e:  # noqa: BLE001 - 감사로그 완비된 브라우저 액션 실행기 — 모든 액션이 성공/실패 모두 log_action()으로 감사기록(risk_level·audit_path 포함), 실패는 ActionResult(ok=False, error) 로 반환, 아무것도 숨기지 않음(2026-09-28 검토)
        log_action(
            "get_attribute", url=url, result="error", error=str(e)[:300], risk_level=gate.verdict, audit_path=audit_path
        )
        return ActionResult("get_attribute", ok=False, verdict=gate.verdict, error=str(e))


def wait_for_selector(  # noqa: PLR0913 - 공개 시그니처 유지(키워드 인자 호환)
    page,
    selector: str,
    *,
    state: str = "visible",
    timeout_ms: int = 15_000,
    intent: IntentToken | None = None,
    audit_path: Path | None = None,
    force: bool = False,
) -> ActionResult:
    """요소가 나타날 때까지 대기."""
    url = _current_url(page)
    gate = _gate_check("wait", selector, url, intent, {}, force)
    try:
        page.wait_for_selector(selector, state=state, timeout=timeout_ms)
        log_action(
            "wait_for_selector",
            url=url,
            selector=selector[:200],
            result="ok",
            risk_level=gate.verdict,
            audit_path=audit_path,
        )
        return ActionResult("wait_for_selector", ok=True, verdict=gate.verdict)
    except Exception as e:  # noqa: BLE001 - 감사로그 완비된 브라우저 액션 실행기 — 모든 액션이 성공/실패 모두 log_action()으로 감사기록(risk_level·audit_path 포함), 실패는 ActionResult(ok=False, error) 로 반환, 아무것도 숨기지 않음(2026-09-28 검토)
        log_action(
            "wait_for_selector",
            url=url,
            result="error",
            error=str(e)[:300],
            risk_level=gate.verdict,
            audit_path=audit_path,
        )
        return ActionResult("wait_for_selector", ok=False, verdict=gate.verdict, error=str(e))


def accept_dialog(
    page,
    *,
    intent: IntentToken | None = None,
    audit_path: Path | None = None,
    force: bool = False,
) -> ActionResult:
    """alert/confirm 다이얼로그 수락."""
    url = _current_url(page)
    gate = _gate_check("alert_accept", "dialog", url, intent, {}, force)
    try:
        page.on("dialog", lambda dialog: dialog.accept())
        log_action("accept_dialog", url=url, result="ok", risk_level=gate.verdict, audit_path=audit_path)
        return ActionResult("accept_dialog", ok=True, verdict=gate.verdict)
    except Exception as e:  # noqa: BLE001 - 감사로그 완비된 브라우저 액션 실행기 — 모든 액션이 성공/실패 모두 log_action()으로 감사기록(risk_level·audit_path 포함), 실패는 ActionResult(ok=False, error) 로 반환, 아무것도 숨기지 않음(2026-09-28 검토)
        log_action(
            "accept_dialog", url=url, result="error", error=str(e)[:300], risk_level=gate.verdict, audit_path=audit_path
        )
        return ActionResult("accept_dialog", ok=False, verdict=gate.verdict, error=str(e))


def fill_form(
    page,
    fields: dict[str, str],
    *,
    intent: IntentToken | None = None,
    audit_path: Path | None = None,
    delay_ms: int = 30,
    force: bool = False,
) -> list[ActionResult]:
    """폼 필드 일괄 입력.

    Parameters
    ----------
    fields : {selector: value} 또는 {selector: {"value": v, "label": l}}
    """
    results = []
    for selector, v in fields.items():
        if isinstance(v, dict):
            value = v.get("value", "")
            label = v.get("label", selector)
        else:
            value = v
            label = selector
        r = type_text(
            page, selector, value, label=label, intent=intent, audit_path=audit_path, delay_ms=delay_ms, force=force
        )
        results.append(r)
        if not r.ok:
            break
    return results


def wait_ms(ms: int) -> None:
    """단순 대기 (ms). Playwright pause 대신 사용."""
    time.sleep(ms / 1000)
