from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
SESSION = ROOT / "scripts" / "common" / "ai_work_session.py"
STANDARD = ROOT / "docs" / "baseline" / "STANDARD_WORKFLOW.md"


def run(args: list[str], record_root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SESSION), "--record-root", str(record_root), "--lane", "audit-lane", *args],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
        timeout=30,
    )


def audit() -> tuple[bool, list[str]]:
    findings: list[str] = []
    ok = True
    if not SESSION.exists():
        return False, [f"[FAIL] missing ai work session helper: {SESSION}"]
    text = STANDARD.read_text(encoding="utf-8") if STANDARD.exists() else ""
    for token in [
        "AI Agent Work Record Rule",
        "Before a new AI session continues operational work",
        "data/runtime/ai_work_record_latest.json",
    ]:
        if token not in text:
            ok = False
            findings.append(f"[FAIL] standard workflow missing work record token: {token}")

    root = ROOT / "tmp" / "ai_work_session_gate" / uuid4().hex
    try:
        start = run(
            [
                "start",
                "--task-id",
                "audit-session",
                "--summary",
                "audit lane work session",
                "--scope",
                "docs/baseline/",
                "--next-step",
                "resume from audit record",
            ],
            root,
        )
        resume = run(["resume-check", "--json"], root)
        close = run(["close", "--verification", "audit passed", "--next-step", "inspect latest before new work"], root)
        latest = root / "audit-lane" / "latest.json"
        history = root / "audit-lane" / "history.jsonl"
        index = root / "latest_lane.json"
        if start.returncode != 0 or resume.returncode != 0 or close.returncode != 0:
            ok = False
            findings.append("[FAIL] ai work session start/resume/close command failed")
        elif not latest.exists() or not history.exists() or not index.exists():
            ok = False
            findings.append("[FAIL] ai work session did not write lane latest/history/index files")
        else:
            findings.append("[PASS] ai work session writes resumable lane records")
    finally:
        if root.exists():
            shutil.rmtree(root, ignore_errors=True)

    if ok:
        findings.append("[PASS] AI work session gate is ready")
    return ok, findings


def main() -> int:
    ok, findings = audit()
    for finding in findings:
        print(finding)
    print("RESULT=" + ("PASS_AI_WORK_SESSION_GATE" if ok else "FAIL_AI_WORK_SESSION_GATE"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
