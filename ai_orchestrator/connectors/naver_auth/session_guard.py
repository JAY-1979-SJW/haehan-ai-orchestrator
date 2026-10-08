"""네이버 세션 지킴이 — 상태·계정을 읽고, 로그인돼 있지 않으면 바로 자동 로그인한다.

기준서: docs/specs/2026-10-01_electron_naver_auto_login.md (§6: 2026-10-01 사용자 지시로 시도 제한 제거)

| 판정 | 동작 |
|---|---|
| in + 대상 계정 alias 일치 | 아무것도 안 함 |
| in + 다른 계정 / 계정 미확인 | 건드리지 않음(전환하려면 로그아웃이 필요해 자동으로 하지 않음) |
| out / unknown | 대상 계정으로 바로 자동 로그인(횟수·간격 제한 없음). 캡차·2단계 인증은 파이프라인이 중단 |
| unavailable | 브라우저를 못 쓰므로 시도할 수 없음 |

로그아웃 URL 이동·쿠키 삭제는 하지 않는다. 자격증명은 이 모듈이 읽지 않는다(파이프라인이 저장소에서 꺼내 쓴다).
외부 의존(브라우저·파이프라인·시각·시도 기록)은 전부 `GuardDeps` 로 주입받아 테스트에서 가짜로 바꾼다.
"""

from __future__ import annotations

import contextlib
import json
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from ai_orchestrator.paths.runtime import data_dir
from scripts.naver.blog.automation.account_probe import alias_to_blog_id

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[3]
ATTEMPTS_FILE = data_dir() / "naver_login_attempts.json"
SETTLE_CHECKS = 6  # 로그인 직후 페이지 이동이 끝나 상태를 읽을 수 있을 때까지 다시 읽는 횟수
SETTLE_WAIT_SECONDS = 3.0
_KEEP = 100
_LOCK = threading.Lock()


@dataclass(frozen=True)
class GuardDeps:
    now: Callable[[], datetime]
    detect: Callable[
        [], dict[str, Any]
    ]  # 읽기 전용 상태 판정 → {"state": in/out/unknown/unavailable, "cookie": bool|None}
    read_alias: Callable[[], str | None]  # 새 탭에서 블로그 alias 읽기(읽기 전용)
    run_login: Callable[[str], dict[str, Any]]  # 로그인 파이프라인(naver_id) — out 일 때만 호출
    save_attempt: Callable[[dict[str, Any]], None]
    # 브라우저가 꺼져 있으면 시작까지 하는 판정(자동 로그인 흐름 전용). 없으면 detect 를 쓴다(테스트의 가짜 부품 호환).
    detect_starting: Callable[[], dict[str, Any]] | None = None
    sleep: Callable[[float], None] = time.sleep


# ── 상태 확인·결정 ───────────────────────────────────────────────────────


def observe(target: str, deps: GuardDeps, *, start_browser: bool = False) -> dict[str, Any]:
    """읽기 전용 관찰: 로그인 상태와(로그인돼 있으면) 어느 계정인지.

    기본은 브라우저를 시작하지 않는다 — 꺼져 있으면 바로 unavailable. 화면이 상태를 반복해서 확인하는 용도라
    사용자 PC 에서 Chrome 이 저절로 뜨고 최대 20초 기다리면 안 된다(2026-10-04 앱 실검증 D7).
    자동 로그인 흐름(start_browser=True)만 필요할 때 브라우저를 시작한다.
    """
    detect = deps.detect_starting if (start_browser and deps.detect_starting is not None) else deps.detect
    detected = detect()
    state = str(detected.get("state", "unknown"))
    seen: dict[str, Any] = {
        "target": target,
        "state": state,
        "cookie": detected.get("cookie"),
        "alias": None,
        "account": None,
    }
    if state == "in":
        alias = deps.read_alias()
        seen["alias"] = alias
        seen["account"] = "unknown" if alias is None else ("verified" if alias_to_blog_id(alias) == target else "other")
    return seen


def _describe(seen: dict[str, Any]) -> str:
    state, account, alias = seen["state"], seen.get("account"), seen.get("alias")
    if state == "in":
        if account == "verified":
            return f"로그인됨 — 계정 확인됨 ({seen['target']})"
        if account == "other":
            return f"다른 계정으로 로그인돼 있습니다 ({alias}). 자동으로 전환하지 않습니다."
        return "로그인됨 — 계정을 확인하지 못했습니다."
    if state == "out":
        return "로그아웃 상태입니다."
    if state == "unavailable":
        return "브라우저에 연결할 수 없습니다."
    return "로그인 상태가 불명확합니다(세션 쿠키는 있는데 화면 근거가 충돌)."


def _result(seen: dict[str, Any], action: str, reason: str, message: str | None = None, **extra: Any) -> dict[str, Any]:
    return {**seen, "action": action, "reason": reason, "message": message or _describe(seen), **extra}


def _login_outcome(result: dict[str, Any]) -> str:
    if result.get("logged_in"):
        return "ok"
    return "captcha" if result.get("captcha") else "failed"


def _observe_after_login(target: str, deps: GuardDeps) -> dict[str, Any]:
    """로그인 직후에는 페이지가 이동 중이라 상태가 unknown 으로 읽힐 수 있다 — 안정될 때까지 몇 번 다시 읽는다."""
    seen = observe(target, deps, start_browser=True)
    for _ in range(SETTLE_CHECKS):
        if seen["state"] in ("in", "out"):
            break
        deps.sleep(SETTLE_WAIT_SECONDS)
        seen = observe(target, deps, start_browser=True)
    return seen


def ensure_login(target: str, deps: GuardDeps, *, allow_attempt: bool = True) -> dict[str, Any]:
    """상태를 확인하고 로그인돼 있지 않으면(out·unknown) 바로 자동 로그인. 결과 dict 의 action: none / logged_in / unverified / captcha / failed."""
    seen = observe(target, deps, start_browser=True)  # 자동 로그인이 목적이라 브라우저가 꺼져 있으면 시작한다
    if seen["state"] not in ("out", "unknown"):
        return _result(seen, "none", "already_logged_in" if seen["state"] == "in" else f"state_{seen['state']}")
    if not allow_attempt:
        return _result(seen, "none", "attempt_not_allowed")

    started = deps.now()
    login = deps.run_login(target)
    outcome = _login_outcome(login)
    deps.save_attempt(
        {
            "at": started.isoformat(timespec="seconds"),
            "target": target,
            "result": outcome,
            "reason": str(login.get("message", ""))[:120],
        }
    )
    after = _observe_after_login(target, deps)
    if after["state"] == "in":
        return _result(after, "logged_in", "auto_login_ok", "자동 로그인 성공 — " + _describe(after))
    if outcome == "ok" and after["state"] == "unknown":
        # 파이프라인은 성공이라고 했고 세션 쿠키도 있지만 화면 근거가 아직 불명확 — 실패라고 단정하지 않는다.
        return _result(
            after,
            "unverified",
            "login_unverified",
            "로그인은 성공한 것으로 보이나 화면에서 확인하지 못했습니다. 새로고침해 다시 확인해 주세요.",
        )
    if outcome == "captcha":
        return _result(
            after, "captcha", "captcha_or_2fa", "캡차·보안 확인이 필요합니다 — 브라우저에서 직접 처리해 주세요."
        )
    return _result(
        after, "failed", "auto_login_failed", "자동 로그인에 실패했습니다: " + str(login.get("message", ""))[:120]
    )


# ── 실제 부품 연결 ───────────────────────────────────────────────────────


def _save_attempt(entry: dict[str, Any]) -> None:
    with _LOCK:
        try:
            current = json.loads(ATTEMPTS_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            current = []
        current = [*(current if isinstance(current, list) else []), entry][-_KEEP:]
        ATTEMPTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        ATTEMPTS_FILE.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")


def default_deps() -> GuardDeps:
    """브라우저(CDP)·로그인 파이프라인·시도 기록 파일을 연결한다. 테스트는 이 함수를 쓰지 않는다."""
    from ai_orchestrator.connectors.naver_auth.login_pipeline import _is_cdp_alive, _start_cdp, run_naver_login_pipeline
    from scripts.auth import login_detector
    from scripts.browser.cdp.connection import open_page, run_on_browser_thread
    from scripts.browser.page.web_connector import get_page_by_url
    from scripts.naver.blog.automation.account_probe import read_alias

    def _detect(start_browser: bool) -> dict[str, Any]:
        try:
            if not _is_cdp_alive():
                if not start_browser:
                    return {"state": "unavailable", "cookie": None}  # 읽기 전용 확인은 브라우저를 띄우지 않는다
                _start_cdp()  # 로그인 파이프라인이 하는 것과 같다(프로필 유지, 세션 보존)

            def job() -> dict[str, Any]:
                page = get_page_by_url("naver.com", create_url="https://www.naver.com/")
                with contextlib.suppress(Exception):  # 이동 중인 페이지는 끝날 때까지 잠깐 기다린 뒤 읽는다
                    page.wait_for_load_state("load", timeout=10000)
                found = login_detector.detect_login_state(page)
                return {
                    "state": found.get("state", "unknown"),
                    "cookie": (found.get("evidence") or {}).get("session_cookie"),
                }

            return run_on_browser_thread(job, timeout=90)
        except Exception as exc:  # noqa: BLE001 - 브라우저를 못 쓰는 경우는 "연결 불가"로 알리고 아무것도 시도하지 않는다(fail-closed)
            logger.warning("세션 상태 감지 실패: %s", type(exc).__name__)
            return {"state": "unavailable", "cookie": None}

    def alias_in_new_tab() -> str | None:
        def job() -> str | None:
            page = open_page(allow_new_tab=True, reason="naver-session-probe")
            try:
                return read_alias(page)
            finally:
                with contextlib.suppress(Exception):  # 탭 정리 실패는 결과에 영향 없음
                    page.close()

        try:
            return run_on_browser_thread(job, timeout=60)
        except Exception as exc:  # noqa: BLE001 - 계정 확인 실패는 "계정 미확인"으로 표시(동작은 막지 않음)
            logger.warning("계정 별칭 확인 실패: %s", type(exc).__name__)
            return None

    return GuardDeps(
        now=datetime.now,
        detect=lambda: _detect(False),
        detect_starting=lambda: _detect(True),
        read_alias=alias_in_new_tab,
        run_login=lambda target: run_naver_login_pipeline(naver_id=target),
        save_attempt=_save_attempt,
    )
