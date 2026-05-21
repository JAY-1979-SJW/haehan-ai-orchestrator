"""audit_haehan_tray_registration_merge.py
HAEHAN_TRAY_REGISTRATION_MERGE_01 감리.

Verdicts:
  PASS_HAEHAN_TRAY_REGISTRATION_MERGE
  WARN_CONSENT_DIALOG_DEFERRED  (HAEHAN_CONSENT_DIALOG_01 에서 해소 예정)
  (WARN_ADMIN_MODE_DEFERRED 제거 — HAEHAN_ADMIN_MODE_WEBVIEW_LAZY_LOAD_01 에서 실 구현 완료)
  FAIL_TRAY_HOOK_NOT_CONNECTED
  FAIL_WIZARD_MISSING
  FAIL_TOKEN_STORE_BROKEN
  FAIL_WSS_HEARTBEAT_BROKEN
  FAIL_SECRET_LEAK
  FAIL_EXISTING_ENTRYPOINT_BROKEN
"""
from __future__ import annotations
import importlib
import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

TRAY_RUNTIME = ROOT / "desktop/tray_runtime.py"
LAUNCHER     = ROOT / "desktop/main_launcher.py"

P = "\033[32m[PASS]\033[0m"
W = "\033[33m[WARN]\033[0m"
F = "\033[31m[FAIL]\033[0m"

issues, warnings, passes = [], [], []

def fail(code, msg): issues.append(f"{F} {code} — {msg}")
def warn(code, msg): warnings.append(f"{W} {code} — {msg}")
def ok(msg):         passes.append(f"{P} {msg}")


# ── 1. tray_runtime 모듈 ─────────────────────────────────────────────────
if not TRAY_RUNTIME.exists():
    fail("FAIL_TRAY_HOOK_NOT_CONNECTED", f"tray_runtime 없음: {TRAY_RUNTIME}")
else:
    ok(f"tray_runtime 존재 ({TRAY_RUNTIME.stat().st_size:,} bytes)")

try:
    from desktop import tray_runtime as tr
    ok("tray_runtime import OK")
except Exception as e:
    fail("FAIL_TRAY_HOOK_NOT_CONNECTED", f"tray_runtime import 실패: {e}")
    print(*issues, sep="\n")
    sys.exit(1)


# ── 2. 필수 심볼 ──────────────────────────────────────────────────────────
required_symbols = [
    "RegistrationStatus", "TrayMenuItem", "HeartbeatPlan", "WizardOutcome",
    "check_registration_status", "decide_next_action", "decide_action_from_error",
    "build_tray_menu_items", "plan_heartbeat",
    "apply_registration_result", "build_diagnostics_payload",
    "run_registration_wizard_cli", "run_registration_wizard_gui",
    "start_heartbeat_background", "start_tray_gui",
    "run_tray_mode_full",
]
missing = [s for s in required_symbols if not hasattr(tr, s)]
if missing:
    fail("FAIL_TRAY_HOOK_NOT_CONNECTED", f"심볼 누락: {missing}")
else:
    ok(f"필수 심볼 {len(required_symbols)}개 존재")


# ── 3. main_launcher 와 연결 ─────────────────────────────────────────────
try:
    from desktop import main_launcher as ml
    src = LAUNCHER.read_text(encoding="utf-8")
    if "tray_runtime" in src and "run_tray_mode_full" in src:
        ok("launcher → tray_runtime 연결 확인")
    else:
        fail("FAIL_TRAY_HOOK_NOT_CONNECTED", "launcher 에 tray_runtime 호출 없음")

    # run_tray_mode 가 skip_gui 지원
    import inspect
    sig = inspect.signature(ml.run_tray_mode)
    if "skip_gui" in sig.parameters:
        ok("run_tray_mode(skip_gui=...) 시그니처 확인")
    else:
        warn("WARN_SKIP_GUI", "run_tray_mode skip_gui 미지원 (테스트 어려움)")
except Exception as e:
    fail("FAIL_EXISTING_ENTRYPOINT_BROKEN", f"main_launcher import 실패: {e}")


# ── 4. wizard CLI 시뮬레이션 ─────────────────────────────────────────────
class _FakeMeta:
    def __init__(self):
        self.agent_id = "la-test1234abcd"
        self.code_id = "code-1"
        self.label = "test"
        self.registered_at = "2026-05-22"
        self.version = "0.2.0"

def _fake_register(*, server_url, registration_code, host, os_name, version):
    if not registration_code:
        raise tr.WizardOutcome  # not used
    return _FakeMeta(), "test_token_FAKE_DO_NOT_USE_ABC123"

def _fake_save(server_url, agent_id, token, *, allow_plaintext_fallback=False):
    return "mock-keyring"

def _fake_config_save(cfg):
    return None

# wizard CLI 호출 — 토큰 원문이 반환에 미포함인지
outcome = tr.run_registration_wizard_cli(
    server_url="https://test.example.com",
    registration_code="REG_CODE_FAKE",
    register_fn=_fake_register,
)
# apply_registration_result 단계는 실제 token_store 호출 — 우회 위해 직접 검증
direct = tr.apply_registration_result(
    "https://test.example.com",
    _FakeMeta(),
    "test_token_FAKE_DO_NOT_USE",
    token_saver=_fake_save,
    config_saver=_fake_config_save,
)
if direct.success:
    ok("apply_registration_result 성공")
else:
    fail("FAIL_WIZARD_MISSING", f"apply_registration_result 실패: {direct}")

# WizardOutcome 에 token 원문 없음
import dataclasses
out_dict = dataclasses.asdict(direct)
if "device_token" not in out_dict and "token" not in out_dict:
    ok("WizardOutcome 에 token 키 없음")
else:
    fail("FAIL_SECRET_LEAK", f"WizardOutcome 에 token 키: {out_dict}")


# ── 5. 토큰 원문 leak 검사 ───────────────────────────────────────────────
src = TRAY_RUNTIME.read_text(encoding="utf-8")
for pat in ["sk-proj-", "sk-ant-", "Bearer eyJ"]:
    if pat in src:
        fail("FAIL_SECRET_LEAK", f"소스에 {pat}")
        break
else:
    ok("tray_runtime 소스 secret 없음")


# ── 6. heartbeat plan ───────────────────────────────────────────────────
status_unreg = tr.RegistrationStatus(registered=False)
plan = tr.plan_heartbeat(status_unreg)
if not plan.can_start and plan.reason == "not_registered":
    ok("plan_heartbeat 미등록 → can_start=False")
else:
    fail("FAIL_WSS_HEARTBEAT_BROKEN", f"미등록 plan 잘못: {plan}")

status_reg = tr.RegistrationStatus(
    registered=True, server_url="https://test.example.com",
    agent_id="la-abc123", token_present=True,
)
plan2 = tr.plan_heartbeat(status_reg)
if plan2.can_start and plan2.ws_url.startswith("wss://"):
    ok(f"plan_heartbeat 등록 → ws_url={plan2.ws_url}")
else:
    fail("FAIL_WSS_HEARTBEAT_BROKEN", f"등록 plan 잘못: {plan2}")


# ── 7. error code 매핑 ──────────────────────────────────────────────────
cases = [
    ("AUTH_FAILED_4401", "show_wizard"),
    ("TOKEN_NOT_STORED", "show_wizard"),
    ("REG_CODE_EXPIRED", "show_wizard"),
    ("SERVER_NOT_REACHABLE", "show_diagnostics"),
    ("HEARTBEAT_LOST", "reconnect"),
    ("", "reconnect"),
]
all_ok = True
for code, expected in cases:
    got = tr.decide_action_from_error(code)
    if got == expected:
        ok(f"decide_action_from_error({code!r}) → {got}")
    else:
        fail("FAIL_WSS_HEARTBEAT_BROKEN", f"{code} → {got}, expected {expected}")
        all_ok = False


# ── 8. tray menu 구성 ───────────────────────────────────────────────────
items_reg = tr.build_tray_menu_items(
    status=status_reg, role="admin", admin_mode_available=False,
)
ids = [it.id for it in items_reg]
for need in ["status", "diagnostics", "re_register", "open_admin", "autostart", "quit"]:
    if need in ids:
        ok(f"메뉴 항목: {need}")
    else:
        fail("FAIL_TRAY_HOOK_NOT_CONNECTED", f"메뉴 누락: {need}")

# 일반 사용자(role=any) 는 open_admin 미노출
items_any = tr.build_tray_menu_items(status=status_reg, role="any")
ids_any = [it.id for it in items_any]
if "open_admin" not in ids_any:
    ok("role=any → open_admin 숨김 (role guard 동작)")
else:
    fail("FAIL_TRAY_HOOK_NOT_CONNECTED", "role=any 인데 open_admin 노출")


# ── 9. diagnostics payload ──────────────────────────────────────────────
payload = tr.build_diagnostics_payload(status=status_reg, heartbeat_state="CONNECTED")
required_keys = ["server_url_redacted", "ws_url_redacted", "agent_id_masked",
                 "state", "token_present", "config_present"]
missing_k = [k for k in required_keys if k not in payload]
if missing_k:
    fail("FAIL_TRAY_HOOK_NOT_CONNECTED", f"diagnostics 키 누락: {missing_k}")
else:
    ok(f"diagnostics payload 키 {len(required_keys)}개 존재")

# token 원문/value 없음
forbidden_keys = ["device_token", "token_value", "token_raw", "token_hash"]
if any(k in payload for k in forbidden_keys):
    fail("FAIL_SECRET_LEAK", f"diagnostics 에 금지 키: {[k for k in forbidden_keys if k in payload]}")
else:
    ok("diagnostics 에 token 원문 키 0")

# masking 확인
if "la-abc123" in json.dumps(payload):
    fail("FAIL_SECRET_LEAK", "agent_id 원문 노출")
elif "***" in payload.get("agent_id_masked", ""):
    ok(f"agent_id 마스킹: {payload['agent_id_masked']}")


# ── 10. launcher diagnostics 통합 ───────────────────────────────────────
buf = io.StringIO()
with redirect_stdout(buf):
    ml.print_diagnostics(ml.AppMode.DIAGNOSTICS)
out = buf.getvalue()
data = json.loads(out)
if data.get("server", {}).get("url_redacted") is not None:
    ok("launcher diagnostics 에 server.url_redacted 추가")
else:
    warn("WARN_DIAG_INTEGRATION", "launcher diagnostics 통합 미완")

if data.get("heartbeat", {}).get("state"):
    ok(f"launcher diagnostics 에 heartbeat.state={data['heartbeat']['state']}")


# ── 11. 기존 entrypoint 회귀 ────────────────────────────────────────────
existing = [
    "desktop.webview_app_pywebview",
    "desktop.local_server",
    "local_agent.desktop_launcher",
    "local_agent.token_store",
    "local_agent.registration_client",
    "local_agent.connection_diagnostics",
]
for mod in existing:
    try:
        importlib.import_module(mod)
        ok(f"기존 entrypoint OK: {mod}")
    except Exception as e:
        fail("FAIL_EXISTING_ENTRYPOINT_BROKEN", f"{mod}: {e}")


# ── 12. lock 회귀 ────────────────────────────────────────────────────────
state_before = ml._read_lock()
state_lock = ml.acquire_lock()
if state_lock.acquired:
    ok("acquire_lock 회귀 OK")
    ml.release_lock()
else:
    warn("WARN_LOCK", f"lock 획득 실패 (이미 사용 중일 수 있음): pid={state_lock.pid}")


# ── 13. Admin Mode 구현 상태 — HAEHAN_AUDIT_WARN_SYNC_01 후 정리 ──────
# WARN_ADMIN_MODE_DEFERRED: HAEHAN_ADMIN_MODE_WEBVIEW_LAZY_LOAD_01 에서 실 구현 완료
# → admin_webview.py 존재 + main_launcher.run_admin_mode 실호출 + admin_mode_available=True 검증
src_run = (ROOT / "desktop/main_launcher.py").read_text(encoding="utf-8")
admin_wv = ROOT / "desktop/admin_webview.py"
admin_checks = []
if admin_wv.exists():
    admin_checks.append("admin_webview.py 존재")
if "admin_webview.run_admin_mode_full" in src_run \
        or "admin_webview.open_admin_window" in src_run \
        or "from desktop import admin_webview" in src_run:
    admin_checks.append("main_launcher → admin_webview 호출")
if "admin_mode_available=True" in src_run:
    admin_checks.append("admin_mode_available=True 전달")
if len(admin_checks) >= 3:
    ok(f"Admin Mode 실 구현 확인 ({', '.join(admin_checks)}) — WARN_ADMIN_MODE_DEFERRED 해소")
else:
    fail("FAIL_ADMIN_MODE_REGRESSED",
         f"Admin Mode 구현 회귀 — 확인된 항목: {admin_checks}")


# ── 14. consent dialog 상태 ────────────────────────────────────────────
# WARN_CONSENT_DIALOG_DEFERRED: 유지 (HAEHAN_CONSENT_DIALOG_01 에서 해소 예정)
if "webview_app_pywebview._check_consent" in src_run \
        or "from desktop.webview_app_pywebview import _check_consent" in src_run:
    ok("main_launcher ↔ _check_consent 연결됨 (WARN_CONSENT_DIALOG_DEFERRED 해소 시 PASS)")
else:
    warn("WARN_CONSENT_DIALOG_DEFERRED",
         "main_launcher consent hook 과 _check_consent 미연결 — HAEHAN_CONSENT_DIALOG_01 에서 해소 예정")


# ── 결과 ────────────────────────────────────────────────────────────────
print()
print("=" * 68)
print("  HAEHAN_TRAY_REGISTRATION_MERGE_01 감리")
print("=" * 68)
for p in passes:   print(p)
for w in warnings: print(w)
for i in issues:   print(i)
print("-" * 68)
print(f"PASS: {len(passes)}  WARN: {len(warnings)}  FAIL: {len(issues)}")
if not issues:
    print(f"\033[32m✅ PASS_HAEHAN_TRAY_REGISTRATION_MERGE\033[0m")
else:
    print(f"\033[31m❌ FAIL — {len(issues)}건 수정 필요\033[0m")
print("=" * 68)
sys.exit(1 if issues else 0)
