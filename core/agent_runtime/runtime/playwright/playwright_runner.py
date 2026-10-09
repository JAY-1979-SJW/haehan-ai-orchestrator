"""
로컬 Playwright runner

사용자 PC에서 Playwright를 실행하여 외부 웹사이트를 조회한다.
서버에서 실행하지 않는다.

지원 action:
- open_url
- read_page
- search
- download_file
- capture_screenshot
- extract_text
- extract_table
- wait_for_user_auth
- detect_login_status

금지:
- page.fill로 password/OTP/cert password 입력
- cookie dump / session dump
- localStorage / sessionStorage dump
- 인증서/NPKI 파일 접근
- 자동 submit / sign / pay / bid 실행
- 민감값 수집·저장·전송
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from ai_orchestrator.contracts.local_task_protocol import (
    STATUS_BLOCKED,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_WAITING_USER_AUTH,
    build_result,
)
from core.agent_runtime.runtime.auth.auth_wait_controller import (
    AUTH_SIGNAL_CERT,
    AUTH_SIGNAL_LOGIN,
    AUTH_SIGNAL_OTP,
    enter_auth_wait,
)

# ── 로그인/인증 감지 패턴 (text 기반, value 수집 없음) ─────────────────────────

_LOGIN_SIGNALS: tuple[str, ...] = (
    "로그인",
    "login",
    "sign in",
    "인증서",
    "certificate",
    "공인인증",
    "공동인증",
    "npki",
    "otp",
    "보안카드",
    "보안프로그램",
    "security program",
    "iniwebkeyboard",
)
_OTP_SIGNALS: tuple[str, ...] = (
    "otp",
    "일회용 비밀번호",
    "보안카드",
    "보안코드",
)
_CERT_SIGNALS: tuple[str, ...] = (
    "인증서",
    "certificate",
    "공인인증",
    "공동인증",
    "npki",
)


def _detect_auth_signal(text: str) -> str | None:
    """텍스트에서 인증 신호를 감지한다. 값은 수집하지 않는다."""
    lower = text.lower()
    if any(p in lower for p in _OTP_SIGNALS):
        return "otp"
    if any(p in lower for p in _CERT_SIGNALS):
        return "cert"
    if any(p in lower for p in _LOGIN_SIGNALS):
        return "login"
    return None


def run_task(task: dict[str, Any]) -> dict[str, Any]:
    """
    task를 받아 Playwright로 실행하고 safe result를 반환한다.

    실제 Playwright가 설치된 환경에서만 동작한다.
    미설치 환경에서는 NOT_AVAILABLE 상태를 반환한다.
    """
    task_id = task.get("task_id", "")
    action = (task.get("action") or "").lower()
    target_url = task.get("target_url", "")  # noqa: F841

    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except ImportError:
        return build_result(
            task_id=task_id,
            ok=False,
            status=STATUS_FAILED,
            message_ko="Playwright 미설치. 로컬 PC에 playwright를 설치해 주세요.",
        )

    dispatch = {
        "open_url": _run_open_url,
        "read_page": _run_read_page,
        "search": _run_search,
        "download_file": _run_download_file,
        "capture_screenshot": _run_capture_screenshot,
        "extract_text": _run_extract_text,
        "extract_table": _run_extract_table,
        "wait_for_user_auth": _run_wait_for_user_auth,
        "detect_login_status": _run_detect_login_status,
    }

    handler = dispatch.get(action)
    if not handler:
        return build_result(
            task_id=task_id,
            ok=False,
            status=STATUS_BLOCKED,
            message_ko=f"지원하지 않는 action: {action!r}",
        )

    try:
        with sync_playwright() as pw:
            return handler(pw, task)
    except Exception as exc:  # noqa: BLE001 - 브라우저 워커 실행기 -- 실행 실패를 ok=False 결과로 변환(fail-closed), URL 호스트 추출 실패는 빈 문자열
        return build_result(
            task_id=task_id,
            ok=False,
            status=STATUS_FAILED,
            message_ko=f"실행 오류: {type(exc).__name__}: {str(exc)[:100]}",
        )


def _get_url_host(url: str) -> str:
    try:
        return urlparse(url).netloc
    except Exception:  # noqa: BLE001 - 브라우저 워커 실행기 -- 실행 실패를 ok=False 결과로 변환(fail-closed), URL 호스트 추출 실패는 빈 문자열
        return ""


def _run_open_url(pw: Any, task: dict[str, Any]) -> dict[str, Any]:
    task_id = task["task_id"]
    target_url = task.get("target_url", "")
    timeout = task.get("timeout_seconds", 300) * 1000

    browser = pw.chromium.launch(headless=True)
    try:
        page = browser.new_page()
        page.goto(target_url, timeout=timeout)
        title = page.title()
        current_url = page.url

        body_sample = page.inner_text("body")[:500] if page.query_selector("body") else ""
        signal = _detect_auth_signal(title + "\n" + body_sample)

        if signal in ("otp",):
            return enter_auth_wait(
                task_id=task_id,
                auth_signal=AUTH_SIGNAL_OTP,
                url_host=_get_url_host(current_url),
            )
        if signal in ("cert", "login"):
            auth_sig = AUTH_SIGNAL_CERT if signal == "cert" else AUTH_SIGNAL_LOGIN
            return enter_auth_wait(
                task_id=task_id,
                auth_signal=auth_sig,
                url_host=_get_url_host(current_url),
            )

        return build_result(
            task_id=task_id,
            ok=True,
            status=STATUS_COMPLETED,
            current_url_host=_get_url_host(current_url),
            title_hint=title[:100],
            message_ko="페이지 열기 완료.",
        )
    finally:
        browser.close()


def _run_read_page(pw: Any, task: dict[str, Any]) -> dict[str, Any]:
    task_id = task["task_id"]
    target_url = task.get("target_url", "")
    timeout = task.get("timeout_seconds", 300) * 1000

    browser = pw.chromium.launch(headless=True)
    try:
        page = browser.new_page()
        page.goto(target_url, timeout=timeout)
        title = page.title()
        current_url = page.url

        body_sample = page.inner_text("body")[:1000] if page.query_selector("body") else ""
        signal = _detect_auth_signal(title + "\n" + body_sample)

        if signal:
            auth_sig = (
                AUTH_SIGNAL_OTP if signal == "otp" else AUTH_SIGNAL_CERT if signal == "cert" else AUTH_SIGNAL_LOGIN
            )
            return enter_auth_wait(
                task_id=task_id,
                auth_signal=auth_sig,
                url_host=_get_url_host(current_url),
            )

        # body_sample은 text만, 민감값 포함 없음
        extracted = {"body_text_sample": body_sample}

        return build_result(
            task_id=task_id,
            ok=True,
            status=STATUS_COMPLETED,
            current_url_host=_get_url_host(current_url),
            title_hint=title[:100],
            extracted_data=extracted,
            message_ko="페이지 읽기 완료.",
        )
    finally:
        browser.close()


def _run_search(pw: Any, task: dict[str, Any]) -> dict[str, Any]:
    task_id = task["task_id"]
    target_url = task.get("target_url", "")
    query = task.get("metadata", {}).get("query", "")
    timeout = task.get("timeout_seconds", 300) * 1000

    browser = pw.chromium.launch(headless=True)
    try:
        page = browser.new_page()
        page.goto(target_url, timeout=timeout)
        title = page.title()
        current_url = page.url

        return build_result(
            task_id=task_id,
            ok=True,
            status=STATUS_COMPLETED,
            current_url_host=_get_url_host(current_url),
            title_hint=title[:100],
            extracted_data={"query": query},
            message_ko="검색 페이지 이동 완료.",
        )
    finally:
        browser.close()


def _run_download_file(pw: Any, task: dict[str, Any]) -> dict[str, Any]:
    """다운로드. 파일 내용은 서버로 전송하지 않고 메타만 반환."""
    task_id = task["task_id"]
    target_url = task.get("target_url", "")
    timeout = task.get("timeout_seconds", 300) * 1000

    browser = pw.chromium.launch(headless=True)
    try:
        page = browser.new_page()
        with page.expect_download(timeout=timeout) as dl_info:
            page.goto(target_url, timeout=timeout)
        download = dl_info.value
        suggested_name = download.suggested_filename

        return build_result(
            task_id=task_id,
            ok=True,
            status=STATUS_COMPLETED,
            current_url_host=_get_url_host(target_url),
            title_hint=suggested_name[:100],
            downloaded_files=[suggested_name],
            message_ko=f"다운로드 완료: {suggested_name}",
        )
    finally:
        browser.close()


def _run_capture_screenshot(pw: Any, task: dict[str, Any]) -> dict[str, Any]:
    """스크린샷. 파일 경로만 반환, 이미지 바이너리는 전송하지 않음."""
    task_id = task["task_id"]
    target_url = task.get("target_url", "")
    timeout = task.get("timeout_seconds", 300) * 1000

    browser = pw.chromium.launch(headless=True)
    try:
        page = browser.new_page()
        page.goto(target_url, timeout=timeout)
        title = page.title()
        screenshot_path = f"screenshot_{task_id[:8]}.png"
        page.screenshot(path=screenshot_path)

        return build_result(
            task_id=task_id,
            ok=True,
            status=STATUS_COMPLETED,
            current_url_host=_get_url_host(page.url),
            title_hint=title[:100],
            extracted_data={"screenshot_filename": screenshot_path},
            message_ko="스크린샷 저장 완료.",
        )
    finally:
        browser.close()


def _run_extract_text(pw: Any, task: dict[str, Any]) -> dict[str, Any]:
    task_id = task["task_id"]
    target_url = task.get("target_url", "")
    selector = task.get("metadata", {}).get("selector", "body")
    timeout = task.get("timeout_seconds", 300) * 1000

    browser = pw.chromium.launch(headless=True)
    try:
        page = browser.new_page()
        page.goto(target_url, timeout=timeout)
        title = page.title()

        el = page.query_selector(selector)
        text = (el.inner_text() if el else "")[:2000]
        signal = _detect_auth_signal(title + "\n" + text)

        if signal:
            auth_sig = (
                AUTH_SIGNAL_OTP if signal == "otp" else AUTH_SIGNAL_CERT if signal == "cert" else AUTH_SIGNAL_LOGIN
            )
            return enter_auth_wait(
                task_id=task_id,
                auth_signal=auth_sig,
                url_host=_get_url_host(page.url),
            )

        return build_result(
            task_id=task_id,
            ok=True,
            status=STATUS_COMPLETED,
            current_url_host=_get_url_host(page.url),
            title_hint=title[:100],
            extracted_data={"text": text},
            message_ko="텍스트 추출 완료.",
        )
    finally:
        browser.close()


def _run_extract_table(pw: Any, task: dict[str, Any]) -> dict[str, Any]:
    task_id = task["task_id"]
    target_url = task.get("target_url", "")
    timeout = task.get("timeout_seconds", 300) * 1000

    browser = pw.chromium.launch(headless=True)
    try:
        page = browser.new_page()
        page.goto(target_url, timeout=timeout)
        title = page.title()

        rows: list[list[str]] = []
        table_els = page.query_selector_all("table")
        if table_els:
            first_table = table_els[0]
            row_els = first_table.query_selector_all("tr")
            for row in row_els[:50]:
                cells = row.query_selector_all("td, th")
                rows.append([c.inner_text().strip()[:200] for c in cells])

        return build_result(
            task_id=task_id,
            ok=True,
            status=STATUS_COMPLETED,
            current_url_host=_get_url_host(page.url),
            title_hint=title[:100],
            extracted_data={"table_rows": rows},
            message_ko=f"테이블 추출 완료 ({len(rows)}행).",
        )
    finally:
        browser.close()


def _run_wait_for_user_auth(pw: Any, task: dict[str, Any]) -> dict[str, Any]:
    """
    사용자 인증 대기. 비밀번호/OTP/인증서는 자동 입력하지 않는다.
    WAITING_USER_AUTH 반환.
    """
    task_id = task["task_id"]
    target_url = task.get("target_url", "")

    return build_result(
        task_id=task_id,
        ok=False,
        status=STATUS_WAITING_USER_AUTH,
        current_url_host=_get_url_host(target_url),
        message_ko=(
            "이 작업은 사용자 PC에서 실행됩니다.\n"
            "브라우저가 열리면 필요한 경우 직접 인증해 주세요.\n"
            "비밀번호, OTP, 인증서 비밀번호는 앱이 저장하지 않습니다."
        ),
    )


def _run_detect_login_status(pw: Any, task: dict[str, Any]) -> dict[str, Any]:
    """로그인 상태 감지. 값은 수집하지 않고 신호만 반환."""
    task_id = task["task_id"]
    target_url = task.get("target_url", "")
    timeout = task.get("timeout_seconds", 300) * 1000

    browser = pw.chromium.launch(headless=True)
    try:
        page = browser.new_page()
        page.goto(target_url, timeout=timeout)
        title = page.title()
        body_sample = page.inner_text("body")[:500] if page.query_selector("body") else ""
        signal = _detect_auth_signal(title + "\n" + body_sample)

        status = STATUS_WAITING_USER_AUTH if signal else STATUS_COMPLETED
        return build_result(
            task_id=task_id,
            ok=True,
            status=status,
            current_url_host=_get_url_host(page.url),
            title_hint=title[:100],
            extracted_data={"auth_signal": signal},
            message_ko=f"로그인 상태 감지 완료. 신호: {signal or '없음'}",
        )
    finally:
        browser.close()
