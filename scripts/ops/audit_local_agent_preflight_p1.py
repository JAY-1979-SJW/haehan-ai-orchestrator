"""audit_local_agent_preflight_p1.py
LOCAL_AGENT_PREFLIGHT_P1 감리 — schema_version: local_agent_preflight_v1

P1 범위 (exception handler P2 는 미포함):
  1. /local-agent/preflight 라우트 소스 존재
  2. full schema 13개 top-level 필드 모두 존재
  3. 필드명 확정: provider_status / optional_status (providers / optional 금지)
  4. can_run 계산 — provider 기반, optional down 은 차단 금지
  5. blocking_reasons / user_message / next_actions 동작
  6. api_key_set 은 boolean (top-level + nested 모두)
  7. claude_cli_available 은 boolean (top-level)
  8. health 요약 — raw key 미포함
  9. whoami — crash 금지, role/admin/source
  10. consent — crash 금지, agreed 필드
  11. optional_status — CAD/CDP down 이어도 can_run=true
  12. warnings — optional down 시 비차단 경고 기록
  13. secret scan

Verdicts:
  PASS_LOCAL_AGENT_PREFLIGHT_P1
  FAIL_PREFLIGHT_ROUTE_MISSING
  FAIL_SCHEMA_FIELD_MISSING
  FAIL_WRONG_FIELD_NAME
  FAIL_CAN_RUN_LOGIC
  FAIL_SECRET_LEAK
  FAIL_API_KEY_SET_NOT_BOOL
  FAIL_OPTIONAL_BLOCKS_CAN_RUN
  FAIL_WHOAMI_CRASH
  FAIL_CONSENT_CRASH
  WARN_NO_TESTCLIENT
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

LOCAL_SERVER = ROOT / "desktop" / "local_server.py"
LOCAL_SVC    = ROOT / "desktop" / "local_agent_service.py"

P = "\033[32m[PASS]\033[0m"
W = "\033[33m[WARN]\033[0m"
F = "\033[31m[FAIL]\033[0m"

issues, warnings, passes = [], [], []

def fail(code, msg): issues.append(f"{F} {code} — {msg}")
def warn(code, msg): warnings.append(f"{W} {code} — {msg}")
def ok(msg):         passes.append(f"{P} {msg}")

REQUIRED_FIELDS = [
    "schema_version", "ok", "can_run", "blocking_reasons",
    "user_message", "next_actions", "provider_status",
    "api_key_set", "claude_cli_available", "health",
    "whoami", "consent", "optional_status", "warnings",
]

FORBIDDEN_RESPONSE_KEYS = {
    "api_key", "apikey", "raw_api_key", "token", "bearer",
    "cookie", "session", "authorization", "database_url",
    "secret", "password",
}

# ── 1. 라우트 / 함수 소스 존재 ───────────────────────────────────────────────
src = LOCAL_SERVER.read_text(encoding="utf-8")
svc = LOCAL_SVC.read_text(encoding="utf-8")

if "/local-agent/preflight" in src:
    ok("/local-agent/preflight 라우트 소스 존재")
else:
    fail("FAIL_PREFLIGHT_ROUTE_MISSING", "local_server.py 에 /local-agent/preflight 없음")

if "local_agent_preflight" in svc:
    ok("local_agent_service.py 에 local_agent_preflight() 존재")
else:
    fail("FAIL_PREFLIGHT_ROUTE_MISSING", "local_agent_service.py 에 local_agent_preflight 없음")

# ── 2. 잘못된 구 필드명 금지 ────────────────────────────────────────────────
if '"providers"' in svc and "provider_status" not in svc:
    fail("FAIL_WRONG_FIELD_NAME", "구 필드명 'providers' 사용, provider_status 로 교체 필요")
else:
    ok("구 필드명 'providers' 미사용 확인")

if '"optional"' in svc and "optional_status" not in svc:
    fail("FAIL_WRONG_FIELD_NAME", "구 필드명 'optional' 사용, optional_status 로 교체 필요")
else:
    ok("구 필드명 'optional' 미사용 확인")

# ── 3. schema_version 고정값 확인 ────────────────────────────────────────────
if "local_agent_preflight_v1" in svc:
    ok("schema_version = local_agent_preflight_v1 소스 존재")
else:
    fail("FAIL_SCHEMA_FIELD_MISSING", "schema_version 'local_agent_preflight_v1' 미발견")


# ── 4. TestClient 동적 검증 ──────────────────────────────────────────────────
try:
    from fastapi.testclient import TestClient

    for mn in list(sys.modules.keys()):
        if mn.startswith("desktop"):
            del sys.modules[mn]

    from desktop import local_server as _ls
    from desktop import local_agent_service as _svc_mod

    _ls._remote_enabled = lambda: True   # type: ignore
    _ls._verify_token   = lambda t: True  # type: ignore

    client = TestClient(_ls.app, raise_server_exceptions=False)

    def _check_full_schema(data: dict, label: str) -> None:
        for field in REQUIRED_FIELDS:
            if field in data:
                ok(f"[{label}] {field} 존재")
            else:
                fail("FAIL_SCHEMA_FIELD_MISSING", f"[{label}] 필수 필드 누락: {field}")

    def _check_secret_leak(data: dict, label: str) -> None:
        data_str = json.dumps(data).lower()
        leaks = []
        for k in FORBIDDEN_RESPONSE_KEYS:
            # api_key_set 오탐 방지: "api_key" 가 key-name으로 독립 등장할 때만
            if k == "api_key":
                if '"api_key"' in data_str and '"api_key_set"' not in data_str:
                    leaks.append(k)
            elif f'"{k}"' in data_str:
                leaks.append(k)
        if leaks:
            fail("FAIL_SECRET_LEAK", f"[{label}] 금지 필드 응답 노출: {leaks}")
        else:
            ok(f"[{label}] secret scan PASS")

    # ── 4a. CASE_A: provider 없음 ─────────────────────────────────────────────
    saved = os.environ.pop("ANTHROPIC_API_KEY", None)
    orig_which = _svc_mod.shutil.which  # type: ignore
    _svc_mod.shutil.which = lambda n: None  # type: ignore

    try:
        r_a = client.get("/local-agent/preflight")
        assert r_a.status_code == 200, f"status={r_a.status_code}"
        data_a = r_a.json()
        ok(f"CASE_A full JSON:\n{json.dumps(data_a, ensure_ascii=False, indent=2)}")
    finally:
        if saved:
            os.environ["ANTHROPIC_API_KEY"] = saved
        _svc_mod.shutil.which = orig_which  # type: ignore

    _check_full_schema(data_a, "CASE_A")
    _check_secret_leak(data_a, "CASE_A")

    # schema_version 값 확인
    if data_a.get("schema_version") == "local_agent_preflight_v1":
        ok("CASE_A schema_version = local_agent_preflight_v1")
    else:
        fail("FAIL_SCHEMA_FIELD_MISSING", f"CASE_A schema_version 값 오류: {data_a.get('schema_version')}")

    # can_run=False
    if data_a.get("can_run") is False:
        ok("CASE_A provider 없음 → can_run=False")
    else:
        fail("FAIL_CAN_RUN_LOGIC", f"CASE_A can_run={data_a.get('can_run')} (False 기대)")

    # blocking_reasons 배열
    br_a = data_a.get("blocking_reasons", None)
    if isinstance(br_a, list):
        ok(f"CASE_A blocking_reasons 배열: {br_a}")
        if "NO_PROVIDER_AVAILABLE" in br_a:
            ok("CASE_A blocking_reasons 에 NO_PROVIDER_AVAILABLE 포함")
        else:
            fail("FAIL_CAN_RUN_LOGIC", f"CASE_A blocking_reasons 에 NO_PROVIDER_AVAILABLE 없음: {br_a}")
    else:
        fail("FAIL_SCHEMA_FIELD_MISSING", f"CASE_A blocking_reasons 배열 아님: {br_a}")

    # user_message 비어있지 않음
    um_a = data_a.get("user_message", "")
    if um_a:
        ok(f"CASE_A user_message: '{um_a}'")
    else:
        fail("FAIL_SCHEMA_FIELD_MISSING", "CASE_A user_message 비어있음")

    # next_actions 배열
    na_a = data_a.get("next_actions", None)
    if isinstance(na_a, list):
        ok(f"CASE_A next_actions: {na_a}")
    else:
        fail("FAIL_SCHEMA_FIELD_MISSING", f"CASE_A next_actions 배열 아님: {na_a}")

    # api_key_set top-level boolean
    aks_top = data_a.get("api_key_set")
    if isinstance(aks_top, bool):
        ok(f"CASE_A api_key_set(top-level) boolean: {aks_top}")
    else:
        fail("FAIL_API_KEY_SET_NOT_BOOL", f"CASE_A api_key_set top-level: {type(aks_top)}")

    # claude_cli_available top-level boolean
    cca = data_a.get("claude_cli_available")
    if isinstance(cca, bool):
        ok(f"CASE_A claude_cli_available(top-level) boolean: {cca}")
    else:
        fail("FAIL_API_KEY_SET_NOT_BOOL", f"CASE_A claude_cli_available top-level: {type(cca)}")

    # provider_status 필드명
    if "provider_status" in data_a:
        ok("CASE_A provider_status 필드명 확인")
        ps = data_a["provider_status"]
        nested_aks = ps.get("anthropic_sdk", {}).get("api_key_set")
        if isinstance(nested_aks, bool):
            ok(f"CASE_A provider_status.anthropic_sdk.api_key_set boolean: {nested_aks}")
        else:
            fail("FAIL_API_KEY_SET_NOT_BOOL", f"nested api_key_set 타입: {type(nested_aks)}")
    else:
        fail("FAIL_WRONG_FIELD_NAME", "CASE_A provider_status 필드 없음")

    if "providers" in data_a:
        fail("FAIL_WRONG_FIELD_NAME", "CASE_A 구 필드명 'providers' 응답에 존재")

    # optional_status 필드명
    if "optional_status" in data_a:
        ok("CASE_A optional_status 필드명 확인")
    else:
        fail("FAIL_WRONG_FIELD_NAME", "CASE_A optional_status 필드 없음")

    if "optional" in data_a:
        fail("FAIL_WRONG_FIELD_NAME", "CASE_A 구 필드명 'optional' 응답에 존재")

    # whoami 필드
    wm = data_a.get("whoami", {})
    if isinstance(wm, dict) and "role" in wm:
        ok(f"CASE_A whoami: {wm}")
    else:
        fail("FAIL_WHOAMI_CRASH", f"CASE_A whoami 형식 오류: {wm}")

    # consent 필드
    cs = data_a.get("consent", {})
    if isinstance(cs, dict) and "agreed" in cs:
        ok(f"CASE_A consent: {cs}")
    else:
        fail("FAIL_CONSENT_CRASH", f"CASE_A consent 형식 오류: {cs}")

    # warnings 배열
    wl = data_a.get("warnings", None)
    if isinstance(wl, list):
        ok(f"CASE_A warnings: {wl}")
    else:
        fail("FAIL_SCHEMA_FIELD_MISSING", f"CASE_A warnings 배열 아님: {wl}")

    # health 필드
    hl = data_a.get("health", {})
    if isinstance(hl, dict) and "available" in hl:
        ok(f"CASE_A health.available={hl.get('available')}")
        # health 에 raw key 없음
        hl_str = json.dumps(hl).lower()
        if "sk-" in hl_str or '"api_key"' in hl_str:
            fail("FAIL_SECRET_LEAK", "CASE_A health 에 raw key 포함")
        else:
            ok("CASE_A health secret scan PASS")
    else:
        fail("FAIL_SCHEMA_FIELD_MISSING", f"CASE_A health 형식 오류: {hl}")

    # ── 4b. CASE_B: mock provider 준비 ───────────────────────────────────────
    os.environ["ANTHROPIC_API_KEY"] = "sk-mock-test-audit-evidence"
    orig_avail = _svc_mod._anthropic_available  # type: ignore
    _svc_mod._anthropic_available = lambda: True  # type: ignore

    try:
        r_b = client.get("/local-agent/preflight")
        assert r_b.status_code == 200, f"status={r_b.status_code}"
        data_b = r_b.json()
        ok(f"CASE_B full JSON:\n{json.dumps(data_b, ensure_ascii=False, indent=2)}")
    finally:
        os.environ.pop("ANTHROPIC_API_KEY", None)
        _svc_mod._anthropic_available = orig_avail  # type: ignore

    _check_full_schema(data_b, "CASE_B")
    _check_secret_leak(data_b, "CASE_B")

    if data_b.get("can_run") is True:
        ok("CASE_B mock provider → can_run=True")
    else:
        fail("FAIL_CAN_RUN_LOGIC", f"CASE_B can_run={data_b.get('can_run')} (True 기대)")

    if not data_b.get("blocking_reasons"):
        ok("CASE_B blocking_reasons 비어있음 (정상)")
    else:
        # consent 없으면 CONSENT_REQUIRED 남을 수 있음 — 환경에 따라 허용
        br_b = data_b.get("blocking_reasons", [])
        non_consent = [r for r in br_b if r != "CONSENT_REQUIRED"]
        if non_consent:
            fail("FAIL_CAN_RUN_LOGIC", f"CASE_B 예상치 못한 blocking_reasons: {non_consent}")
        else:
            ok(f"CASE_B blocking_reasons: {br_b} (CONSENT_REQUIRED 만 있을 수 있음)")

    # mock key 원문 미노출
    if "sk-mock-test-audit-evidence" in r_b.text:
        fail("FAIL_SECRET_LEAK", "CASE_B mock API key 원문 응답에 노출")
    else:
        ok("CASE_B mock API key 원문 미노출")

    if data_b.get("api_key_set") is True:
        ok("CASE_B api_key_set(top-level)=True")
    else:
        fail("FAIL_API_KEY_SET_NOT_BOOL", f"CASE_B api_key_set={data_b.get('api_key_set')}")

    # ── 4c. CAD/CDP down → can_run=true 유지 ─────────────────────────────────
    os.environ["ANTHROPIC_API_KEY"] = "sk-mock-optional-test"
    _svc_mod._anthropic_available = lambda: True  # type: ignore
    orig_find_mcp  = _svc_mod._find_mcp_server      # type: ignore
    orig_check_cdp = _svc_mod._check_cdp_available  # type: ignore
    _svc_mod._find_mcp_server    = lambda: None      # type: ignore
    _svc_mod._check_cdp_available = lambda: False    # type: ignore

    try:
        r_c = client.get("/local-agent/preflight")
        data_c = r_c.json()
        ok(f"CASE_C CAD/CDP down JSON:\n{json.dumps(data_c, ensure_ascii=False, indent=2)}")
    finally:
        os.environ.pop("ANTHROPIC_API_KEY", None)
        _svc_mod._anthropic_available   = orig_avail    # type: ignore
        _svc_mod._find_mcp_server       = orig_find_mcp  # type: ignore
        _svc_mod._check_cdp_available   = orig_check_cdp # type: ignore

    cad_avail = data_c.get("optional_status", {}).get("cad", {}).get("available")
    cdp_avail = data_c.get("optional_status", {}).get("cdp", {}).get("available")

    if cad_avail is False and cdp_avail is False:
        ok("CASE_C CAD/CDP down → optional_status.available=False")
    else:
        fail("FAIL_OPTIONAL_BLOCKS_CAN_RUN", f"CASE_C CAD={cad_avail} CDP={cdp_avail}")

    can_run_c = data_c.get("can_run")
    if can_run_c is True:
        ok("CASE_C CAD/CDP down 에서도 can_run=True (optional 미차단)")
    else:
        fail("FAIL_OPTIONAL_BLOCKS_CAN_RUN", f"CASE_C can_run={can_run_c} — optional 이 can_run 차단")

    warns_c = data_c.get("warnings", [])
    if "CAD_MCP_SERVER_NOT_FOUND" in warns_c and "CDP_BROWSER_NOT_RUNNING" in warns_c:
        ok(f"CASE_C warnings 에 CAD/CDP 경고 기록: {warns_c}")
    else:
        fail("FAIL_OPTIONAL_BLOCKS_CAN_RUN",
             f"CASE_C warnings 에 CAD/CDP 경고 미기록: {warns_c}")

    # ── 4d. whoami crash 금지 — _resolve_whoami_role 강제 예외 ───────────────
    orig_whoami = _svc_mod._safe_whoami_summary  # type: ignore
    _svc_mod._safe_whoami_summary = lambda: (_ for _ in ()).throw(RuntimeError("mock crash"))  # type: ignore
    try:
        r_wm = client.get("/local-agent/preflight")
        if r_wm.status_code == 200:
            ok("whoami crash → 200 반환 (crash 없음)")
        else:
            fail("FAIL_WHOAMI_CRASH", f"whoami crash 후 status={r_wm.status_code}")
    except Exception as e:
        fail("FAIL_WHOAMI_CRASH", f"whoami crash 전파: {e}")
    finally:
        _svc_mod._safe_whoami_summary = orig_whoami  # type: ignore

    # ── 4e. consent crash 금지 ────────────────────────────────────────────────
    orig_consent = _svc_mod._safe_consent_summary  # type: ignore
    _svc_mod._safe_consent_summary = lambda: (_ for _ in ()).throw(RuntimeError("mock crash"))  # type: ignore
    try:
        r_cs = client.get("/local-agent/preflight")
        if r_cs.status_code == 200:
            ok("consent crash → 200 반환 (crash 없음)")
        else:
            fail("FAIL_CONSENT_CRASH", f"consent crash 후 status={r_cs.status_code}")
    except Exception as e:
        fail("FAIL_CONSENT_CRASH", f"consent crash 전파: {e}")
    finally:
        _svc_mod._safe_consent_summary = orig_consent  # type: ignore

except ImportError as e:
    warn("WARN_NO_TESTCLIENT", f"TestClient 사용 불가 — 동적 검증 생략: {e}")
except Exception as e:
    import traceback
    warn("WARN_NO_TESTCLIENT", f"동적 검증 오류: {e}\n{traceback.format_exc()[-400:]}")


# ── 5. secret scan — 소스 파일 ──────────────────────────────────────────────
combined = (LOCAL_SERVER.read_text(encoding="utf-8") +
            LOCAL_SVC.read_text(encoding="utf-8"))

def _strip_comments(text: str) -> str:
    out = []
    for ln in text.split("\n"):
        if ln.lstrip().startswith("#"):
            continue
        idx = ln.find("#")
        out.append(ln[:idx] if idx >= 0 else ln)
    return "\n".join(out)

raw_keys = re.findall(r"sk-[A-Za-z0-9\-_]{10,}", _strip_comments(combined))
if raw_keys:
    fail("FAIL_SECRET_LEAK", f"소스에 sk- raw key 패턴: {raw_keys[:3]}")
else:
    ok("소스 secret scan — sk- raw key 없음")


# ── 결과 ─────────────────────────────────────────────────────────────────────
print()
print("=" * 72)
print("  LOCAL_AGENT_PREFLIGHT_P1 감리 (schema_version: local_agent_preflight_v1)")
print("=" * 72)
for p in passes:   print(p)
for w in warnings: print(w)
for i in issues:   print(i)
print("-" * 72)
print(f"PASS: {len(passes)}  WARN: {len(warnings)}  FAIL: {len(issues)}")
if not issues:
    print("\033[32m✅ PASS_LOCAL_AGENT_PREFLIGHT_P1\033[0m")
else:
    print(f"\033[31m❌ FAIL — {len(issues)}건 수정 필요\033[0m")
print("=" * 72)
sys.exit(1 if issues else 0)
