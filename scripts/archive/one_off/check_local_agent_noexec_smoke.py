"""
check_local_agent_noexec_smoke.py

No-exec static smoke check for local-agent control surface.
- File read only. No network calls, no subprocess, no docker, no POST.
- PASS/WARN: exit 0  |  FAIL: exit 1
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

results: list[tuple[str, str]] = []  # (level, message)


def check(level: str, msg: str) -> None:
    results.append((level, msg))
    print(f"[{level}] {msg}")


# ── A. 필수 파일 존재 ──────────────────────────────────────────────────────────

REQUIRED_FILES = [
    "ai_orchestrator/agent_hub/router/root.py",
    "tools/gates/approval.py",
    "tools/gates/policy.py",
    "ai_orchestrator/policies/default_policy.yaml",
    "ai_orchestrator/agent_hub/registry/facade.py",
    "admin-web/src/app/local-agents/LocalAgentsClient.tsx",
    "admin-web/src/lib/api.ts",
    "admin-web/src/types/local-agent.ts",
]

for rel in REQUIRED_FILES:
    p = REPO_ROOT / rel
    if p.exists():
        check("PASS", f"required file exists: {rel}")
    else:
        check("FAIL", f"required file MISSING: {rel}")


# ── B. approval UI marker ──────────────────────────────────────────────────────

UI_FILE = REPO_ROOT / "admin-web/src/app/local-agents/LocalAgentsClient.tsx"
API_FILE = REPO_ROOT / "admin-web/src/lib/api.ts"
TYPES_FILE = REPO_ROOT / "admin-web/src/types/local-agent.ts"

APPROVAL_MARKERS = [
    ("waiting_approval", UI_FILE, "FAIL"),
    ("approve", UI_FILE, "FAIL"),
    ("reject", UI_FILE, "FAIL"),
    ("token_id", TYPES_FILE, "FAIL"),
    ("승인 확인", UI_FILE, "FAIL"),
    ("거절 확인", UI_FILE, "FAIL"),
    ("approveLocalAgentTask", API_FILE, "FAIL"),
    ("rejectLocalAgentTask", API_FILE, "FAIL"),
    ("getLocalAgentTask", API_FILE, "WARN"),
]

for marker, file_path, severity in APPROVAL_MARKERS:
    if not file_path.exists():
        check("WARN", f"file not found, skipping marker '{marker}': {file_path.name}")
        continue
    text = file_path.read_text(encoding="utf-8", errors="replace")
    if marker in text:
        check("PASS", f"approval UI marker found: '{marker}' in {file_path.name}")
    else:
        check(severity, f"approval UI marker MISSING: '{marker}' in {file_path.name}")


# ── C. safety/policy marker ────────────────────────────────────────────────────

POLICY_FILE = REPO_ROOT / "ai_orchestrator/policies/default_policy.yaml"
APPROVAL_PY = REPO_ROOT / "tools/gates/approval.py"
ROUTER_PY = REPO_ROOT / "ai_orchestrator/agent_hub/router/root.py"

SAFETY_MARKERS = [
    ("dry_run", ROUTER_PY, "FAIL"),
    ("waiting_approval", ROUTER_PY, "FAIL"),
    ("approve", ROUTER_PY, "FAIL"),
    ("reject", ROUTER_PY, "FAIL"),
    ("critical", POLICY_FILE, "WARN"),
    ("audit", APPROVAL_PY, "WARN"),
    ("preview", ROUTER_PY, "WARN"),
]

for marker, file_path, severity in SAFETY_MARKERS:
    if not file_path.exists():
        check("WARN", f"file not found, skipping safety marker '{marker}': {file_path.name}")
        continue
    text = file_path.read_text(encoding="utf-8", errors="replace")
    if marker in text:
        check("PASS", f"safety marker found: '{marker}' in {file_path.name}")
    else:
        check(severity, f"safety marker MISSING: '{marker}' in {file_path.name}")


# ── D. 위험 POST — 스크립트 자체 확인 ─────────────────────────────────────────
# regex로 실제 import 문과 실제 호출 구문만 검사
# 상수 리스트 안의 문자열 리터럴은 제외 (따옴표로 시작하는 패턴 제외)

import re as _re  # noqa: E402 — 상단 상수 블록 이후 import (기존 구조 유지)

THIS_LINES = Path(__file__).read_text(encoding="utf-8", errors="replace").splitlines()

# import 레벨 검사: 실제 import 문 (줄 시작이 import/from)
_NET_MODS = ["requests", "httpx", "urllib"]
for _mod in _NET_MODS:
    _pat = _re.compile(r"^\s*(?:import|from)\s+" + _re.escape(_mod) + r"[\s.]")
    _hits = [ln for ln in THIS_LINES if _pat.match(ln)]
    if _hits:
        check("FAIL", f"this script imports forbidden module: {_mod!r}")
    else:
        check("PASS", f"no forbidden import of: {_mod!r}")

# subprocess / os.system 실제 호출 검사
# 문자열 리터럴 내부(따옴표 직전에 패턴이 있는 경우)는 제외
_CALL_PATS = [
    ("subprocess.run", _re.compile(r"(?<!['\"])subprocess\.run\s*\(")),
    ("subprocess.call", _re.compile(r"(?<!['\"])subprocess\.call\s*\(")),
    ("subprocess.Popen", _re.compile(r"(?<!['\"])subprocess\.Popen\s*\(")),
    ("os.system", _re.compile(r"(?<!['\"])os\.system\s*\(")),
]
for _name, _cpat in _CALL_PATS:
    _hits = [ln for ln in THIS_LINES if _cpat.search(ln) and not ln.strip().startswith("#")]
    if _hits:
        check("FAIL", f"this script contains forbidden call: {_name!r}")
    else:
        check("PASS", f"no forbidden call in script: {_name!r}")


# ── E. legacy URL 신규 노출 확인 ───────────────────────────────────────────────

ADMIN_WEB_SRC = REPO_ROOT / "admin-web/src"
LEGACY_PATTERN = "/api/v1/admin/local-agents"

if ADMIN_WEB_SRC.exists():
    found_legacy = []
    for ts_file in ADMIN_WEB_SRC.rglob("*.ts"):
        text = ts_file.read_text(encoding="utf-8", errors="replace")
        if LEGACY_PATTERN in text:
            found_legacy.append(str(ts_file.relative_to(REPO_ROOT)))
    for tsx_file in ADMIN_WEB_SRC.rglob("*.tsx"):
        text = tsx_file.read_text(encoding="utf-8", errors="replace")
        if LEGACY_PATTERN in text:
            found_legacy.append(str(tsx_file.relative_to(REPO_ROOT)))
    if found_legacy:
        for f in found_legacy:
            check("WARN", f"legacy URL '{LEGACY_PATTERN}' found in: {f}")
    else:
        check("PASS", f"no legacy URL '{LEGACY_PATTERN}' exposed in admin-web/src")
else:
    check("WARN", "admin-web/src directory not found, skipping legacy URL check")


# ── F. secret/cookie/session 위험 문자열 정적 확인 ────────────────────────────
# Authorization 헤더 직접 조립, document.cookie, sessionStorage, localStorage 무분별 사용 감지

SECRET_PATTERNS = [
    ("document.cookie", "FAIL"),
    ("sessionStorage", "WARN"),
    ("localStorage", "WARN"),
    # Authorization 헤더를 직접 문자열로 조립하는 패턴
    ('"Authorization"', "WARN"),
    ("'Authorization'", "WARN"),
]

if ADMIN_WEB_SRC.exists():
    all_src_files = list(ADMIN_WEB_SRC.rglob("*.ts")) + list(ADMIN_WEB_SRC.rglob("*.tsx"))
    for pattern, severity in SECRET_PATTERNS:
        hit_files = []
        for f in all_src_files:
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
                if pattern in text:
                    hit_files.append(f.name)
            except OSError:
                pass
        if hit_files:
            check(severity, f"secret-risk pattern '{pattern}' found in: {', '.join(hit_files[:5])}")
        else:
            check("PASS", f"no secret-risk pattern: '{pattern}'")
else:
    check("WARN", "admin-web/src directory not found, skipping secret pattern check")


# ── G. capture/cancel 코드 존재 (기존 기능 유지 확인) ─────────────────────────

EXISTING_MARKERS = [
    ("capture-screenshot", API_FILE, "WARN"),
    ("cancelTask", API_FILE, "WARN"),
]
for marker, file_path, severity in EXISTING_MARKERS:
    if not file_path.exists():
        check("WARN", f"file not found, skipping marker '{marker}'")
        continue
    text = file_path.read_text(encoding="utf-8", errors="replace")
    if marker in text:
        check("PASS", f"existing feature marker present: '{marker}' in {file_path.name}")
    else:
        check(severity, f"existing feature marker MISSING: '{marker}' in {file_path.name}")


# ── 최종 요약 ──────────────────────────────────────────────────────────────────

total = len(results)
passes = sum(1 for r in results if r[0] == "PASS")
warns = sum(1 for r in results if r[0] == "WARN")
fails = sum(1 for r in results if r[0] == "FAIL")

print()
print("=" * 60)
print(f"Total: {total}  PASS: {passes}  WARN: {warns}  FAIL: {fails}")

if fails > 0:
    print("Final: FAIL")
    sys.exit(1)
elif warns > 0:
    print("Final: WARN")
    sys.exit(0)
else:
    print("Final: PASS")
    sys.exit(0)
