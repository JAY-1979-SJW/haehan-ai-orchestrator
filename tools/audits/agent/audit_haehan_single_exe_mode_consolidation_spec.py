"""audit_haehan_single_exe_mode_consolidation_spec.py
HAEHAN_SINGLE_EXE_MODE_CONSOLIDATION_SPEC_01 감리.

판정:
  PASS_HAEHAN_SINGLE_EXE_MODE_CONSOLIDATION_SPEC
  WARN_AGENT_EXE_DEPRECATION_PENDING
  FAIL_TWO_APP_STRATEGY_REMAINS
  FAIL_TRAY_MODE_MISSING
  FAIL_ADMIN_MODE_MISSING
  FAIL_ROLE_GUARD_MISSING
  FAIL_DEPRECATED_PLAN_MISSING
  FAIL_SECURITY_POLICY_MISSING
  FAIL_NEXT_PLAN_MISSING
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
SPEC = ROOT / "docs/design/HAEHAN_SINGLE_EXE_MODE_CONSOLIDATION_SPEC_01.md"

P = "\033[32m[PASS]\033[0m"
W = "\033[33m[WARN]\033[0m"
F = "\033[31m[FAIL]\033[0m"

issues: list[Any] = []
warnings: list[Any] = []
passes: list[Any] = []


def fail(code, msg):
    issues.append(f"{F} {code} — {msg}")


def warn(code, msg):
    warnings.append(f"{W} {code} — {msg}")


def ok(msg):
    passes.append(f"{P} {msg}")


# ── 1. 설계서 존재 ─────────────────────────────────────────────────────────
if not SPEC.exists():
    fail("FAIL_NEXT_PLAN_MISSING", f"설계서 없음: {SPEC}")
    print(*issues, sep="\n")
    sys.exit(1)

text = SPEC.read_text(encoding="utf-8")
ok(f"설계서 존재 ({len(text):,} bytes)")


# ── 2. 단일 exe 원칙 ───────────────────────────────────────────────────────
single_exe_keys = ["HaehanAI.exe", "단일 exe", "A안 통합", "사용자는 exe 하나"]
matched = [k for k in single_exe_keys if k in text]
if len(matched) >= 2:
    ok(f"단일 exe 원칙 명시: {matched}")
else:
    fail("FAIL_TWO_APP_STRATEGY_REMAINS", "단일 exe 원칙 명시 부족")


# ── 3. Tray Mode 정의 ─────────────────────────────────────────────────────
tray_keys = ["Tray Mode", "트레이", "wizard", "heartbeat"]
matched = [k for k in tray_keys if k in text]
if len(matched) >= 3:
    ok(f"Tray Mode 정의 확인: {matched}")
else:
    fail("FAIL_TRAY_MODE_MISSING", f"Tray Mode 정의 부족: {matched}")


# ── 4. Admin Mode 정의 ────────────────────────────────────────────────────
admin_keys = ["Admin Mode", "--admin", "관리화면", "pywebview", "lazy load"]
matched = [k for k in admin_keys if k in text]
if len(matched) >= 3:
    ok(f"Admin Mode 정의 확인: {matched}")
else:
    fail("FAIL_ADMIN_MODE_MISSING", f"Admin Mode 정의 부족: {matched}")


# ── 5. 두 앱 기능 맵 ─────────────────────────────────────────────────────
map_keys = ["기능 맵", "흡수", "유지", "폐기"]
matched = [k for k in map_keys if k in text]
if len(matched) >= 3:
    ok(f"기능 맵 작성: {matched}")
else:
    fail("FAIL_DEPRECATED_PLAN_MISSING", f"기능 맵 부족: {matched}")


# ── 6. role guard 정책 ───────────────────────────────────────────────────
role_keys = ["role guard", "admin/owner", "role 확인", "min_role", "권한"]
matched = [k for k in role_keys if k in text]
if len(matched) >= 3:
    ok(f"role guard 정책: {matched}")
else:
    fail("FAIL_ROLE_GUARD_MISSING", f"role guard 정책 부족: {matched}")

# 5중 guard 명시
guard_layers = ["트레이", "CLI", "미들웨어", "WS", "사이드바"]
matched_g = [k for k in guard_layers if k in text]
if len(matched_g) >= 4:
    ok(f"role guard 다층 (5중) 명시: {matched_g}")
else:
    warn("WARN_ROLE_GUARD_LAYERS", f"다층 guard 명시 부족: {matched_g}")


# ── 7. deprecated 대상 분류 ──────────────────────────────────────────────
deprecated_keys = ["deprecated", "DEPRECATED", "HaehanAI-Agent.spec", "build_desktop_agent_windows", "폐기 후보"]
matched = [k for k in deprecated_keys if k in text]
if len(matched) >= 3:
    ok(f"deprecated 분류: {matched}")
    warn("WARN_AGENT_EXE_DEPRECATION_PENDING", "Agent.exe deprecated — 별도 cleanup 공정에서 삭제 예정")
else:
    fail("FAIL_DEPRECATED_PLAN_MISSING", "deprecated 대상 명시 부족")


# ── 8. 보안 정책 ─────────────────────────────────────────────────────────
sec_keys = ["device_token", "registration_code", "redaction", "Chrome profile cookie", "server proxy"]
matched = [k for k in sec_keys if k in text]
if len(matched) >= 4:
    ok(f"보안 정책 명시: {matched}")
else:
    fail("FAIL_SECURITY_POLICY_MISSING", f"보안 정책 부족: {matched}")


# ── 9. lifecycle 정책 ────────────────────────────────────────────────────
lifecycle_keys = ["lifecycle", "consent", "token 로드", "local_server", "단일 인스턴스", "종료"]
matched = [k for k in lifecycle_keys if k in text]
if len(matched) >= 4:
    ok(f"lifecycle 정책: {matched}")
else:
    warn("WARN_LIFECYCLE_DETAIL", f"lifecycle 세부 보강 필요: {matched}")


# ── 10. build policy ────────────────────────────────────────────────────
build_keys = ["onefolder", "Playwright", "ui_dist", "HaehanAI.spec", "pythonnet", "collect_all"]
matched = [k for k in build_keys if k in text]
if len(matched) >= 3:
    ok(f"build policy: {matched}")
else:
    warn("WARN_BUILD_POLICY_DETAIL", f"build policy 보강: {matched}")


# ── 11. 위험 분석 ──────────────────────────────────────────────────────
risk_keys = ["위험 분석", "exe 크기", "admin surface", "port 충돌", "migration"]
matched = [k for k in risk_keys if k in text]
if len(matched) >= 3:
    ok(f"위험 분석: {matched}")
else:
    warn("WARN_RISK_DETAIL", f"위험 분석 부족: {matched}")


# ── 12. 단계별 구현 계획 ──────────────────────────────────────────────────
steps = [
    "HAEHAN_SINGLE_EXE_LAUNCHER_FOUNDATION_01",
    "HAEHAN_TRAY_REGISTRATION_MERGE_01",
    "HAEHAN_ADMIN_MODE_WEBVIEW_LAZY_LOAD_01",
    "HAEHAN_SINGLE_EXE_BUILD_01",
    "HAEHAN_AGENT_EXE_DEPRECATION_01",
    "HAEHAN_SINGLE_EXE_USER_FIELD_TEST_01",
]
matched = [s for s in steps if s in text]
if len(matched) >= 5:
    ok(f"단계별 구현 계획 ({len(matched)}/6): 모두 명시")
else:
    fail("FAIL_NEXT_PLAN_MISSING", f"단계 누락: {set(steps) - set(matched)}")


# ── 13. 즉시 삭제 금지 명시 ───────────────────────────────────────────────
no_delete_keys = ["즉시 삭제 금지", "즉시 폐기 금지", "삭제 금지", "즉시 Agent.exe 삭제", "cleanup 공정"]
matched = [k for k in no_delete_keys if k in text]
if len(matched) >= 2:
    ok(f"즉시 삭제 금지 명시: {matched}")
else:
    fail("FAIL_DEPRECATED_PLAN_MISSING", "즉시 삭제 금지 문구 누락")


# ── 14. OUT_OF_SCOPE 명시 ────────────────────────────────────────────────
oos_keys = ["OUT_OF_SCOPE", "본 공정에서 하지 않음", "PyInstaller 재빌드", "code signing"]
matched = [k for k in oos_keys if k in text]
if len(matched) >= 2:
    ok(f"OUT_OF_SCOPE 명시: {matched}")
else:
    warn("WARN_OUT_OF_SCOPE", f"OUT_OF_SCOPE 명시 부족: {matched}")


# ── 15. secret 누출 검사 ─────────────────────────────────────────────────
forbidden = ["device_token=", "registration_code=", "sk-", "openai_api_key="]
leaks = []
for f in forbidden:
    # 정책 설명 컨텍스트에 등장하는 것은 허용 (REDACTED 처리 문구)
    lines = [ln for ln in text.split("\n") if f in ln and "REDACTED" not in ln and "금지" not in ln]
    if lines:
        leaks.append(f)
if leaks:
    fail("FAIL_SECURITY_POLICY_MISSING", f"secret 누출 의심: {leaks}")
else:
    ok("secret 누출 0")


# ── 결과 ────────────────────────────────────────────────────────────────
print()
print("=" * 68)
print("  HAEHAN_SINGLE_EXE_MODE_CONSOLIDATION_SPEC_01 감리")
print("=" * 68)
for p in passes:
    print(p)
for w in warnings:
    print(w)
for i in issues:
    print(i)
print("-" * 68)
print(f"PASS: {len(passes)}  WARN: {len(warnings)}  FAIL: {len(issues)}")
if not issues:
    print("\033[32m✅ PASS_HAEHAN_SINGLE_EXE_MODE_CONSOLIDATION_SPEC\033[0m")
else:
    print(f"\033[31m❌ FAIL — {len(issues)}건 수정 필요\033[0m")
print("=" * 68)
sys.exit(1 if issues else 0)
