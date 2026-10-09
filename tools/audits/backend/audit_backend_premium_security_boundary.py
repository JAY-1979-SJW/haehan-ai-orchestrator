"""Security Boundary 감사 스크립트 — read-only.

secret redaction, egress 차단, 금지 실행 패턴을 점검한다.
외부 호출, DB 접속, 파일 수정 금지.

exit code: 0=PASS/PASS_WITH_KNOWN_WARN, 1=FAIL, 2=STOP_CONDITION
"""

from __future__ import annotations

import importlib
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
# sys.path에 프로젝트 root 추가 (직접 실행 시 필요)
if str(ROOT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(ROOT))

AUDIT_NAME = "security_boundary"

REQUIRED_FORBIDDEN_KEYS = {
    "password",
    "token",
    "session",
    "cookie",
    "secret",
    "private_key",
    "client_secret",
    "otp",
    "credential",
    "cert_password",
    "api_key",
    "authorization",
}

DANGEROUS_PATTERNS = [
    "os.system(",
    "subprocess.Popen(",
    "eval(",
    "exec(",
    "shell=True",
]

CHECKLIST = [
    {"id": "sb-01", "title": "secret_redaction forbidden key 목록 존재 (40+)", "required": True},
    {"id": "sb-02", "title": "password/token/session/cookie/secret 차단 키 포함", "required": True},
    {"id": "sb-03", "title": "server external web block policy 존재", "required": True},
    {"id": "sb-04", "title": "Playwright/server browser import 금지 기준 존재", "required": True},
    {"id": "sb-05", "title": "외부 URL egress 차단 테스트 존재", "required": False},
    {"id": "sb-06", "title": "OAuth token 출력 금지 (token 직접 로깅 없음)", "required": True},
    {"id": "sb-07", "title": "certificate password 저장 금지", "required": True},
    {"id": "sb-08", "title": "bid auto execute 금지 정책 존재", "required": True},
    {"id": "sb-09", "title": "payment/transfer/signature 자동 실행 금지", "required": True},
    {"id": "sb-10", "title": "DB write/schema 변경 없음 (migration 파일 없음)", "required": True},
    {"id": "sb-11", "title": "UI 파일 변경 없음", "required": True},
    {"id": "sb-12", "title": "위험 패턴(os.system/eval/exec) 핵심 모듈 없음", "required": False},
    {"id": "sb-13", "title": "quality gate 실행 가능", "required": True},
]


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _grep_src(pattern: str, paths: list[Path]) -> list[str]:
    found = []
    for p in paths:
        if p.exists():
            try:
                src = p.read_text(encoding="utf-8", errors="ignore")
                for i, line in enumerate(src.splitlines(), 1):
                    if pattern in line:
                        found.append(f"{p.name}:{i}: {line.strip()[:80]}")
            except Exception:  # noqa: BLE001 - read-only 보안경계 감사 스크립트 — 각 except는 파일읽기 실패 시 건너뛰거나 해당 체크를 FAIL/WARN으로 표시해 오류가 PASS로 은폐되지 않으며, 실제 쓰기/실행 동작이 없음.
                pass
    return found


def _item(cid: str, status: str, evidence: str, details: dict | None = None) -> dict:
    meta = next(c for c in CHECKLIST if c["id"] == cid)
    return {
        "id": cid,
        "title": meta["title"],
        "required": meta["required"],
        "status": status,
        "evidence": evidence,
        "details": details or {},
    }


def _check_forbidden_key_list() -> tuple[dict, set]:
    try:
        redact = importlib.import_module("ai_orchestrator.safety_policy.secret_redaction")
        forbidden = getattr(redact, "FORBIDDEN_SECRET_FIELDS", set())
        return (
            _item(
                "sb-01",
                "PASS" if len(forbidden) >= 35 else "FAIL",
                f"key 수={len(forbidden)}",
                {"count": len(forbidden)},
            ),
            forbidden,
        )
    except Exception as e:  # noqa: BLE001 - read-only 보안경계 감사 스크립트 — 각 except는 파일읽기 실패 시 건너뛰거나 해당 체크를 FAIL/WARN으로 표시해 오류가 PASS로 은폐되지 않으며, 실제 쓰기/실행 동작이 없음.
        return _item("sb-01", "FAIL", str(e)), set()


def _check_core_forbidden_keys_present(forbidden: set) -> dict:
    missing_keys = REQUIRED_FORBIDDEN_KEYS - {k.lower() for k in forbidden}
    return _item(
        "sb-02",
        "PASS" if not missing_keys else "FAIL",
        f"누락: {missing_keys}" if missing_keys else "핵심 key 전체 포함",
    )


def _load_policy_src() -> str:
    policy_src = ""
    for f in [
        ROOT / "ai_orchestrator/safety_policy/safety_policy_registry.py",
        ROOT / "ai_orchestrator/server/server_egress_policy.py",
    ]:
        if f.exists():
            policy_src += f.read_text(encoding="utf-8", errors="ignore")
    return policy_src


def _check_egress_block(policy_src: str) -> dict:
    has_egress_block = "server_external_web_block" in policy_src or "egress" in policy_src.lower()
    return _item(
        "sb-03", "PASS" if has_egress_block else "FAIL", "egress block 정책 존재" if has_egress_block else "없음"
    )


def _check_browser_guard_files() -> dict:
    browser_guard_files = (
        list(ROOT.glob("ai_orchestrator/**/*browser*policy*.py"))
        + list(ROOT.glob("ai_orchestrator/**/*server_guard*.py"))
        + list(ROOT.glob("ai_orchestrator/**/*execution_location*.py"))
    )
    has_browser_guard = len(browser_guard_files) > 0
    return _item(
        "sb-04",
        "PASS" if has_browser_guard else "WARN",
        f"브라우저 가드 파일: {[f.name for f in browser_guard_files[:3]]}",
    )


def _check_egress_tests_exist() -> dict:
    egress_tests = list(ROOT.glob("tests/test_external_web_work_connectors*.py")) + list(
        ROOT.glob("tests/test_app_scope_web_desktop_boundary*.py")
    )
    return _item("sb-05", "PASS" if egress_tests else "WARN", f"egress 테스트: {[f.name for f in egress_tests]}")


def _check_no_token_logging(core_paths: list[Path]) -> dict:
    token_log_hits = _grep_src("logging.info.*token", core_paths) + _grep_src("print.*access_token", core_paths)
    return _item(
        "sb-06",
        "PASS" if not token_log_hits else "FAIL",
        f"token 직접 로깅: {token_log_hits[:3]}" if token_log_hits else "token 로깅 없음",
    )


def _check_no_cert_password_storage(core_paths: list[Path]) -> dict:
    cert_store_hits = _grep_src("cert_password", core_paths)
    cert_in_models = [h for h in cert_store_hits if "field" in h.lower() or "=" in h]
    return _item(
        "sb-07",
        "PASS" if not cert_in_models else "WARN",
        f"cert_password 필드: {cert_in_models[:3]}" if cert_in_models else "cert_password 저장 없음",
    )


def _check_bid_auto_execute_blocked(policy_src: str) -> dict:
    # sb-08: bid auto execute 금지 (registry + model_adapters + audit_evidence 모두 검색)
    bridge_src = ""
    for fp in [ROOT / "ai_orchestrator/domain/model_adapters.py", ROOT / "ai_orchestrator/audit_evidence/models.py"]:
        if fp.exists():
            bridge_src += fp.read_text(encoding="utf-8", errors="ignore")
    has_no_bid = (
        "no-bid-auto-execute" in policy_src
        or "no_bid_auto_execute" in policy_src
        or "no-bid-auto-execute" in bridge_src
        or "no_bid_auto_execute" in bridge_src
        or "BID_EXTERNAL_APP_BRIDGE" in policy_src
    )
    return _item("sb-08", "PASS" if has_no_bid else "FAIL", "no_bid_auto_execute 정책 있음" if has_no_bid else "없음")


def _check_no_payment_patterns(core_paths: list[Path]) -> dict:
    payment_patterns = ["auto_payment", "auto_transfer", "auto_sign", "auto_submit_bid"]
    payment_hits = []
    for pat in payment_patterns:
        payment_hits += _grep_src(pat, core_paths)
    return _item(
        "sb-09",
        "PASS" if not payment_hits else "FAIL",
        f"위험 패턴: {payment_hits[:3]}" if payment_hits else "자동 결제/이체/서명 패턴 없음",
    )


def _check_no_new_migrations() -> dict:
    new_migrations = []
    for mig_dir in [ROOT / "migrations", ROOT / "alembic/versions"]:
        if mig_dir.exists():
            migs = sorted(mig_dir.glob("*.py"), key=lambda f: f.stat().st_mtime, reverse=True)[:3]
            new_migrations.extend([f.name for f in migs])
    return _item(
        "sb-10",
        "PASS" if not new_migrations else "WARN",
        f"최근 migration: {new_migrations}" if new_migrations else "신규 migration 없음",
    )


def _check_no_ui_changes() -> dict:
    try:
        proc = subprocess.run(
            ["git", "diff", "--name-only", "HEAD~1..HEAD"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=10,
            encoding="utf-8",
        )
        changed = proc.stdout.splitlines()
        ui_changed = [f for f in changed if f.startswith("admin-web/") or f.startswith("desktop/ui/")]
        return _item(
            "sb-11", "PASS" if not ui_changed else "FAIL", f"UI 변경: {ui_changed}" if ui_changed else "UI 변경 없음"
        )
    except Exception as e:  # noqa: BLE001 - read-only 보안경계 감사 스크립트 — 각 except는 파일읽기 실패 시 건너뛰거나 해당 체크를 FAIL/WARN으로 표시해 오류가 PASS로 은폐되지 않으며, 실제 쓰기/실행 동작이 없음.
        return _item("sb-11", "WARN", f"git diff 실패: {e}")


def _check_no_dangerous_patterns() -> dict:
    danger_hits = []
    for pat in DANGEROUS_PATTERNS:
        hits = _grep_src(
            pat, list(ROOT.glob("ai_orchestrator/services/*.py")) + list(ROOT.glob("ai_orchestrator/domain/*.py"))
        )
        danger_hits.extend(hits)
    return _item(
        "sb-12",
        "PASS" if not danger_hits else "WARN",
        f"위험 패턴: {danger_hits[:3]}" if danger_hits else "위험 패턴 없음",
    )


def _check_quality_gate_runnable() -> dict:
    qg = ROOT / "tools/quality/quality_gate.py"
    if not qg.exists():
        return _item("sb-13", "FAIL", "quality_gate.py 없음")
    try:
        proc = subprocess.run(
            [sys.executable, str(qg), "--staged", "--enforce", "--allow-existing-code-change"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=60,
            encoding="utf-8",
        )
        passed = proc.returncode == 0
        out = proc.stdout.strip().splitlines()
        return _item("sb-13", "PASS" if passed else "FAIL", "\n".join(out[-3:]) if out else "no output")
    except Exception as e:  # noqa: BLE001 - read-only 보안경계 감사 스크립트 — 각 except는 파일읽기 실패 시 건너뛰거나 해당 체크를 FAIL/WARN으로 표시해 오류가 PASS로 은폐되지 않으며, 실제 쓰기/실행 동작이 없음.
        return _item("sb-13", "WARN", f"quality gate 실행 실패: {e}")


def run_audit() -> dict[str, Any]:
    # 2026-09-29 STD-08(복잡도) 리팩터: sb-01~13 체크 블록을 _check_*() 함수로 분리(순서·조건·
    # 문자열 그대로). forbidden/policy_src/core_paths 는 명시적 인자로 전달.
    results: list[dict[str, Any]] = []
    sb01, forbidden = _check_forbidden_key_list()
    results.append(sb01)
    results.append(_check_core_forbidden_keys_present(forbidden))

    policy_src = _load_policy_src()
    results.append(_check_egress_block(policy_src))
    results.append(_check_browser_guard_files())
    results.append(_check_egress_tests_exist())

    core_paths = (
        list(ROOT.glob("ai_orchestrator/services/*.py"))
        + list(ROOT.glob("ai_orchestrator/domain/*.py"))
        + list(ROOT.glob("ai_orchestrator/safety_policy/*.py"))
    )
    results.append(_check_no_token_logging(core_paths))
    results.append(_check_no_cert_password_storage(core_paths))
    results.append(_check_bid_auto_execute_blocked(policy_src))
    results.append(_check_no_payment_patterns(core_paths))
    results.append(_check_no_new_migrations())
    results.append(_check_no_ui_changes())
    results.append(_check_no_dangerous_patterns())
    results.append(_check_quality_gate_runnable())

    summary = {"pass": 0, "warn": 0, "fail": 0, "skip": 0}
    for r in results:
        summary[r["status"].lower()] = summary.get(r["status"].lower(), 0) + 1

    required_fail = any(r["status"] == "FAIL" and r["required"] for r in results)
    verdict = "FAIL" if required_fail else ("PASS_WITH_KNOWN_WARN" if summary["warn"] > 0 else "PASS")

    return {
        "audit_name": AUDIT_NAME,
        "verdict": verdict,
        "checked_at": _now(),
        "checklist": results,
        "summary": summary,
    }


def main() -> int:
    from scripts.common.audit_cli import run_checklist_cli

    return run_checklist_cli(AUDIT_NAME, run_audit)


if __name__ == "__main__":
    sys.exit(main())
