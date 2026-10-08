"""
LOCAL_AGENT_PUBLIC_EXTERNAL_READONLY_LIVE_SMOKE_1

로컬 PC 에이전트 경로에서만 공개/비로그인 사이트 read-only smoke 실행.

원칙:
- allowlist 사이트만 접속
- read-only 액션만 (title, text excerpt, link 카운트, 다운로드 후보 카운트)
- 로그인/타이프/제출/다운로드 실행/쿠키/세션/스토리지 추출 모두 금지
- 결과는 universal_safe_result 정책에 맞춰 redaction
- HTML 원문/screenshot/cookies/storage 저장 금지

서버에서 절대 실행하면 안 된다.
이 스크립트는 사용자 PC에서 직접 실행되어야 한다.
"""

from __future__ import annotations

import json
import os
import platform
import socket
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_REPO_ROOT = str(Path(__file__).resolve().parent.parent.parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# allowlist (3개 공개 사이트만)
_ALLOWLIST = (
    "https://example.com",
    "https://www.wikipedia.org",
    "https://www.python.org",
)

# read-only allow action
_ALLOWED_READONLY_ACTIONS = frozenset(
    (
        "open_url",
        "read_page",
        "extract_text",
        "extract_metadata",
    )
)

# 차단 액션
_BLOCKED_LIVE_ACTIONS = frozenset(
    (
        "login",
        "type_password",
        "submit_form",
        "cookie_export",
        "session_export",
        "storage_state_export",
        "token_export",
        "payment",
        "transfer",
        "bid_submit",
        "electronic_signature",
        "cert_password_input",
        "otp_input",
        "download_file_execute",
        "click_submit",
    )
)

# 결과 허용 필드
_ALLOWED_RESULT_FIELDS = frozenset(
    (
        "url",
        "final_url",
        "reachable",
        "title",
        "text_excerpt",
        "links_count",
        "table_count",
        "download_candidate_count",
        "blocked_sensitive_actions",
        "server_browser_used",
        "cookie_exported",
        "session_exported",
        "storage_state_exported",
        "password_collected",
        "otp_collected",
        "certificate_password_collected",
        "redaction_applied",
        "verdict",
        "error_category",
        "duration_ms",
    )
)

# 7개 safe field 항상 False
_SAFE_FIELDS = (
    "cookie_exported",
    "session_exported",
    "password_collected",
    "otp_collected",
    "certificate_password_collected",
    "storage_state_exported",
    "server_browser_used",
)


def _is_local_execution() -> bool:
    """현재 실행 환경이 로컬 PC인지 확인 (서버 컨테이너 차단)."""
    # docker container indicator
    if Path("/.dockerenv").exists():
        return False
    # systemd-detect-virt 같은 신호 (linux)
    if sys.platform.startswith("linux"):
        try:
            with Path("/proc/1/cgroup").open(encoding="utf-8") as f:
                content = f.read()
            if "docker" in content or "kubepods" in content:
                return False
        except Exception:  # noqa: BLE001 - 로컬 에이전트 외부 readonly smoke 테스트 - CDP 평가 실패 시 timeout/None 반환
            pass
    # Windows/Mac은 일반적으로 로컬
    return True


def _is_allowlisted(url: str) -> bool:
    if not url:
        return False
    url_clean = url.rstrip("/")
    for allowed in _ALLOWLIST:
        if url_clean == allowed.rstrip("/") or url_clean.startswith(allowed + "/"):
            return True
    return False


def _sanitize_result(raw: dict[str, Any]) -> dict[str, Any]:
    """허용 필드만 남기고, safe field 강제 False, redaction 적용."""
    safe: dict[str, Any] = {}
    for key, value in raw.items():
        if key in _ALLOWED_RESULT_FIELDS:
            safe[key] = value
    for f in _SAFE_FIELDS:
        safe[f] = False
    safe["redaction_applied"] = True
    return safe


def _classify_blocked_action_payloads() -> list[dict[str, Any]]:
    """민감 동작 차단 검증 (실제 실행 없이 정책 분류만)."""
    from ai_orchestrator.contracts.action_risk_policy import (
        GRADE_BLOCKED,
        GRADE_USER_DIRECT,
        classify_action,
    )

    sensitive_actions = [
        "login_password_input",
        "otp_input",
        "cert_password_input",
        "cookie_export",
        "session_export",
        "storage_state_export",
        "token_export",
        "confirm_payment",
        "auto_payment",
        "transfer_money",
        "auto_bid_submit",
        "bid_final_submit",
        "auto_sign",
        "e_sign",
    ]
    out = []
    for action in sensitive_actions:
        grade = classify_action(action)
        is_blocked_or_user_direct = grade in (GRADE_BLOCKED, GRADE_USER_DIRECT)
        out.append(
            {
                "action": action,
                "grade": grade,
                "blocked_or_user_direct": is_blocked_or_user_direct,
            }
        )
    return out


def smoke_one(url: str) -> dict[str, Any]:
    """단일 URL read-only smoke."""
    task_id = str(uuid.uuid4())  # noqa: F841
    started = datetime.now(UTC)

    if not _is_allowlisted(url):
        return _sanitize_result(
            {
                "url": url,
                "reachable": False,
                "verdict": "BLOCKED_NOT_ALLOWLISTED",
                "error_category": "ALLOWLIST_VIOLATION",
            }
        )

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return _sanitize_result(
            {
                "url": url,
                "reachable": False,
                "verdict": "PLAYWRIGHT_NOT_AVAILABLE",
                "error_category": "PLAYWRIGHT_MISSING",
            }
        )

    raw: dict[str, Any] = {
        "url": url,
        "blocked_sensitive_actions": [],
        "verdict": "UNKNOWN",
    }
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                # 쿠키/storage 저장 안 함 (메모리 only context — 종료 시 자동 폐기)
            )
            page = context.new_page()
            try:
                page.goto(url, timeout=20000, wait_until="domcontentloaded")
                raw["final_url"] = page.url
                raw["reachable"] = True
                raw["title"] = (page.title() or "")[:120]

                try:
                    body = page.inner_text("body")[:500]
                except Exception:  # noqa: BLE001 - 로컬 에이전트 외부 readonly smoke 테스트 - CDP 평가 실패 시 timeout/None 반환
                    body = ""
                raw["text_excerpt"] = body

                try:
                    raw["links_count"] = len(page.query_selector_all("a"))
                    raw["table_count"] = len(page.query_selector_all("table"))
                    # 다운로드 후보: a[href]에 .pdf/.xlsx/.zip 등 포함
                    candidates = 0
                    for a in page.query_selector_all("a[href]"):
                        href = (a.get_attribute("href") or "").lower()
                        if any(
                            href.endswith(ext) for ext in (".pdf", ".xlsx", ".zip", ".exe", ".msi", ".doc", ".docx")
                        ):
                            candidates += 1
                    raw["download_candidate_count"] = candidates
                except Exception:  # noqa: BLE001 - 로컬 에이전트 외부 readonly smoke 테스트 - CDP 평가 실패 시 timeout/None 반환
                    raw["links_count"] = 0
                    raw["table_count"] = 0
                    raw["download_candidate_count"] = 0

                raw["verdict"] = "OK_READONLY"
            except Exception as e:  # noqa: BLE001 - 로컬 에이전트 외부 readonly smoke 테스트 - CDP 평가 실패 시 timeout/None 반환
                raw["reachable"] = False
                raw["verdict"] = "NETWORK_ERROR_OR_TIMEOUT"
                raw["error_category"] = type(e).__name__
            finally:
                # 명시적으로 cookie/storage 추출 안 함
                browser.close()

    except Exception as e:  # noqa: BLE001 - 로컬 에이전트 외부 readonly smoke 테스트 - CDP 평가 실패 시 timeout/None 반환
        raw["reachable"] = False
        raw["verdict"] = "PLAYWRIGHT_LAUNCH_ERROR"
        raw["error_category"] = type(e).__name__

    finished = datetime.now(UTC)
    raw["duration_ms"] = int((finished - started).total_seconds() * 1000)
    return _sanitize_result(raw)


def run_full_smoke(write_report: bool = True) -> dict[str, Any]:
    """allowlist 3개 URL 직렬 실행 + 차단 검증."""
    if not _is_local_execution():
        return {
            "verdict": "BLOCKED_NOT_LOCAL_EXECUTION",
            "message": "이 스크립트는 로컬 PC에서만 실행 가능합니다 (docker/server 환경 감지됨)",
            **dict.fromkeys(_SAFE_FIELDS, False),
        }

    print("=" * 60)
    print("LOCAL_AGENT_PUBLIC_EXTERNAL_READONLY_LIVE_SMOKE_1")
    print("=" * 60)
    print(f"실행 호스트: {socket.gethostname()} / {platform.system()} {platform.release()}")
    print(f"시작 시각: {datetime.now(UTC).isoformat()}")
    print()

    results: list[dict[str, Any]] = []
    for url in _ALLOWLIST:
        print(f"[smoke] {url}")
        r = smoke_one(url)
        results.append(r)
        verdict = r.get("verdict", "")
        title = r.get("title", "")[:60]
        ext = (r.get("text_excerpt", "") or "")[:80].replace("\n", " ")
        print(f"  verdict={verdict} | title={title} | excerpt={ext}")
        print(
            f"  links={r.get('links_count')} | tables={r.get('table_count')} | downloads={r.get('download_candidate_count')}"
        )
        print(f"  server_browser_used={r.get('server_browser_used')} | cookie_exported={r.get('cookie_exported')}")
        print()

    print("=" * 60)
    print("민감 동작 정책 분류 검증 (실제 실행 없음)")
    print("=" * 60)
    blocked_check = _classify_blocked_action_payloads()
    for c in blocked_check:
        flag = "PASS" if c["blocked_or_user_direct"] else "FAIL"
        print(f"  [{flag}] {c['action']} → {c['grade']}")

    summary = {
        "task_id": str(uuid.uuid4()),
        "executed_at": datetime.now(UTC).isoformat(),
        "executed_on_local": True,
        "host": socket.gethostname(),
        "allowlist": list(_ALLOWLIST),
        "results": results,
        "blocked_action_check": blocked_check,
        "all_blocked_or_user_direct": all(c["blocked_or_user_direct"] for c in blocked_check),
        **dict.fromkeys(_SAFE_FIELDS, False),
    }

    if write_report:
        report_dir = Path(_REPO_ROOT) / "data" / "reports" / "local_agent"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = (
            report_dir
            / f"local_agent_public_external_readonly_live_smoke_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        with report_path.open("w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        print()
        print(f"[리포트 저장] {os.path.relpath(report_path, _REPO_ROOT)}")

    return summary


def main():
    summary = run_full_smoke(write_report=True)
    reachable = sum(1 for r in summary["results"] if r.get("reachable"))
    print()
    print("=" * 60)
    print(f"결과: {reachable}/{len(summary['results'])} reachable")
    print(f"민감 동작 모두 차단 분류: {summary['all_blocked_or_user_direct']}")
    print(f"server_browser_used: {summary['server_browser_used']}")
    print("=" * 60)


if __name__ == "__main__":
    main()
