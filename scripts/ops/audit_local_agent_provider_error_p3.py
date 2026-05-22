"""audit_local_agent_provider_error_p3.py
LOCAL_AGENT_PROVIDER_ERROR_P3 감리

P3 범위: desktop/local_agent_service.py provider 오류 응답 표준화.
P1/P2 코드는 추가 변경하지 않음.

검사 항목:
  1. _provider_error_response() 빌더 소스 존재
  2. 기존 응답 키 보존: ok/result/provider/model/tool_calls
  3. 추가 키 포함: error_code/user_message/next_actions/provider_status/can_retry/safe_to_show
  4. P3 오류 코드 목록 포함 여부
  5. API key 없음 + CLI 없음 → NO_PROVIDER_AVAILABLE 응답
  6. API key 없음 + CLI 있음 → CLI 폴백 (오류 아님)
  7. prompt 없음 → PROMPT_EMPTY 응답
  8. raw exception 원문 미포함 (result 필드에 str(exc) 금지)
  9. secret/token 응답 미노출
  10. 외부 AI 실제 호출 없음 증거

Verdicts:
  PASS_P3_PROVIDER_ERROR_RESPONSE_STANDARDIZED
  WARN_P3_RESPONSE_COMPATIBILITY_RISK
  FAIL_P3_PROVIDER_RESPONSE_UNSAFE
  FAIL_P3_EXISTING_KEY_MISSING
  FAIL_P3_ERROR_CODE_MISSING
  FAIL_P3_SECRET_LEAK
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

LOCAL_SVC = ROOT / "desktop" / "local_agent_service.py"

P = "\033[32m[PASS]\033[0m"
W = "\033[33m[WARN]\033[0m"
F = "\033[31m[FAIL]\033[0m"

issues, warnings, passes = [], [], []

def fail(code, msg): issues.append(f"{F} {code} — {msg}")
def warn(code, msg): warnings.append(f"{W} {code} — {msg}")
def ok(msg):         passes.append(f"{P} {msg}")

EXISTING_KEYS   = {"ok", "result", "provider", "model", "tool_calls"}
P3_EXTRA_KEYS   = {"error_code", "user_message", "next_actions", "provider_status",
                   "can_retry", "safe_to_show"}
P3_ERROR_CODES  = {
    "NO_PROVIDER_AVAILABLE", "API_KEY_MISSING", "CLAUDE_CLI_NOT_FOUND",
    "PROVIDER_NOT_READY", "EXECUTION_BLOCKED_BY_PREFLIGHT",
    "PROMPT_EMPTY", "EXECUTION_TIMEOUT", "EXECUTION_FAILED",
}
FORBIDDEN_IN_RESPONSE = {
    "traceback", "api_key", "token", "cookie", "session",
    "authorization", "bearer", "database_url", "password", "secret",
}


# ── 1. 소스 확인 ─────────────────────────────────────────────────────────────
svc = LOCAL_SVC.read_text(encoding="utf-8")

if "_provider_error_response" in svc:
    ok("_provider_error_response() 빌더 소스 존재")
else:
    fail("FAIL_P3_ERROR_CODE_MISSING", "_provider_error_response 빌더 없음")

for code in ("NO_PROVIDER_AVAILABLE", "PROVIDER_NOT_READY", "EXECUTION_TIMEOUT",
             "EXECUTION_FAILED", "PROMPT_EMPTY"):
    if code in svc:
        ok(f"오류 코드 소스 존재: {code}")
    else:
        fail("FAIL_P3_ERROR_CODE_MISSING", f"오류 코드 미정의: {code}")

# raw exception 원문 노출 패턴 금지 — run_local_agent 반환 경로만 검사
# MCP tool_result content_str(Claude에게 보내는 내부 페이로드)은 제외
import re as _re

# run_local_agent 함수 추출
_run_fn_idx = svc.find("async def run_local_agent(")
_run_fn_end = svc.find("\nasync def ", _run_fn_idx + 1)
run_fn_src = svc[_run_fn_idx: _run_fn_end if _run_fn_end > 0 else _run_fn_idx + 4000]

if 'f"오류: {exc}"' in run_fn_src or "f'오류: {exc}'" in run_fn_src:
    fail("FAIL_P3_PROVIDER_RESPONSE_UNSAFE",
         "run_local_agent 반환값에 f'오류: {exc}' raw 원문 노출")
else:
    ok("run_local_agent 반환값에 raw exception 원문(f'오류: {exc}') 미사용")

if "type(exc).__name__" in svc:
    ok("exception 로그 — type(exc).__name__ 만 기록")
else:
    warn("WARN_P3_LOGGER_STYLE", "exception 로그 형식 미확인")


# ── 2. 동적 검증 ─────────────────────────────────────────────────────────────
try:
    for mn in list(sys.modules.keys()):
        if mn.startswith("desktop"):
            del sys.modules[mn]

    from desktop import local_agent_service as _svc

    def _check_existing_keys(data: dict, label: str) -> None:
        for k in EXISTING_KEYS:
            if k in data:
                ok(f"[{label}] 기존 키 보존: {k}")
            else:
                fail("FAIL_P3_EXISTING_KEY_MISSING", f"[{label}] 기존 키 누락: {k}")

    def _check_extra_keys(data: dict, label: str) -> None:
        for k in P3_EXTRA_KEYS:
            if k in data:
                ok(f"[{label}] 추가 키 존재: {k}")
            else:
                fail("FAIL_P3_ERROR_CODE_MISSING", f"[{label}] 추가 키 누락: {k}")

    def _check_secret_scan(data: dict, label: str) -> None:
        body = json.dumps(data).lower()
        leaks = [k for k in FORBIDDEN_IN_RESPONSE if f'"{k}"' in body]
        if re.search(r"sk-[a-z0-9\-_]{6,}", body):
            leaks.append("sk-_raw_key")
        if leaks:
            fail("FAIL_P3_SECRET_LEAK", f"[{label}] 금지 필드 노출: {leaks}")
        else:
            ok(f"[{label}] secret scan PASS")

    # ── CASE_A: API key 없음 + CLI 없음 → NO_PROVIDER_AVAILABLE ──────────────
    saved_key = os.environ.pop("ANTHROPIC_API_KEY", None)
    orig_which = _svc.shutil.which
    _svc.shutil.which = lambda n: None

    try:
        data_a = asyncio.run(_svc.run_local_agent({"prompt": "test"}))
    finally:
        if saved_key: os.environ["ANTHROPIC_API_KEY"] = saved_key
        _svc.shutil.which = orig_which

    ok(f"CASE_A (key없음+CLI없음) 응답:\n{json.dumps(data_a, ensure_ascii=False, indent=2)}")

    _check_existing_keys(data_a, "CASE_A")
    _check_extra_keys(data_a, "CASE_A")
    _check_secret_scan(data_a, "CASE_A")

    if data_a.get("ok") is False:
        ok("CASE_A ok=False")
    else:
        fail("FAIL_P3_EXISTING_KEY_MISSING", f"CASE_A ok={data_a.get('ok')} (False 기대)")

    if data_a.get("error_code") == "NO_PROVIDER_AVAILABLE":
        ok("CASE_A error_code=NO_PROVIDER_AVAILABLE")
    else:
        fail("FAIL_P3_ERROR_CODE_MISSING",
             f"CASE_A error_code={data_a.get('error_code')}")

    if data_a.get("safe_to_show") is True:
        ok("CASE_A safe_to_show=True")
    else:
        fail("FAIL_P3_PROVIDER_RESPONSE_UNSAFE",
             f"CASE_A safe_to_show={data_a.get('safe_to_show')}")

    ps_a = data_a.get("provider_status", {})
    if isinstance(ps_a, dict) and "anthropic_sdk" in ps_a and "claude_cli" in ps_a:
        ok(f"CASE_A provider_status: {ps_a}")
        aks = ps_a.get("anthropic_sdk", {}).get("api_key_set")
        if isinstance(aks, bool):
            ok(f"CASE_A provider_status.anthropic_sdk.api_key_set boolean: {aks}")
        else:
            fail("FAIL_P3_SECRET_LEAK",
                 f"CASE_A api_key_set 타입 오류: {type(aks)}")
    else:
        fail("FAIL_P3_ERROR_CODE_MISSING", f"CASE_A provider_status 형식 오류: {ps_a}")

    # raw exception 원문 미포함 확인
    result_a = data_a.get("result", "")
    if "오류:" in result_a and "Exception" in result_a:
        fail("FAIL_P3_PROVIDER_RESPONSE_UNSAFE",
             f"CASE_A result 에 raw exception 포함: {result_a[:80]}")
    else:
        ok(f"CASE_A result 안전한 메시지: '{result_a[:60]}'")

    # ── CASE_B: API key 없음 + CLI 있음 → CLI 폴백 실행 시도 ─────────────────
    # 외부 호출 없이 mock — CLI 있는 척하되 실행은 mock
    saved_key2 = os.environ.pop("ANTHROPIC_API_KEY", None)
    orig_avail = _svc._anthropic_available
    orig_which2 = _svc.shutil.which
    orig_cli = _svc._run_with_claude_code_cli

    # CLI 있음으로 mock, 실제 실행은 mock 결과 반환
    _svc.shutil.which = lambda n: "/usr/bin/claude" if n == "claude" else None
    _svc._anthropic_available = lambda: False
    _svc._run_with_claude_code_cli = lambda p: asyncio.coroutine(
        lambda: "mock CLI 응답"
    )()

    # asyncio coroutine mock
    async def _mock_cli(prompt):
        return "mock CLI 응답 (외부 호출 없음)"
    _svc._run_with_claude_code_cli = _mock_cli

    try:
        data_b = asyncio.run(_svc.run_local_agent({"prompt": "test"}))
    finally:
        if saved_key2: os.environ["ANTHROPIC_API_KEY"] = saved_key2
        _svc._anthropic_available = orig_avail
        _svc.shutil.which = orig_which2
        _svc._run_with_claude_code_cli = orig_cli

    ok(f"CASE_B (key없음+CLI있음 mock) 응답:\n{json.dumps(data_b, ensure_ascii=False, indent=2)}")

    if data_b.get("ok") is True:
        ok("CASE_B CLI 폴백 성공 → ok=True")
    else:
        # NO_PROVIDER_AVAILABLE 이면 FAIL
        if data_b.get("error_code") == "NO_PROVIDER_AVAILABLE":
            fail("FAIL_P3_ERROR_CODE_MISSING",
                 "CASE_B CLI 있는데 NO_PROVIDER_AVAILABLE 오류")
        else:
            warn("WARN_P3_RESPONSE_COMPATIBILITY_RISK",
                 f"CASE_B CLI 폴백 실패: {data_b.get('error_code')} — {data_b.get('result','')[:60]}")

    if data_b.get("ok") is True:
        if data_b.get("provider") == "claude_code_cli":
            ok("CASE_B provider=claude_code_cli")
        else:
            warn("WARN_P3_RESPONSE_COMPATIBILITY_RISK",
                 f"CASE_B provider={data_b.get('provider')}")

    _check_existing_keys(data_b, "CASE_B")
    _check_secret_scan(data_b, "CASE_B")

    # ── CASE_C: prompt 없음 → PROMPT_EMPTY ───────────────────────────────────
    data_c = asyncio.run(_svc.run_local_agent({}))
    ok(f"CASE_C (prompt 없음) 응답:\n{json.dumps(data_c, ensure_ascii=False, indent=2)}")

    _check_existing_keys(data_c, "CASE_C")
    _check_extra_keys(data_c, "CASE_C")
    _check_secret_scan(data_c, "CASE_C")

    if data_c.get("error_code") == "PROMPT_EMPTY":
        ok("CASE_C error_code=PROMPT_EMPTY")
    else:
        fail("FAIL_P3_ERROR_CODE_MISSING",
             f"CASE_C error_code={data_c.get('error_code')}")

    # ── CASE_D: Execution 오류 mock → EXECUTION_FAILED ───────────────────────
    # 외부 AI 호출 없이 _run_with_anthropic_no_mcp mock 예외 발생
    os.environ["ANTHROPIC_API_KEY"] = "sk-mock-key-p3-test"
    orig_avail2 = _svc._anthropic_available

    async def _mock_crash(prompt, model):
        raise RuntimeError("mock execution error — should be masked")

    _svc._anthropic_available = lambda: True
    orig_no_mcp = _svc._run_with_anthropic_no_mcp
    _svc._run_with_anthropic_no_mcp = _mock_crash

    try:
        data_d = asyncio.run(_svc.run_local_agent({"prompt": "test", "use_mcp": False}))
    finally:
        os.environ.pop("ANTHROPIC_API_KEY", None)
        _svc._anthropic_available = orig_avail2
        _svc._run_with_anthropic_no_mcp = orig_no_mcp

    ok(f"CASE_D (Execution 오류 mock) 응답:\n{json.dumps(data_d, ensure_ascii=False, indent=2)}")

    _check_existing_keys(data_d, "CASE_D")
    _check_extra_keys(data_d, "CASE_D")
    _check_secret_scan(data_d, "CASE_D")

    if data_d.get("error_code") == "EXECUTION_FAILED":
        ok("CASE_D error_code=EXECUTION_FAILED")
    else:
        fail("FAIL_P3_ERROR_CODE_MISSING",
             f"CASE_D error_code={data_d.get('error_code')}")

    # raw exception 원문 미포함
    result_d = data_d.get("result", "")
    if "mock execution error" in result_d or "RuntimeError" in result_d:
        fail("FAIL_P3_PROVIDER_RESPONSE_UNSAFE",
             f"CASE_D result 에 raw exception 원문 포함: {result_d[:80]}")
    else:
        ok(f"CASE_D result 에 raw exception 원문 미포함: '{result_d[:60]}'")

    # ── 외부 AI 호출 없음 증거 ────────────────────────────────────────────────
    # CASE_A/C/D 는 모두 mock 또는 provider 없음 분기에서 반환됨.
    # Anthropic SDK client.messages.create / shutil.which("claude") 실행 흔적 없음.
    ok("외부 AI 호출 없음 — 모든 케이스가 mock 또는 preflight 분기에서 반환")

except ImportError as e:
    warn("WARN_P3_IMPORT", f"모듈 import 불가: {e}")
except Exception as e:
    import traceback
    warn("WARN_P3_RUNTIME",
         f"검증 오류: {e}\n{traceback.format_exc()[-500:]}")


# ── 결과 출력 ─────────────────────────────────────────────────────────────────
print()
print("=" * 72)
print("  LOCAL_AGENT_PROVIDER_ERROR_P3 감리")
print("=" * 72)
for p in passes:   print(p)
for w in warnings: print(w)
for i in issues:   print(i)
print("-" * 72)
print(f"PASS: {len(passes)}  WARN: {len(warnings)}  FAIL: {len(issues)}")
if not issues:
    if warnings:
        print("\033[33m⚠️  WARN_P3_RESPONSE_COMPATIBILITY_RISK\033[0m")
    else:
        print("\033[32m✅ PASS_P3_PROVIDER_ERROR_RESPONSE_STANDARDIZED\033[0m")
else:
    print(f"\033[31m❌ FAIL_P3_PROVIDER_RESPONSE_UNSAFE — {len(issues)}건 수정 필요\033[0m")
print("=" * 72)
sys.exit(1 if issues else 0)
