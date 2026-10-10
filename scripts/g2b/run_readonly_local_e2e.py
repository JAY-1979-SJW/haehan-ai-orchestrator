"""
나라장터 read-only 로컬 E2E 실행 스크립트

공통 LOCAL_PLAYWRIGHT task protocol만 사용한다.
g2b 전용 브라우저 조작 로직 없음.
서버 외부 브라우저 실행 없음.

허용:
- 공개 홈페이지 read-only 접속
- title/text/table 추출
- 로그인/인증/OTP 감지 (자동 입력 없음)
- 다운로드 후보 감지 (dry-run, 자동 다운로드 없음)
- safe result / safe manifest 생성

금지:
- 비밀번호 자동 입력
- OTP 자동 입력
- 인증서 비밀번호 자동 입력
- cookie/session/token export
- submit/sign/payment/bid 실행
- 인증서/NPKI 파일 접근
- 실제 파일 다운로드 (dry-run만)

사용:
  python scripts/local_agent/run_g2b_readonly_local_e2e.py
"""

from __future__ import annotations

import datetime
import json
import pathlib
import sys

_BOOTSTRAP_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
if str(_BOOTSTRAP_ROOT) not in sys.path:
    sys.path.insert(0, str(_BOOTSTRAP_ROOT))

from scripts.common.app_paths import repo_root as _repo_root  # noqa: E402

_REPO_ROOT = _repo_root()

from ai_orchestrator.contracts.local_task_protocol import (  # noqa: E402
    STATUS_FAILED,
    STATUS_USER_ACTION_REQUIRED,
    STATUS_WAITING_USER_AUTH,
    build_task,
)
from core.agent_runtime.runtime.download.download_upload_manifest import build_manifest  # noqa: E402
from core.agent_runtime.runtime.local_session_boundary import enforce_session_boundary  # noqa: E402
from core.agent_runtime.runtime.playwright.playwright_bootstrap import (  # noqa: E402
    PLAYWRIGHT_READY,
    check_playwright_status,
)
from core.agent_runtime.runtime.result_sanitizer import sanitize_result  # noqa: E402

# ── 설정 ──────────────────────────────────────────────────────────────────────

G2B_HOME_URL = "https://www.g2b.go.kr/"
G2B_HOST = "www.g2b.go.kr"
TASK_ID = "g2b-readonly-e2e-20260508-001"
TIMEOUT_SEC = 30

_REPORT_DIR = pathlib.Path(_REPO_ROOT) / "data" / "reports" / "g2b"


def _build_g2b_task(action: str, url: str = G2B_HOME_URL) -> dict:
    return build_task(
        action=action,
        target_url=url,
        domain=G2B_HOST,
        readonly=True,
        requires_user_presence=False,
        timeout_seconds=TIMEOUT_SEC,
        task_id=TASK_ID,
        metadata={"source": "g2b_readonly_e2e_20260508"},
    )


def _safe_result(result: dict) -> dict:
    sanitized = sanitize_result(result)
    return enforce_session_boundary(sanitized)


def _check_dangerous_state(result: dict) -> str | None:
    """위험 상태 감지. 감지되면 이유 반환, 없으면 None."""
    status = result.get("status", "")  # noqa: F841
    # 위험 작업이 자동 실행된 흔적 검사
    if result.get("auto_submit_triggered"):
        return "FAIL: auto_submit_triggered"
    if result.get("auto_sign_triggered"):
        return "FAIL: auto_sign_triggered"
    if result.get("auto_payment_triggered"):
        return "FAIL: auto_payment_triggered"
    if result.get("auto_bid_triggered"):
        return "FAIL: auto_bid_triggered"
    if result.get("cookie_exported"):
        return "FAIL: cookie_exported"
    if result.get("session_exported"):
        return "FAIL: session_exported"
    if result.get("password_collected"):
        return "FAIL: password_collected"
    if result.get("otp_collected"):
        return "FAIL: otp_collected"
    if result.get("certificate_password_collected"):
        return "FAIL: certificate_password_collected"
    return None


def _run_e2e() -> dict:
    from core.agent_runtime.runtime.playwright.playwright_runner import run_task

    report: dict = {
        "run_at": datetime.datetime.now(tz=datetime.UTC).isoformat(),
        "task_id": TASK_ID,
        "target_url": G2B_HOME_URL,
        "target_host": G2B_HOST,
        "execution_mode": "LOCAL_PLAYWRIGHT",
        "server_browser_used": False,
        "steps": [],
        "final_status": None,
        "safe_result": None,
        "manifest": None,
        "dangerous_state": None,
        "policy_violations": [],
    }

    steps = report["steps"]

    # ── STEP A: read_page ────────────────────────────────────────────────────
    print(f"[A] read_page → {G2B_HOME_URL}")
    task = _build_g2b_task("read_page")
    raw = run_task(task)
    safe = _safe_result(raw)

    danger = _check_dangerous_state(safe)
    if danger:
        report["dangerous_state"] = danger
        report["final_status"] = "FAIL_STOP"
        return report

    step_a = {
        "step": "read_page",
        "status": safe.get("status"),
        "title_hint": safe.get("title_hint", ""),
        "current_url_host": safe.get("current_url_host", ""),
        "body_text_sample": (safe.get("extracted_data") or {}).get("body_text_sample", "")[:200],
        "auth_signal": (safe.get("extracted_data") or {}).get("auth_signal"),
        "message_ko": safe.get("message_ko", ""),
        "sensitive_data_collected": safe.get("sensitive_data_collected"),
        "cookie_exported": safe.get("cookie_exported"),
        "session_exported": safe.get("session_exported"),
    }
    steps.append(step_a)
    print(f"    → status={step_a['status']} title={step_a['title_hint']!r}")

    status = safe.get("status")
    if status in (STATUS_WAITING_USER_AUTH, STATUS_USER_ACTION_REQUIRED):
        print(f"    → 인증 필요 감지: {step_a['auth_signal']}. WARN (정상 동작).")
        report["final_status"] = "WARN_AUTH_REQUIRED"
        report["safe_result"] = safe
        _write_manifest(report, task_id=TASK_ID, downloaded_files=[])
        return report

    if status == STATUS_FAILED:
        print(f"    → 접속 실패: {safe.get('message_ko', '')}. WARN.")
        report["final_status"] = "WARN_CONNECT_FAILED"
        report["safe_result"] = safe
        return report

    # ── STEP B: extract_text ─────────────────────────────────────────────────
    print("[B] extract_text")
    task_b = _build_g2b_task("extract_text")
    raw_b = run_task(task_b)
    safe_b = _safe_result(raw_b)
    step_b = {
        "step": "extract_text",
        "status": safe_b.get("status"),
        "text_sample": (safe_b.get("extracted_data") or {}).get("text", "")[:200],
    }
    steps.append(step_b)
    print(f"    → status={step_b['status']} text_len={len(step_b['text_sample'])}")

    danger = _check_dangerous_state(safe_b)
    if danger:
        report["dangerous_state"] = danger
        report["final_status"] = "FAIL_STOP"
        return report

    # ── STEP C: extract_table ────────────────────────────────────────────────
    print("[C] extract_table")
    task_c = _build_g2b_task("extract_table")
    raw_c = run_task(task_c)
    safe_c = _safe_result(raw_c)
    step_c = {
        "step": "extract_table",
        "status": safe_c.get("status"),
        "table_rows_count": len((safe_c.get("extracted_data") or {}).get("table_rows", [])),
    }
    steps.append(step_c)
    print(f"    → status={step_c['status']} rows={step_c['table_rows_count']}")

    danger = _check_dangerous_state(safe_c)
    if danger:
        report["dangerous_state"] = danger
        report["final_status"] = "FAIL_STOP"
        return report

    # ── STEP D: detect_login_status ─────────────────────────────────────────
    print("[D] detect_login_status")
    task_d = _build_g2b_task("detect_login_status")
    raw_d = run_task(task_d)
    safe_d = _safe_result(raw_d)
    step_d = {
        "step": "detect_login_status",
        "status": safe_d.get("status"),
        "auth_signal": (safe_d.get("extracted_data") or {}).get("auth_signal"),
    }
    steps.append(step_d)
    print(f"    → status={step_d['status']} auth_signal={step_d['auth_signal']}")

    # ── STEP E: download manifest dry-run ────────────────────────────────────
    print("[E] download manifest dry-run (실제 다운로드 없음)")
    # 실제 첨부 링크 추출 없이 정책 검증만 수행
    sample_candidates = [
        {"filename": "입찰공고문.pdf", "size_bytes": 51200},
        {"filename": "첨부서류.hwpx", "size_bytes": 20480},
        {"filename": "cert.pfx", "size_bytes": 4096},  # 차단 대상
        {"filename": "setup.exe", "size_bytes": 1024000},  # 차단 대상
    ]
    manifest = build_manifest(
        task_id=TASK_ID,
        downloaded_files=sample_candidates,
        task_downloaded_filenames=[str(f["filename"]) for f in sample_candidates],
    )
    step_e = {
        "step": "download_manifest_dry_run",
        "total_files": manifest["total_files"],
        "allowed_count": manifest["allowed_count"],
        "blocked_count": manifest["blocked_count"],
        "certificate_file_detected": manifest["certificate_file_detected"],
        "sensitive_data_detected": manifest["sensitive_data_detected"],
    }
    steps.append(step_e)
    print(
        f"    → allowed={step_e['allowed_count']} blocked={step_e['blocked_count']} cert_detected={step_e['certificate_file_detected']}"
    )

    report["manifest"] = manifest
    report["safe_result"] = safe
    report["final_status"] = "PASS"
    return report


def _write_manifest(report: dict, task_id: str, downloaded_files: list) -> None:
    if not downloaded_files:
        report["manifest"] = {
            "task_id": task_id,
            "files": [],
            "sensitive_data_detected": False,
            "certificate_file_detected": False,
            "total_files": 0,
            "allowed_count": 0,
            "blocked_count": 0,
        }


def _save_report(report: dict) -> pathlib.Path:
    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = _REPORT_DIR / f"g2b_readonly_local_e2e_{ts}.json"
    with path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    return path


def main() -> None:
    print("=" * 60)
    print("나라장터 read-only 로컬 E2E 실행")
    print(f"target: {G2B_HOME_URL}")
    print("=" * 60)

    pw_status = check_playwright_status()
    if pw_status.get("status") != PLAYWRIGHT_READY:
        print(f"[WARN] Playwright 미설치: {pw_status}")
        report = {
            "run_at": datetime.datetime.now(tz=datetime.UTC).isoformat(),
            "task_id": TASK_ID,
            "target_url": G2B_HOME_URL,
            "target_host": G2B_HOST,
            "execution_mode": "LOCAL_PLAYWRIGHT",
            "server_browser_used": False,
            "final_status": "WARN_PLAYWRIGHT_NOT_INSTALLED",
            "playwright_status": pw_status,
            "steps": [],
            "dangerous_state": None,
            "safe_result": None,
            "manifest": None,
            "policy_violations": [],
        }
    else:
        try:
            report = _run_e2e()
        except Exception as exc:  # noqa: BLE001 - 나라장터(G2B) 읽기전용 e2e 스모크 테스트 - 실패 시 예외 정보를 보고서(report)에 기록만, 입찰/제출 등 쓰기 동작 없음
            report = {
                "run_at": datetime.datetime.now(tz=datetime.UTC).isoformat(),
                "task_id": TASK_ID,
                "target_url": G2B_HOME_URL,
                "target_host": G2B_HOST,
                "execution_mode": "LOCAL_PLAYWRIGHT",
                "server_browser_used": False,
                "final_status": f"WARN_EXCEPTION: {type(exc).__name__}: {str(exc)[:100]}",
                "steps": [],
                "dangerous_state": None,
                "safe_result": None,
                "manifest": None,
                "policy_violations": [],
            }

    if report.get("dangerous_state"):
        print(f"\n[FAIL STOP] 위험 상태 감지: {report['dangerous_state']}")
        sys.exit(2)

    path = _save_report(report)
    print(f"\n[결과] final_status={report['final_status']}")
    print(f"[리포트] {path}")

    if report["final_status"] == "PASS":
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
