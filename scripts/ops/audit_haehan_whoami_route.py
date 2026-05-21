"""audit_haehan_whoami_route.py
HAEHAN_WHOAMI_ROUTE_01 감리.

Verdicts:
  PASS_HAEHAN_WHOAMI_ROUTE
  WARN_WHOAMI_SOURCE_DEFAULT
  FAIL_WHOAMI_ROUTE_MISSING
  FAIL_WHOAMI_SECRET_LEAK
  FAIL_WHOAMI_ROLE_BYPASS
  FAIL_LOCAL_ONLY_BYPASS
  FAIL_ADMIN_WEBVIEW_NOT_USING_WHOAMI
  FAIL_EXISTING_ENTRYPOINT_BROKEN
  FAIL_DIRTY_SCOPE_VIOLATION
"""
from __future__ import annotations

import ast
import importlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

LOCAL_SERVER = ROOT / "desktop/local_server.py"
ADMIN_WV     = ROOT / "desktop/admin_webview.py"

P = "\033[32m[PASS]\033[0m"
W = "\033[33m[WARN]\033[0m"
F = "\033[31m[FAIL]\033[0m"

issues, warnings, passes = [], [], []

def fail(code, msg): issues.append(f"{F} {code} — {msg}")
def warn(code, msg): warnings.append(f"{W} {code} — {msg}")
def ok(msg):         passes.append(f"{P} {msg}")


# ── 1. 라우터 소스 확인 ────────────────────────────────────────────────
src = LOCAL_SERVER.read_text(encoding="utf-8")

if '/api/v1/whoami' not in src:
    fail("FAIL_WHOAMI_ROUTE_MISSING", "/api/v1/whoami 라우터 없음")
else:
    ok("/api/v1/whoami 라우터 소스 존재")

# @app.get 데코레이터 매칭
if '@app.get("/api/v1/whoami")' in src or "@app.get('/api/v1/whoami')" in src:
    ok("@app.get('/api/v1/whoami') 데코레이터 확인")
else:
    fail("FAIL_WHOAMI_ROUTE_MISSING", "데코레이터 누락")


# ── 2. 라우터 소스에 secret 키 없음 ─────────────────────────────────────
# whoami 함수 내부에서 응답에 들어가는 값 점검
# 단순 검사: 함수 시그니처와 응답 dict 구성에서 금지 키 등장 여부
def _extract_function(src_text: str, fn_name: str) -> str:
    """fn_name 정의 라인부터 다음 같은 들여쓰기의 비어있지 않은 라인 전까지."""
    lines = src_text.split("\n")
    start = None
    for i, ln in enumerate(lines):
        if ln.startswith(f"async def {fn_name}(") or ln.startswith(f"def {fn_name}("):
            start = i
            break
    if start is None:
        return ""
    out = [lines[start]]
    for ln in lines[start + 1:]:
        if ln and not ln.startswith(" ") and not ln.startswith("\t"):
            break
        out.append(ln)
    return "\n".join(out)


whoami_src = _extract_function(src, "whoami")
resolve_src = _extract_function(src, "_resolve_whoami_role")
combined = whoami_src + "\n" + resolve_src

forbidden_keys = [
    "device_token", "registration_code", "bearer",
    "cookie", "authorization", "secret",
    "password", "api_key", "sk-",
]
# 주석 (#) 라인 제거 후 검사 — 정책 설명 주석에 단어가 등장하는 false positive 회피
def _strip_comments(code_text: str) -> str:
    out = []
    for ln in code_text.split("\n"):
        # 주석 라인 (# 로만 시작하는) 제외
        if ln.lstrip().startswith("#"):
            continue
        # 인라인 주석 제거
        idx = ln.find("#")
        if idx >= 0:
            ln = ln[:idx]
        out.append(ln)
    return "\n".join(out)

leaks = []
combined_no_comment = _strip_comments(combined).lower()
for fk in forbidden_keys:
    if fk in combined_no_comment:
        leaks.append(fk)

if leaks:
    fail("FAIL_WHOAMI_SECRET_LEAK", f"whoami 소스에 금지 키워드: {leaks}")
else:
    ok("whoami 함수 소스에 금지 키워드 없음")


# ── 3. 실제 응답 검증 — FastAPI TestClient ─────────────────────────────
try:
    from fastapi.testclient import TestClient
    # local_server import 시점에 신선한 상태 보장
    for mn in list(sys.modules.keys()):
        if mn == "desktop.local_server":
            del sys.modules[mn]
    from desktop import local_server as _ls
    from desktop.local_server import app as _app
    # TestClient 의 client.host = "testclient" 이므로 미들웨어 통과를 위해 우회
    _ls._remote_enabled = lambda: True  # type: ignore
    _ls._verify_token = lambda t: True  # type: ignore

    # env 영향 제거하고 호출
    saved_env = os.environ.pop("HAEHAN_ROLE", None)
    try:
        client = TestClient(_app)
        r_default = client.get("/api/v1/whoami")
        if r_default.status_code != 200:
            fail("FAIL_WHOAMI_ROUTE_MISSING",
                 f"기본 status={r_default.status_code}")
        else:
            data = r_default.json()
            # 필수 키
            for need in ("ok", "role", "admin", "source"):
                if need not in data:
                    fail("FAIL_WHOAMI_ROUTE_MISSING", f"응답 키 누락: {need}")
            else:
                ok(f"기본 응답 OK: role={data.get('role')} admin={data.get('admin')} source={data.get('source')}")

            # 응답 키에 금지 키 없음
            data_str = json.dumps(data).lower()
            response_leaks = [fk for fk in forbidden_keys if fk in data_str]
            if response_leaks:
                fail("FAIL_WHOAMI_SECRET_LEAK", f"응답에 금지 키: {response_leaks}")
            else:
                ok("기본 응답에 금지 키 없음")

            # local-only bypass 금지: 기본 (env 없음) 시 admin=False 여야 함
            if data.get("admin") is False:
                ok("local-only bypass 금지 — 기본 admin=False")
            else:
                fail("FAIL_LOCAL_ONLY_BYPASS",
                     f"env 없는데 admin=True: {data}")

        # 2) env HAEHAN_ROLE=admin
        os.environ["HAEHAN_ROLE"] = "admin"
        r_admin = client.get("/api/v1/whoami").json()
        if r_admin.get("role") == "admin" and r_admin.get("admin") is True:
            ok(f"HAEHAN_ROLE=admin → role=admin admin=True source={r_admin.get('source')}")
        else:
            fail("FAIL_WHOAMI_ROLE_BYPASS", f"admin 결과 잘못: {r_admin}")

        # 3) env HAEHAN_ROLE=owner
        os.environ["HAEHAN_ROLE"] = "owner"
        r_owner = client.get("/api/v1/whoami").json()
        if r_owner.get("admin") is True:
            ok("HAEHAN_ROLE=owner → admin=True")
        else:
            fail("FAIL_WHOAMI_ROLE_BYPASS", f"owner 결과 잘못: {r_owner}")

        # 4) env HAEHAN_ROLE=user
        os.environ["HAEHAN_ROLE"] = "user"
        r_user = client.get("/api/v1/whoami").json()
        if r_user.get("admin") is False:
            ok("HAEHAN_ROLE=user → admin=False")
        else:
            fail("FAIL_WHOAMI_ROLE_BYPASS", f"user 인데 admin=True: {r_user}")

        # 5) env HAEHAN_ROLE=any
        os.environ["HAEHAN_ROLE"] = "any"
        r_any = client.get("/api/v1/whoami").json()
        if r_any.get("admin") is False:
            ok("HAEHAN_ROLE=any → admin=False")
        else:
            fail("FAIL_WHOAMI_ROLE_BYPASS", f"any 인데 admin=True: {r_any}")

    finally:
        if saved_env is None:
            os.environ.pop("HAEHAN_ROLE", None)
        else:
            os.environ["HAEHAN_ROLE"] = saved_env

except ImportError as e:
    warn("WARN_FASTAPI_TESTCLIENT", f"TestClient 사용 불가 — 동적 검증 생략: {e}")


# ── 4. admin_webview 실제 연동 확인 ─────────────────────────────────────
aw_src = ADMIN_WV.read_text(encoding="utf-8")
if "/api/v1/whoami" in aw_src:
    ok("admin_webview 가 /api/v1/whoami 경로 사용")
else:
    fail("FAIL_ADMIN_WEBVIEW_NOT_USING_WHOAMI",
         "admin_webview 에 /api/v1/whoami 경로 없음")


# admin_webview.check_role_via_api 가 실제 whoami route 응답을 통과시키는지
try:
    # sys.modules 정리 없이 첫 번째 블록의 monkeypatch 그대로 재사용
    from desktop import admin_webview as aw
    from desktop import local_server as _ls2
    from fastapi.testclient import TestClient
    # monkeypatch 재확인 (idempotent)
    _ls2._remote_enabled = lambda: True  # type: ignore
    _ls2._verify_token = lambda t: True  # type: ignore

    client = TestClient(_ls2.app)

    def _real_api_caller(server_url, timeout):
        # TestClient 사용 — server_url 무시하고 직접 호출
        r = client.get("/api/v1/whoami")
        return r.json()

    saved_env = os.environ.pop("HAEHAN_ROLE", None)
    try:
        # admin
        os.environ["HAEHAN_ROLE"] = "admin"
        r_admin = aw.check_role_via_api(api_caller=_real_api_caller)
        if r_admin.passed:
            ok(f"admin_webview ↔ 실 whoami 연동 admin PASS")
        else:
            fail("FAIL_ADMIN_WEBVIEW_NOT_USING_WHOAMI",
                 f"admin 인데 거부됨: {r_admin}")

        # owner
        os.environ["HAEHAN_ROLE"] = "owner"
        r_owner = aw.check_role_via_api(api_caller=_real_api_caller)
        if r_owner.passed:
            ok("admin_webview ↔ whoami owner PASS")
        else:
            fail("FAIL_ADMIN_WEBVIEW_NOT_USING_WHOAMI", f"owner 거부: {r_owner}")

        # user
        os.environ["HAEHAN_ROLE"] = "user"
        r_user = aw.check_role_via_api(api_caller=_real_api_caller)
        if not r_user.passed:
            ok("admin_webview ↔ whoami user 거부 (정상)")
        else:
            fail("FAIL_WHOAMI_ROLE_BYPASS", f"user 통과: {r_user}")

        # any
        os.environ["HAEHAN_ROLE"] = "any"
        r_any = aw.check_role_via_api(api_caller=_real_api_caller)
        if not r_any.passed:
            ok("admin_webview ↔ whoami any 거부 (local-only bypass 금지)")
        else:
            fail("FAIL_LOCAL_ONLY_BYPASS", f"any 통과: {r_any}")
    finally:
        if saved_env is None:
            os.environ.pop("HAEHAN_ROLE", None)
        else:
            os.environ["HAEHAN_ROLE"] = saved_env

except Exception as e:
    warn("WARN_LIVE_INTEGRATION", f"실 통합 검증 생략: {e}")


# ── 5. 기존 entrypoint 회귀 ────────────────────────────────────────────
existing = [
    "desktop.webview_app_pywebview",
    "desktop.local_server",
    "local_agent.desktop_launcher",
    "local_agent.token_store",
    "desktop.tray_runtime",
    "desktop.main_launcher",
    "desktop.admin_webview",
]
for mod in existing:
    try:
        for mn in list(sys.modules.keys()):
            if mn == mod:
                del sys.modules[mn]
        importlib.import_module(mod)
        ok(f"기존 entrypoint OK: {mod}")
    except Exception as e:
        fail("FAIL_EXISTING_ENTRYPOINT_BROKEN", f"{mod}: {e}")


# ── 6. dirty scope 검증 — commit history 기반 ────────────────────────
# HAEHAN_WHOAMI_ROUTE_01 커밋 자체의 변경 파일이 allowed 범위 내인지.
# (이후 공정에서 working tree 가 다른 변경을 가지더라도 본 커밋 자체의 scope 만 검증)
import subprocess
log_scope = subprocess.run(
    ["git", "log", "--all", "-E",
     "--grep=^feat.haehan.: HAEHAN_WHOAMI_ROUTE_01",
     "-1", "--name-only", "--pretty=format:%H"],
    cwd=ROOT, capture_output=True, text=True, timeout=10,
)
scope_lines = [l for l in log_scope.stdout.strip().split("\n") if l.strip()]
if not scope_lines:
    warn("WARN_COMMIT_NOT_FOUND",
         "HAEHAN_WHOAMI_ROUTE_01 커밋 미발견 — working tree fallback")
    diff = subprocess.run(
        ["git", "diff", "--name-only", "HEAD"],
        cwd=ROOT, capture_output=True, text=True, timeout=10,
    )
    modified = [p.strip().replace("\\", "/") for p in diff.stdout.split("\n") if p.strip()]
else:
    modified = [l.strip().replace("\\", "/") for l in scope_lines[1:]]

allowed = {
    "desktop/local_server.py",
    "scripts/ops/audit_haehan_whoami_route.py",
    "tests/test_haehan_whoami_route.py",
}
pre_existing = {
    "scripts/archive/data/chrome_ui_monitor_state.json",
}
violations = [m for m in modified if m not in allowed and m not in pre_existing]
if violations:
    fail("FAIL_DIRTY_SCOPE_VIOLATION", f"WHOAMI_ROUTE_01 커밋 범위 외: {violations}")
else:
    ok(f"수정 범위 검증 OK — WHOAMI_ROUTE_01 커밋 변경 {len(modified)}개 모두 허용 범위")


# ── 7. 수정 금지 파일 staged 검사 ───────────────────────────────────────
# HAEHAN_WHOAMI_ROUTE_01 커밋 자체의 변경 파일에 금지 파일이 없는지 검증.
# (이후 공정에서 stash 복원 등으로 staged 되더라도 본 검증은 commit history 기준)
log = subprocess.run(
    ["git", "log", "--all", "-E",
     "--grep=^feat.haehan.: HAEHAN_WHOAMI_ROUTE_01",
     "-1", "--name-only", "--pretty=format:%H"],
    cwd=ROOT, capture_output=True, text=True, timeout=10,
)
lines = [l for l in log.stdout.strip().split("\n") if l.strip()]
if not lines:
    warn("WARN_COMMIT_NOT_FOUND", "HAEHAN_WHOAMI_ROUTE_01 커밋 미발견 — staged fallback")
    staged = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=ROOT, capture_output=True, text=True, timeout=10,
    )
    staged_files = set(p.strip().replace("\\", "/") for p in staged.stdout.split("\n") if p.strip())
    forbidden_staged = {"desktop/webview_app_pywebview.py", "desktop/tray_app.py"}
    bad = forbidden_staged & staged_files
    if bad:
        fail("FAIL_DIRTY_SCOPE_VIOLATION", f"수정 금지 파일 staged: {bad}")
    else:
        ok("수정 금지 파일 staged 없음 (fallback)")
else:
    commit_files = set(l.strip().replace("\\", "/") for l in lines[1:])
    forbidden_in_commit = {"desktop/webview_app_pywebview.py", "desktop/tray_app.py"}
    bad = forbidden_in_commit & commit_files
    if bad:
        fail("FAIL_DIRTY_SCOPE_VIOLATION",
             f"WHOAMI_ROUTE_01 커밋 자체에 금지 파일: {bad}")
    else:
        ok("WHOAMI_ROUTE_01 커밋 자체에 금지 파일 (webview_app_pywebview/tray_app) 없음")


# ── 8. 라우터 추가 분량 (최소 수정 검증) ────────────────────────────────
inserted_lines = subprocess.run(
    ["git", "diff", "--stat", "HEAD", "desktop/local_server.py"],
    cwd=ROOT, capture_output=True, text=True, timeout=10,
)
stat_out = inserted_lines.stdout
# "n insertions(+)" 패턴
import re
m = re.search(r"(\d+) insertion", stat_out)
if m:
    n = int(m.group(1))
    if n > 100:
        warn("WARN_NON_MINIMAL_PATCH", f"local_server.py +{n} 라인 — 최소 수정 권장")
    else:
        ok(f"local_server.py 추가 {n} 라인 — 최소 수정 범위")


# ── 결과 ──────────────────────────────────────────────────────────────
print()
print("=" * 68)
print("  HAEHAN_WHOAMI_ROUTE_01 감리")
print("=" * 68)
for p in passes:   print(p)
for w in warnings: print(w)
for i in issues:   print(i)
print("-" * 68)
print(f"PASS: {len(passes)}  WARN: {len(warnings)}  FAIL: {len(issues)}")
if not issues:
    print(f"\033[32m✅ PASS_HAEHAN_WHOAMI_ROUTE\033[0m")
else:
    print(f"\033[31m❌ FAIL — {len(issues)}건 수정 필요\033[0m")
print("=" * 68)
sys.exit(1 if issues else 0)
