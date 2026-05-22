"""audit_desktop_agent_common_spec.py
DESKTOP_AGENT_COMMON_SPEC_P5 감리

P5 범위: P1~P4 전체 구현을 정적+동적으로 통합 점검.
  - P1: /local-agent/preflight schema
  - P2: exception handler
  - P3: provider 오류 응답
  - P4: 테스트 파일 존재 및 PASS
  - 공통: 보안 / 배포 불변 / 회귀

검사 항목 (20개):
  01. /local-agent/health 라우트 존재
  02. /local-agent/preflight 라우트 존재
  03. schema_version = local_agent_preflight_v1 존재
  04. provider_status 필드명 사용
  05. optional_status 필드명 사용
  06. providers / optional 구 필드명 회귀 금지
  07. api_key_set boolean만 노출
  08. raw key 계열 금지 필드명 미사용
  09. CAD/CDP optional 이 core can_run 계산에 미포함
  10. blocking_reasons 와 warnings 분리
  11. HTTPException status code 보존
  12. RequestValidationError 422 보존
  13. 예상 밖 Exception 500 마스킹
  14. provider 오류 응답 정형 구조 존재
  15. 기존 /local-agent/run 기본 키 보존
  16. 외부 AI 실제 호출 없는 테스트 구조
  17. app_config 중앙 설정 훼손 없음
  18. 서버 배포/Docker 관련 변경 없음
  19. ui_dist 변경 없음
  20. 기존 dirty/untracked 미포함 (P5 허용 범위만)

Verdicts:
  PASS_P5_COMMON_SPEC_AUDIT_READY
  WARN_P5_AUDIT_COVERAGE_INSUFFICIENT
  FAIL_P5_AUDIT_GAP
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

LOCAL_SERVER = ROOT / "desktop" / "local_server.py"
LOCAL_SVC    = ROOT / "desktop" / "local_agent_service.py"
APP_CONFIG   = ROOT / "desktop" / "app_config.py"
TEST_P4      = ROOT / "tests" / "test_desktop_common_spec_preflight.py"
UI_DIST      = ROOT / "desktop" / "ui_dist"

P = "\033[32m[PASS]\033[0m"
W = "\033[33m[WARN]\033[0m"
F = "\033[31m[FAIL]\033[0m"

issues, warnings, passes = [], [], []
def fail(code, msg): issues.append(f"{F} {code} — {msg}")
def warn(code, msg): warnings.append(f"{W} {code} — {msg}")
def ok(msg):         passes.append(f"{P} {msg}")

srv = LOCAL_SERVER.read_text(encoding="utf-8")
svc = LOCAL_SVC.read_text(encoding="utf-8")

FORBIDDEN_RAW_KEYS = {
    "api_key", "apikey", "raw_api_key", "token", "bearer",
    "cookie", "session", "authorization", "database_url",
    "password", "secret",
}
SK_PAT = re.compile(r"sk-[A-Za-z0-9\-_]{6,}")


# ── helper ────────────────────────────────────────────────────────────────────
def _strip_comments(text: str) -> str:
    out = []
    for ln in text.split("\n"):
        if ln.lstrip().startswith("#"):
            continue
        idx = ln.find("#")
        out.append(ln[:idx] if idx >= 0 else ln)
    return "\n".join(out)

def _mock_req(method="GET", path="/test"):
    req = MagicMock()
    req.method = method
    req.url.path = path
    return req

def _reload_desktop():
    for mn in list(sys.modules.keys()):
        if mn.startswith("desktop"):
            del sys.modules[mn]


# ══════════════════════════════════════════════════════════════════════════════
# 01. /local-agent/health 라우트 존재
# ══════════════════════════════════════════════════════════════════════════════
if "/local-agent/health" in srv:
    ok("01. /local-agent/health 라우트 소스 존재")
else:
    fail("FAIL_P5_AUDIT_GAP", "01. /local-agent/health 라우트 없음")


# ══════════════════════════════════════════════════════════════════════════════
# 02. /local-agent/preflight 라우트 존재
# ══════════════════════════════════════════════════════════════════════════════
if "/local-agent/preflight" in srv:
    ok("02. /local-agent/preflight 라우트 소스 존재")
else:
    fail("FAIL_P5_AUDIT_GAP", "02. /local-agent/preflight 라우트 없음")


# ══════════════════════════════════════════════════════════════════════════════
# 03. schema_version = local_agent_preflight_v1
# ══════════════════════════════════════════════════════════════════════════════
if "local_agent_preflight_v1" in svc:
    ok("03. schema_version = local_agent_preflight_v1 소스 존재")
else:
    fail("FAIL_P5_AUDIT_GAP", "03. schema_version 값 미발견")


# ══════════════════════════════════════════════════════════════════════════════
# 04. provider_status 필드명 사용
# ══════════════════════════════════════════════════════════════════════════════
if "provider_status" in svc:
    ok("04. provider_status 필드명 소스 존재")
else:
    fail("FAIL_P5_AUDIT_GAP", "04. provider_status 필드명 없음")


# ══════════════════════════════════════════════════════════════════════════════
# 05. optional_status 필드명 사용
# ══════════════════════════════════════════════════════════════════════════════
if "optional_status" in svc:
    ok("05. optional_status 필드명 소스 존재")
else:
    fail("FAIL_P5_AUDIT_GAP", "05. optional_status 필드명 없음")


# ══════════════════════════════════════════════════════════════════════════════
# 06. providers / optional 구 필드명 회귀 금지
# ══════════════════════════════════════════════════════════════════════════════
# preflight 함수 소스만 검사 (health 등 다른 함수는 별도 스코프)
preflight_fn_idx = svc.find("def local_agent_preflight(")
preflight_fn_end = svc.find("\ndef ", preflight_fn_idx + 1)
preflight_fn_src = svc[preflight_fn_idx: preflight_fn_end if preflight_fn_end > 0 else len(svc)]

old_fields_in_preflight = []
if '"providers"' in preflight_fn_src:
    old_fields_in_preflight.append("providers")
if '"optional"' in preflight_fn_src:
    old_fields_in_preflight.append("optional")

if old_fields_in_preflight:
    fail("FAIL_P5_AUDIT_GAP",
         f"06. preflight 함수에 구 필드명 회귀: {old_fields_in_preflight}")
else:
    ok("06. preflight 함수에 구 필드명(providers/optional) 미사용")


# ══════════════════════════════════════════════════════════════════════════════
# 07. api_key_set boolean — 동적 검증
# ══════════════════════════════════════════════════════════════════════════════
try:
    _reload_desktop()
    from desktop import local_agent_service as _svc_mod
    from desktop import local_server as _ls_mod
    _ls_mod._remote_enabled = lambda: True
    _ls_mod._verify_token   = lambda t: True

    saved = os.environ.pop("ANTHROPIC_API_KEY", None)
    orig_which = _svc_mod.shutil.which
    _svc_mod.shutil.which = lambda n: None

    try:
        from fastapi.testclient import TestClient
        _client = TestClient(_ls_mod.app, raise_server_exceptions=False)
        r = _client.get("/local-agent/preflight")
        data = r.json()
    finally:
        if saved: os.environ["ANTHROPIC_API_KEY"] = saved
        _svc_mod.shutil.which = orig_which

    top_aks = data.get("api_key_set")
    nested_aks = data.get("provider_status", {}).get("anthropic_sdk", {}).get("api_key_set")

    if isinstance(top_aks, bool) and isinstance(nested_aks, bool):
        ok(f"07. api_key_set top={top_aks} nested={nested_aks} — 모두 boolean")
    else:
        fail("FAIL_P5_AUDIT_GAP",
             f"07. api_key_set 타입 오류 top={type(top_aks)} nested={type(nested_aks)}")

    # raw API key 원문 미노출
    resp_str = json.dumps(data)
    raw_leaks = [k for k in FORBIDDEN_RAW_KEYS
                 if f'"{k}"' in resp_str.lower()
                 and not (k == "api_key" and "api_key_set" in resp_str.lower())]
    if raw_leaks:
        fail("FAIL_P5_AUDIT_GAP", f"07. 응답에 금지 필드 노출: {raw_leaks}")
    else:
        ok("07-extra. 응답 금지 필드 미노출")

except Exception as e:
    warn("WARN_P5_DYNAMIC", f"07 동적 검증 오류: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# 08. raw key 계열 금지 필드명 소스 미사용 (주석 제거 후)
# ══════════════════════════════════════════════════════════════════════════════
# preflight/run 반환 dict 안에서만 검사
run_fn_idx = svc.find("async def run_local_agent(")
run_fn_end = svc.find("\nasync def ", run_fn_idx + 1)
run_fn_src  = svc[run_fn_idx: run_fn_end if run_fn_end > 0 else len(svc)]
check_src = _strip_comments(preflight_fn_src + run_fn_src)

raw_in_src = []
for k in FORBIDDEN_RAW_KEYS:
    if f'"{k}"' in check_src.lower() and k != "api_key":  # api_key_set 허용
        raw_in_src.append(k)
    elif k == "api_key" and '"api_key"' in check_src and '"api_key_set"' not in check_src:
        raw_in_src.append(k)

if raw_in_src:
    fail("FAIL_P5_AUDIT_GAP",
         f"08. preflight/run 반환 소스에 금지 필드명: {raw_in_src}")
else:
    ok("08. preflight/run 반환 소스에 raw key 금지 필드명 없음")

# sk- raw key 소스 미포함
if SK_PAT.search(_strip_comments(svc)):
    fail("FAIL_P5_AUDIT_GAP", "08. 소스에 sk- raw key 패턴 발견")
else:
    ok("08-extra. 소스 sk- raw key 없음")


# ══════════════════════════════════════════════════════════════════════════════
# 09. CAD/CDP optional 이 core can_run 계산에 미포함
# ══════════════════════════════════════════════════════════════════════════════
# can_run 계산 라인만 검사 — cad_ok/cdp_ok 조건 미포함 확인
# "can_run =" 로 시작하는 라인만 추출 (주석/blank 제외)
can_run_lines = [
    ln for ln in preflight_fn_src.split("\n")
    if re.match(r"\s*can_run\s*=", ln)
]
bad_can_run = [ln for ln in can_run_lines if "cad_ok" in ln or "cdp_ok" in ln]
if bad_can_run:
    fail("FAIL_P5_AUDIT_GAP",
         f"09. can_run 계산 라인에 cad_ok/cdp_ok 포함: {bad_can_run}")
else:
    ok(f"09. can_run 계산 라인에 cad_ok/cdp_ok 미포함: {can_run_lines}")

# 동적: CAD/CDP down → can_run=True 검증
try:
    _reload_desktop()
    from desktop import local_agent_service as _svc_mod2
    from desktop import local_server as _ls_mod2
    _ls_mod2._remote_enabled = lambda: True
    _ls_mod2._verify_token   = lambda t: True

    os.environ["ANTHROPIC_API_KEY"] = "sk-mock-p5-audit"
    orig_avail = _svc_mod2._anthropic_available
    orig_mcp   = _svc_mod2._find_mcp_server
    orig_cdp   = _svc_mod2._check_cdp_available
    _svc_mod2._anthropic_available  = lambda: True
    _svc_mod2._find_mcp_server      = lambda: None
    _svc_mod2._check_cdp_available  = lambda: False

    try:
        from fastapi.testclient import TestClient
        _c2 = TestClient(_ls_mod2.app, raise_server_exceptions=False)
        d2  = _c2.get("/local-agent/preflight").json()
    finally:
        os.environ.pop("ANTHROPIC_API_KEY", None)
        _svc_mod2._anthropic_available  = orig_avail
        _svc_mod2._find_mcp_server      = orig_mcp
        _svc_mod2._check_cdp_available  = orig_cdp

    if d2.get("can_run") is True:
        ok("09-dynamic. CAD/CDP down → can_run=True 유지")
    else:
        fail("FAIL_P5_AUDIT_GAP",
             f"09-dynamic. CAD/CDP down 인데 can_run={d2.get('can_run')}")

    warns_d2 = d2.get("warnings", [])
    if "CAD_MCP_SERVER_NOT_FOUND" in warns_d2 and "CDP_BROWSER_NOT_RUNNING" in warns_d2:
        ok("09-dynamic. CAD/CDP 경고가 warnings 에 기록됨")
    else:
        fail("FAIL_P5_AUDIT_GAP",
             f"09-dynamic. CAD/CDP 경고 warnings 미기록: {warns_d2}")

except Exception as e:
    warn("WARN_P5_DYNAMIC", f"09 동적 검증 오류: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# 10. blocking_reasons 와 warnings 분리
# ══════════════════════════════════════════════════════════════════════════════
if "blocking_reasons" in svc and "warnings" in svc:
    ok("10. blocking_reasons / warnings 양쪽 소스 존재")
else:
    fail("FAIL_P5_AUDIT_GAP", "10. blocking_reasons 또는 warnings 소스 없음")

# CAD/CDP 경고가 blocking_reasons 가 아닌 warnings_list 에 들어가는지 소스 확인
if "warnings_list.append" in svc and "CAD_MCP_SERVER_NOT_FOUND" in svc:
    ok("10. CAD/CDP 경고가 warnings_list 에 추가되는 소스 확인")
else:
    fail("FAIL_P5_AUDIT_GAP", "10. CAD/CDP 경고가 warnings_list 에 추가되지 않음")

if "blocking_reasons.append" in svc and "NO_PROVIDER_AVAILABLE" in svc:
    ok("10. NO_PROVIDER_AVAILABLE 이 blocking_reasons 에 추가되는 소스 확인")
else:
    fail("FAIL_P5_AUDIT_GAP", "10. NO_PROVIDER_AVAILABLE blocking_reasons 소스 없음")


# ══════════════════════════════════════════════════════════════════════════════
# 11~13. exception handler — 함수 직접 호출
# ══════════════════════════════════════════════════════════════════════════════
try:
    _reload_desktop()
    from fastapi import HTTPException as _HTTPEx
    from fastapi.exceptions import RequestValidationError as _RVE
    from desktop import local_server as _ls3

    req = _mock_req()

    # 11. HTTPException status 보존
    for code in (404, 403, 401):
        r = asyncio.run(_ls3._http_exception_handler(req, _HTTPEx(status_code=code)))
        if r.status_code == code:
            ok(f"11. HTTPException {code} status 보존")
        else:
            fail("FAIL_P5_AUDIT_GAP",
                 f"11. HTTPException {code} → status={r.status_code}")

    # 12. RequestValidationError 422
    rve = _RVE([{"loc": ("body",), "msg": "required", "type": "missing"}])
    r422 = asyncio.run(_ls3._validation_exception_handler(req, rve))
    if r422.status_code == 422:
        ok("12. RequestValidationError → 422 보존")
    else:
        fail("FAIL_P5_AUDIT_GAP", f"12. RequestValidationError → {r422.status_code}")

    # 13. 예상 밖 Exception → 500 마스킹
    exc_secret = RuntimeError("secret: sk-real-abc123 DB pass=admin")
    r500 = asyncio.run(_ls3._generic_exception_handler(req, exc_secret))
    if r500.status_code == 500:
        ok("13. Exception → 500 마스킹")
    else:
        fail("FAIL_P5_AUDIT_GAP", f"13. Exception → status={r500.status_code}")

    body500 = r500.body.decode()
    if "sk-real-abc123" in body500 or "admin" in body500:
        fail("FAIL_P5_AUDIT_GAP", f"13. 500 응답에 secret 노출: {body500[:80]}")
    else:
        ok("13-extra. 500 응답 secret 미노출")

    if "Traceback" in body500 or "RuntimeError" in body500:
        fail("FAIL_P5_AUDIT_GAP", f"13. 500 응답에 traceback/type 노출")
    else:
        ok("13-extra. 500 응답에 traceback/exception type 미노출")

except Exception as e:
    import traceback as _tb
    warn("WARN_P5_DYNAMIC", f"11~13 동적 검증 오류: {e}\n{_tb.format_exc()[-300:]}")


# ══════════════════════════════════════════════════════════════════════════════
# 14. provider 오류 응답 정형 구조 존재
# ══════════════════════════════════════════════════════════════════════════════
if "_provider_error_response" in svc:
    ok("14. _provider_error_response 빌더 소스 존재")
else:
    fail("FAIL_P5_AUDIT_GAP", "14. _provider_error_response 빌더 없음")

p3_keys = ("error_code", "user_message", "next_actions", "provider_status",
           "can_retry", "safe_to_show")
for k in p3_keys:
    if f'"{k}"' in svc:
        ok(f"14. P3 추가 키 소스 존재: {k}")
    else:
        fail("FAIL_P5_AUDIT_GAP", f"14. P3 추가 키 소스 없음: {k}")

# 동적: NO_PROVIDER_AVAILABLE 응답 shape
try:
    _reload_desktop()
    from desktop import local_agent_service as _svc_run
    saved2 = os.environ.pop("ANTHROPIC_API_KEY", None)
    orig_w = _svc_run.shutil.which
    _svc_run.shutil.which = lambda n: None
    _svc_run._anthropic_available = lambda: False
    try:
        d_run = asyncio.run(_svc_run.run_local_agent({"prompt": "test"}))
    finally:
        if saved2: os.environ["ANTHROPIC_API_KEY"] = saved2
        _svc_run.shutil.which = orig_w

    for k in ("ok", "result", "provider", "model", "tool_calls",
              "error_code", "user_message", "next_actions",
              "provider_status", "can_retry", "safe_to_show"):
        if k in d_run:
            ok(f"14-dynamic. run 오류 응답 키 존재: {k}")
        else:
            fail("FAIL_P5_AUDIT_GAP", f"14-dynamic. run 오류 응답 키 누락: {k}")

except Exception as e:
    warn("WARN_P5_DYNAMIC", f"14 동적 검증 오류: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# 15. 기존 /local-agent/run 기본 키 보존
# ══════════════════════════════════════════════════════════════════════════════
# 정상 실행 경로에 ok/result/provider/model/tool_calls 반환 소스 확인
run_success_ret = 'return {"ok": True, "result": result, "provider": provider, "model": model, "tool_calls": 0}'
if run_success_ret in svc:
    ok("15. /local-agent/run 정상 반환에 기존 5개 키 보존")
else:
    warn("WARN_P5_AUDIT_COVERAGE_INSUFFICIENT",
         "15. run 정상 반환 구조 소스 변형 확인 필요")


# ══════════════════════════════════════════════════════════════════════════════
# 16. 외부 AI 실제 호출 없는 테스트 구조 확인
# ══════════════════════════════════════════════════════════════════════════════
if TEST_P4.exists():
    t_src = TEST_P4.read_text(encoding="utf-8")
    markers = ["monkeypatch", "mock", "_should_not_call", "AssertionError"]
    found = [m for m in markers if m in t_src]
    if len(found) >= 3:
        ok(f"16. P4 테스트 파일에 외부 호출 차단 패턴 확인: {found}")
    else:
        warn("WARN_P5_AUDIT_COVERAGE_INSUFFICIENT",
             f"16. P4 테스트 외부 호출 차단 패턴 부족: {found}")

    # pytest 실행
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(TEST_P4), "-q", "--tb=no"],
        cwd=ROOT, capture_output=True, text=True, timeout=60,
    )
    last_line = result.stdout.strip().split("\n")[-1]
    if result.returncode == 0:
        ok(f"16-pytest. P4 테스트 PASS: {last_line}")
    else:
        fail("FAIL_P5_AUDIT_GAP",
             f"16-pytest. P4 테스트 FAIL: {last_line}")
else:
    fail("FAIL_P5_AUDIT_GAP", "16. P4 테스트 파일 없음: tests/test_desktop_common_spec_preflight.py")


# ══════════════════════════════════════════════════════════════════════════════
# 17. app_config 중앙 설정 훼손 없음
# ══════════════════════════════════════════════════════════════════════════════
diff_cfg = subprocess.run(
    ["git", "diff", "HEAD", "--", "desktop/app_config.py"],
    cwd=ROOT, capture_output=True, text=True, timeout=10,
)
if diff_cfg.stdout.strip():
    fail("FAIL_P5_AUDIT_GAP",
         f"17. app_config.py 변경 감지:\n{diff_cfg.stdout[:300]}")
else:
    ok("17. app_config.py 변경 없음")


# ══════════════════════════════════════════════════════════════════════════════
# 18. 서버 배포/Docker 관련 변경 없음
# ══════════════════════════════════════════════════════════════════════════════
deploy_files = [
    "docker-compose.yml", "docker-compose.yaml",
    "Dockerfile", "dockerfile",
    ".github/workflows",
    "nginx.conf",
]
for df in deploy_files:
    diff_d = subprocess.run(
        ["git", "diff", "HEAD", "--", df],
        cwd=ROOT, capture_output=True, text=True, timeout=10,
    )
    if diff_d.stdout.strip():
        fail("FAIL_P5_AUDIT_GAP", f"18. 배포 파일 변경 감지: {df}")

# untracked 배포 파일 없음
status = subprocess.run(
    ["git", "status", "--short"],
    cwd=ROOT, capture_output=True, text=True, timeout=10,
)
deploy_untracked = [l for l in status.stdout.split("\n")
                    if l.strip().startswith("??") and
                    any(d in l for d in ("Dockerfile", "docker-compose", ".github", "nginx"))]
if deploy_untracked:
    fail("FAIL_P5_AUDIT_GAP", f"18. 배포 untracked 파일 발견: {deploy_untracked}")
else:
    ok("18. 서버 배포/Docker 관련 변경 없음")


# ══════════════════════════════════════════════════════════════════════════════
# 19. ui_dist 변경 없음
# ══════════════════════════════════════════════════════════════════════════════
diff_ui = subprocess.run(
    ["git", "diff", "HEAD", "--", "desktop/ui_dist/"],
    cwd=ROOT, capture_output=True, text=True, timeout=10,
)
ui_untracked = [l for l in status.stdout.split("\n")
                if l.strip().startswith("??") and "ui_dist" in l]

if diff_ui.stdout.strip() or ui_untracked:
    fail("FAIL_P5_AUDIT_GAP",
         f"19. ui_dist 변경 감지 diff={bool(diff_ui.stdout.strip())} untracked={ui_untracked}")
else:
    ok("19. ui_dist 변경 없음")


# ══════════════════════════════════════════════════════════════════════════════
# 20. 기존 dirty/untracked 미포함 (P5 허용 범위만)
# ══════════════════════════════════════════════════════════════════════════════
# 이번 작업(P1~P5) 허용 변경 목록
ALLOWED_MODIFIED = {
    "desktop/local_agent_service.py",
    "desktop/local_server.py",
    "scripts/archive/data/chrome_ui_monitor_state.json",  # pre-existing
    "scripts/navigator.py",                                # pre-existing
}
ALLOWED_UNTRACKED_PREFIXES = (
    "scripts/ops/audit_local_agent_preflight_p1.py",
    "scripts/ops/audit_local_agent_exception_handler_p2.py",
    "scripts/ops/audit_local_agent_provider_error_p3.py",
    "scripts/ops/audit_desktop_agent_common_spec.py",
    "scripts/ops/check_naver_mail.py",    # pre-existing untracked
    "scripts/ops/check_remote_browser.py",
    "scripts/ops/naver_login_and_mail.py",
    "scripts/ops/verify_remote_browser.py",
    "tests/test_desktop_common_spec_preflight.py",
)

violations = []
for raw_line in status.stdout.split("\n"):
    if not raw_line.strip():
        continue
    # git status --short 형식: "XY path" — XY 는 2글자, 공백 1개, 경로
    status_code = raw_line[:2].strip()
    filepath = raw_line[3:].strip().replace("\\", "/")

    if status_code == "M":
        if filepath not in ALLOWED_MODIFIED:
            violations.append(f"수정됨(허용외): {filepath}")
    elif status_code == "??":
        if not any(filepath.endswith(p.replace("\\", "/").split("/")[-1])
                   for p in ALLOWED_UNTRACKED_PREFIXES):
            violations.append(f"untracked(허용외): {filepath}")

if violations:
    fail("FAIL_P5_AUDIT_GAP",
         f"20. 허용 범위 외 변경/untracked:\n  " + "\n  ".join(violations))
else:
    ok("20. dirty/untracked 파일 모두 허용 범위 내")


# ══════════════════════════════════════════════════════════════════════════════
# 결과 출력 + 리포트 저장
# ══════════════════════════════════════════════════════════════════════════════
import datetime
report = {
    "audit": "DESKTOP_AGENT_COMMON_SPEC_P5",
    "timestamp": datetime.datetime.now().isoformat(),
    "pass": len(passes),
    "warn": len(warnings),
    "fail": len(issues),
    "verdict": (
        "PASS_P5_COMMON_SPEC_AUDIT_READY"   if not issues and not warnings else
        "WARN_P5_AUDIT_COVERAGE_INSUFFICIENT" if not issues else
        "FAIL_P5_AUDIT_GAP"
    ),
    "issues":   [i for i in issues],
    "warnings": [w for w in warnings],
}

report_path = ROOT / "data" / "audit_desktop_agent_common_spec_latest.json"
report_path.parent.mkdir(exist_ok=True)
report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

print()
print("=" * 72)
print("  DESKTOP_AGENT_COMMON_SPEC_P5 감리")
print("=" * 72)
for p in passes:   print(p)
for w in warnings: print(w)
for i in issues:   print(i)
print("-" * 72)
print(f"PASS: {len(passes)}  WARN: {len(warnings)}  FAIL: {len(issues)}")
print(f"리포트: {report_path}")
if not issues:
    if warnings:
        print("\033[33m⚠️  WARN_P5_AUDIT_COVERAGE_INSUFFICIENT\033[0m")
    else:
        print("\033[32m✅ PASS_P5_COMMON_SPEC_AUDIT_READY\033[0m")
else:
    print(f"\033[31m❌ FAIL_P5_AUDIT_GAP — {len(issues)}건\033[0m")
print("=" * 72)
sys.exit(1 if issues else 0)
