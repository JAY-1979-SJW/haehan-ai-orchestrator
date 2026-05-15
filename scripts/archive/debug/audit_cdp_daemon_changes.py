#!/usr/bin/env python3
"""CDP 데몬 변경사항 포괄 감사 스크립트 v1.0

감사 영역:
  1. 보안 — 위험 패턴 검사
  2. 모듈 의존성 — import 구조 검증
  3. 스키마 일관성 — PopupEvent 사용
  4. 게이트 적용 — 위험 등급 일치
  5. 프로세스 격리 — subprocess 격리 검증
  6. 코드 품질 — 복잡도, 줄 수

실행:
  python scripts/audit_cdp_daemon_changes.py
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

# ── 감사 결과 저장 ──────────────────────────────────────────────────
AUDIT_REPORT = ROOT / "data" / "audit_cdp_daemon_changes.json"

audit_result = {
    "timestamp": __import__("datetime").datetime.now().isoformat(),
    "sections": {},
    "issues": [],
    "status": "PASS",
}


def log_issue(section: str, severity: str, message: str, file: str = "", line: int = 0) -> None:
    """감사 이슈 기록."""
    issue = {
        "section": section,
        "severity": severity,
        "message": message,
        "file": file,
        "line": line,
    }
    audit_result["issues"].append(issue)
    if severity == "FAIL":
        audit_result["status"] = "FAIL"
    elif severity == "WARN" and audit_result["status"] != "FAIL":
        audit_result["status"] = "WARN"


# ── 1. 보안 감사 ────────────────────────────────────────────────────
def audit_security() -> None:
    """위험 패턴 정적 검사."""
    section = "SECURITY"
    audit_result["sections"][section] = {"checks": 0, "passed": 0, "failed": 0}

    files_to_check = [
        ROOT / "scripts" / "cdp_daemon.py",
        ROOT / "scripts" / "chrome_ui_monitor.py",
        ROOT / "scripts" / "cdp_client.py",
    ]

    dangerous_patterns = [
        (r"\beval\s*\(", "eval() 사용 금지", "FAIL"),
        (r"\bexec\s*\(", "exec() 사용 금지", "FAIL"),
        (r"os\.system\s*\(", "os.system() 사용 금지", "FAIL"),
        (r"shell\s*=\s*True", "shell=True 사용 금지", "FAIL"),
        (r"CREATE_NEW_PROCESS_GROUP", "프로세스 그룹 생성 검증", "INFO"),
        (r"subprocess\.Popen", "Popen 호출 검증", "INFO"),
    ]

    for fpath in files_to_check:
        if not fpath.exists():
            continue

        try:
            content = fpath.read_text(encoding="utf-8")
            lines = content.split("\n")
        except Exception as e:
            log_issue(section, "WARN", f"파일 읽기 실패: {fpath}", str(fpath))
            continue

        for pattern, desc, severity in dangerous_patterns:
            for i, line in enumerate(lines, 1):
                if re.search(pattern, line):
                    audit_result["sections"][section]["checks"] += 1
                    if severity == "FAIL":
                        log_issue(section, severity, f"{desc} (라인 {i})", str(fpath), i)
                        audit_result["sections"][section]["failed"] += 1
                    else:
                        audit_result["sections"][section]["passed"] += 1

    if audit_result["sections"][section]["failed"] == 0:
        audit_result["sections"][section]["passed"] += 1


# ── 2. 모듈 의존성 감사 ─────────────────────────────────────────────
def audit_dependencies() -> None:
    """import 구조 검증."""
    section = "DEPENDENCIES"
    audit_result["sections"][section] = {"imports": {}, "issues": 0}

    files_to_check = {
        "cdp_daemon.py": ROOT / "scripts" / "cdp_daemon.py",
        "chrome_ui_monitor.py": ROOT / "scripts" / "chrome_ui_monitor.py",
        "cdp_client.py": ROOT / "scripts" / "cdp_client.py",
    }

    expected_imports = {
        "cdp_daemon.py": ["subprocess", "threading", "json", "signal"],
        "chrome_ui_monitor.py": ["signal", "json", "scripts.chrome_ui_watcher", "scripts.popup_monitor"],
        "cdp_client.py": ["subprocess", "sys"],
    }

    for name, fpath in files_to_check.items():
        if not fpath.exists():
            continue

        try:
            tree = ast.parse(fpath.read_text(encoding="utf-8"))
            imports = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.add(alias.name.split(".")[0])
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imports.add(node.module.split(".")[0])

            audit_result["sections"][section]["imports"][name] = sorted(list(imports))

            # 순환 의존성 체크
            if name == "cdp_daemon.py" and "cdp_daemon" in imports:
                log_issue(section, "FAIL", "순환 의존성 감지: cdp_daemon이 자신을 import", name)
                audit_result["sections"][section]["issues"] += 1
            if name == "chrome_ui_monitor.py" and "chrome_ui_monitor" in imports:
                log_issue(section, "FAIL", "순환 의존성 감지: chrome_ui_monitor이 자신을 import", name)
                audit_result["sections"][section]["issues"] += 1
        except Exception as e:
            log_issue(section, "WARN", f"AST 파싱 실패: {e}", name)


# ── 3. 스키마 일관성 감사 ───────────────────────────────────────────
def audit_schema_consistency() -> None:
    """PopupEvent 스키마 사용 검증."""
    section = "SCHEMA"
    audit_result["sections"][section] = {"checks": 0, "passed": 0}

    # schemas.py에서 PopupEvent 정의 확인
    schemas_file = ROOT / "scripts" / "schemas.py"
    if schemas_file.exists():
        content = schemas_file.read_text(encoding="utf-8")
        if "class PopupEvent" in content:
            audit_result["sections"][section]["checks"] += 1
            audit_result["sections"][section]["passed"] += 1
        else:
            log_issue(section, "FAIL", "PopupEvent 타입 정의 없음", str(schemas_file))

    # popup_monitor.py에서 PopupEvent 사용 확인
    popup_monitor_file = ROOT / "scripts" / "popup_monitor.py"
    if popup_monitor_file.exists():
        content = popup_monitor_file.read_text(encoding="utf-8")
        if "_record_event" in content:
            audit_result["sections"][section]["checks"] += 1
            audit_result["sections"][section]["passed"] += 1


# ── 4. 게이트 적용 감사 ────────────────────────────────────────────
def audit_gate_consistency() -> None:
    """게이트 레지스트리와 실제 코드 일치도 검사."""
    section = "GATE"
    audit_result["sections"][section] = {"checks": 0, "passed": 0}

    gate_file = ROOT / "scripts" / "gate.py"
    if not gate_file.exists():
        log_issue(section, "FAIL", "gate.py 파일 없음", str(gate_file))
        return

    content = gate_file.read_text(encoding="utf-8")
    expected_gates = [
        "popup_detect",
        "popup_dismiss",
        "chrome_ui_detect",
        "chrome_ui_dismiss",
    ]

    for gate_name in expected_gates:
        audit_result["sections"][section]["checks"] += 1
        if f'"{gate_name}"' in content or f"'{gate_name}'" in content:
            audit_result["sections"][section]["passed"] += 1
        else:
            log_issue(section, "WARN", f"게이트 '{gate_name}' 미등록", str(gate_file))


# ── 5. 프로세스 격리 검증 ───────────────────────────────────────────
def audit_process_isolation() -> None:
    """독립 프로세스 격리 검증."""
    section = "PROCESS_ISOLATION"
    audit_result["sections"][section] = {"checks": 0, "passed": 0}

    cdp_daemon_file = ROOT / "scripts" / "cdp_daemon.py"
    if cdp_daemon_file.exists():
        content = cdp_daemon_file.read_text(encoding="utf-8")

        # chrome_ui_monitor 분리 확인
        audit_result["sections"][section]["checks"] += 1
        if "chrome_ui_monitor.py" in content and "_launch_background_python" in content:
            audit_result["sections"][section]["passed"] += 1
        else:
            log_issue(section, "FAIL", "chrome_ui_monitor 독립 프로세스 미분리", str(cdp_daemon_file))

        # ChromeUIWatcher 비활성화 확인
        audit_result["sections"][section]["checks"] += 1
        if "ChromeUIWatcher" in content and ("#" in content or "# " in content):
            # 주석 여부 확인
            if not re.search(r"^\s*from scripts.popup_monitor import ChromeUIWatcher", content, re.MULTILINE):
                audit_result["sections"][section]["passed"] += 1
            else:
                log_issue(section, "WARN", "ChromeUIWatcher가 여전히 활성화될 수 있음", str(cdp_daemon_file))
        else:
            audit_result["sections"][section]["passed"] += 1


# ── 6. 코드 품질 감사 ────────────────────────────────────────────
def audit_code_quality() -> None:
    """코드 라인 수 및 복잡도."""
    section = "CODE_QUALITY"
    audit_result["sections"][section] = {"files": {}}

    files_to_check = {
        "cdp_daemon.py": (ROOT / "scripts" / "cdp_daemon.py", 800),  # 최대 줄 수
        "chrome_ui_monitor.py": (ROOT / "scripts" / "chrome_ui_monitor.py", 300),
        "cdp_client.py": (ROOT / "scripts" / "cdp_client.py", 500),
    }

    for name, (fpath, max_lines) in files_to_check.items():
        if not fpath.exists():
            continue

        try:
            lines = fpath.read_text(encoding="utf-8").split("\n")
            line_count = len([l for l in lines if l.strip() and not l.strip().startswith("#")])

            audit_result["sections"][section]["files"][name] = {
                "lines": line_count,
                "max": max_lines,
                "status": "OK" if line_count <= max_lines else "WARN",
            }

            if line_count > max_lines:
                log_issue(section, "WARN", f"{name}: {line_count}줄 (권장: {max_lines}줄)", name)
        except Exception as e:
            log_issue(section, "WARN", f"파일 분석 실패: {e}", name)


# ── 실행 ────────────────────────────────────────────────────────────
def main() -> None:
    print("\n" + "=" * 70)
    print("  CDP 데몬 변경사항 포괄 감사")
    print("=" * 70)

    audit_security()
    print("✓ 보안 감사 완료")

    audit_dependencies()
    print("✓ 모듈 의존성 검증 완료")

    audit_schema_consistency()
    print("✓ 스키마 일관성 검사 완료")

    audit_gate_consistency()
    print("✓ 게이트 적용 검사 완료")

    audit_process_isolation()
    print("✓ 프로세스 격리 검증 완료")

    audit_code_quality()
    print("✓ 코드 품질 검사 완료")

    # 결과 저장
    AUDIT_REPORT.parent.mkdir(parents=True, exist_ok=True)
    AUDIT_REPORT.write_text(json.dumps(audit_result, ensure_ascii=False, indent=2), encoding="utf-8")

    # 결과 출력
    print("\n" + "=" * 70)
    print(f"  상태: {audit_result['status']}")
    print("=" * 70)

    if audit_result["issues"]:
        print(f"\n⚠️  {len(audit_result['issues'])}개 이슈 발견:\n")
        for issue in audit_result["issues"]:
            severity_icon = "❌" if issue["severity"] == "FAIL" else "⚠️ " if issue["severity"] == "WARN" else "ℹ️ "
            print(
                f"{severity_icon} [{issue['section']}] {issue['message']}"
                + (f" ({issue['file']}:{issue['line']})" if issue["file"] else "")
            )
    else:
        print("\n✅ 모든 감사 항목 통과!")

    print(f"\n📋 감사 보고서: {AUDIT_REPORT}")


if __name__ == "__main__":
    main()
