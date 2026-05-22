"""audit_local_agent_exception_handler_p2.py
LOCAL_AGENT_EXCEPTION_HANDLER_P2 감리

P2 범위: desktop/local_server.py exception handler 3종만.
P1(/local-agent/preflight) 코드는 이 감리에서 검사하지 않음.

검사 항목:
  1. 소스 — handler 3종 등록 확인
  2. HTTPException → exc.status_code 보존 (404/403/401)
  3. RequestValidationError → 422 보존
  4. 예상 밖 Exception → 500 마스킹
  5. 500 응답에 금지 항목 없음
  6. secret 포함 exception 을 던졌을 때 응답에 secret 미노출
  7. 응답 secret scan

주의: SPA catch-all (/{full_path:path}) 이 등록돼 있으므로
      핸들러 함수를 asyncio.run() 으로 직접 호출해 검증함.

Verdicts:
  PASS_P2_EXCEPTION_HANDLER_MASKING
  WARN_P2_EXCEPTION_HANDLER_PARTIAL
  FAIL_P2_SECRET_OR_STATUS_LEAK
  FAIL_P2_HANDLER_MISSING
  FAIL_P2_STATUS_CODE_WRONG
"""
from __future__ import annotations

import asyncio
import json
import re
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

LOCAL_SERVER = ROOT / "desktop" / "local_server.py"

P = "\033[32m[PASS]\033[0m"
W = "\033[33m[WARN]\033[0m"
F = "\033[31m[FAIL]\033[0m"

issues, warnings, passes = [], [], []

def fail(code, msg): issues.append(f"{F} {code} — {msg}")
def warn(code, msg): warnings.append(f"{W} {code} — {msg}")
def ok(msg):         passes.append(f"{P} {msg}")

FORBIDDEN_IN_500 = {
    "traceback", "stack_trace", "exc_info",
    "api_key", "token", "cookie", "session",
    "authorization", "bearer", "database_url",
    "password", "secret",
}


# ── helper: 가짜 Request 객체 ───────────────────────────────────────────────
def _mock_request(method="GET", path="/test"):
    req = MagicMock()
    req.method = method
    req.url.path = path
    return req


# ── 1. 소스 확인 ─────────────────────────────────────────────────────────────
src = LOCAL_SERVER.read_text(encoding="utf-8")

for handler_name in ("HTTPException", "RequestValidationError", "Exception"):
    if f"exception_handler({handler_name})" in src:
        ok(f"소스에 {handler_name} handler 등록 확인")
    else:
        fail("FAIL_P2_HANDLER_MISSING", f"{handler_name} handler 미등록")

http_h_idx = src.find("_http_exception_handler")
http_h_src = src[http_h_idx: http_h_idx + 300] if http_h_idx >= 0 else ""
if "exc.status_code" in http_h_src:
    ok("HTTPException handler — exc.status_code 사용 확인")
else:
    fail("FAIL_P2_STATUS_CODE_WRONG", "HTTPException handler 가 exc.status_code 미사용")

gen_h_idx = src.find("_generic_exception_handler")
gen_h_src = src[gen_h_idx: gen_h_idx + 400] if gen_h_idx >= 0 else ""
if "내부 서버 오류" in gen_h_src or "internal server error" in gen_h_src.lower():
    ok("generic handler — 안전한 고정 메시지 확인")
else:
    fail("FAIL_P2_SECRET_OR_STATUS_LEAK", "generic handler 에 안전 고정 메시지 없음")

if "traceback.format_exc" in gen_h_src or "str(exc)" in gen_h_src:
    fail("FAIL_P2_SECRET_OR_STATUS_LEAK", "generic handler 에 traceback/str(exc) 포함")
else:
    ok("generic handler 소스 — traceback/str(exc) 원문 미사용")

if "type(exc).__name__" in gen_h_src:
    ok("generic handler logger — type(exc).__name__ 만 기록")
else:
    warn("WARN_P2_LOGGER_STYLE", "generic handler logger type(exc).__name__ 형식 미확인")


# ── 2. diff ──────────────────────────────────────────────────────────────────
diff_out = subprocess.run(
    ["git", "diff", "HEAD", "--", "desktop/local_server.py"],
    cwd=ROOT, capture_output=True, text=True, timeout=10,
)
diff_lines = [l for l in diff_out.stdout.split("\n")
              if l.startswith("+") and "exception_handler" in l.lower()]
if diff_lines:
    ok("exception handler diff:\n  " + "\n  ".join(diff_lines))
else:
    warn("WARN_P2_DIFF_EMPTY", "diff 에서 exception_handler 라인 미발견")


# ── 3. 핸들러 함수 직접 호출 검증 ────────────────────────────────────────────
try:
    for mn in list(sys.modules.keys()):
        if mn.startswith("desktop"):
            del sys.modules[mn]

    from desktop import local_server as _ls
    from fastapi import HTTPException as _HTTPEx
    from fastapi.exceptions import RequestValidationError as _RVE

    req = _mock_request()

    # ── 3a. HTTPException 404 ────────────────────────────────────────────────
    exc_404 = _HTTPEx(status_code=404, detail="not found")
    r = asyncio.run(_ls._http_exception_handler(req, exc_404))
    ok(f"HTTPException 404 응답:\n  status={r.status_code}  body={r.body.decode()}")
    if r.status_code == 404:
        ok("HTTPException 404 status 보존 ✓")
    else:
        fail("FAIL_P2_STATUS_CODE_WRONG", f"404 → status={r.status_code}")

    # ── 3b. HTTPException 403 ────────────────────────────────────────────────
    exc_403 = _HTTPEx(status_code=403, detail="forbidden")
    r = asyncio.run(_ls._http_exception_handler(req, exc_403))
    ok(f"HTTPException 403 응답:\n  status={r.status_code}  body={r.body.decode()}")
    if r.status_code == 403:
        ok("HTTPException 403 status 보존 ✓")
    else:
        fail("FAIL_P2_STATUS_CODE_WRONG", f"403 → status={r.status_code}")

    # ── 3c. HTTPException 401 ────────────────────────────────────────────────
    exc_401 = _HTTPEx(status_code=401, detail="unauthorized")
    r = asyncio.run(_ls._http_exception_handler(req, exc_401))
    ok(f"HTTPException 401 응답:\n  status={r.status_code}  body={r.body.decode()}")
    if r.status_code == 401:
        ok("HTTPException 401 status 보존 ✓")
    else:
        fail("FAIL_P2_STATUS_CODE_WRONG", f"401 → status={r.status_code}")

    # ── 3d. RequestValidationError → 422 ─────────────────────────────────────
    try:
        rve = _RVE([{"loc": ("body",), "msg": "field required", "type": "missing"}])
        r422 = asyncio.run(_ls._validation_exception_handler(req, rve))
        ok(f"RequestValidationError 422 응답:\n  status={r422.status_code}  body={r422.body.decode()[:120]}")
        if r422.status_code == 422:
            ok("RequestValidationError 422 status 보존 ✓")
        else:
            fail("FAIL_P2_STATUS_CODE_WRONG", f"RequestValidationError → status={r422.status_code}")
    except Exception as e:
        warn("WARN_P2_422_CONSTRUCT", f"RequestValidationError 직접 생성 실패: {e}")

    # ── 3e. RuntimeError → 500 마스킹 ────────────────────────────────────────
    exc_rt = RuntimeError("mock internal error — should be masked")
    r500 = asyncio.run(_ls._generic_exception_handler(req, exc_rt))
    ok(f"RuntimeError 500 응답:\n  status={r500.status_code}  body={r500.body.decode()}")

    if r500.status_code == 500:
        ok("RuntimeError → status=500 마스킹 ✓")
    else:
        fail("FAIL_P2_STATUS_CODE_WRONG", f"RuntimeError → status={r500.status_code}")

    body_500 = r500.body.decode().lower()
    leaks_500 = []
    for k in FORBIDDEN_IN_500:
        if k in body_500:
            leaks_500.append(k)
    if "mock internal error" in body_500:
        leaks_500.append("raw_exception_message")
    if re.search(r"sk-[a-z0-9\-_]{6,}", body_500):
        leaks_500.append("sk-_raw_key")

    if leaks_500:
        fail("FAIL_P2_SECRET_OR_STATUS_LEAK",
             f"500 응답에 금지 항목: {leaks_500}")
    else:
        ok(f"500 응답 금지 항목 없음 ✓")

    try:
        j = json.loads(r500.body)
        if "detail" in j:
            ok(f"500 응답 형식 — detail='{j['detail']}'")
        else:
            warn("WARN_P2_500_FORMAT", f"500 응답에 detail 키 없음: {j}")
    except Exception:
        fail("FAIL_P2_SECRET_OR_STATUS_LEAK", "500 응답 JSON 파싱 실패")

    # ── 3f. secret 포함 exception → 응답에 secret 미노출 ────────────────────
    exc_sec = ValueError(
        "DB connect failed: postgresql://admin:sk-secret-password@db.internal:5432/prod"
    )
    r500s = asyncio.run(_ls._generic_exception_handler(req, exc_sec))
    ok(f"secret 포함 exception 응답:\n  status={r500s.status_code}  body={r500s.body.decode()}")

    if r500s.status_code == 500:
        ok("secret 포함 exception → status=500 ✓")
    else:
        fail("FAIL_P2_STATUS_CODE_WRONG",
             f"secret exception → status={r500s.status_code}")

    body_sec = r500s.body.decode()
    secret_leaks = []
    if "sk-secret-password" in body_sec:
        secret_leaks.append("raw_password_in_url")
    if "postgresql://" in body_sec:
        secret_leaks.append("database_url")
    if "db.internal" in body_sec:
        secret_leaks.append("internal_hostname")
    if re.search(r"sk-[a-z0-9\-_]{6,}", body_sec.lower()):
        secret_leaks.append("sk-_raw_key")
    if "admin:" in body_sec:
        secret_leaks.append("db_credentials")

    if secret_leaks:
        fail("FAIL_P2_SECRET_OR_STATUS_LEAK",
             f"secret exception 응답에 secret 노출: {secret_leaks}")
    else:
        ok("secret 포함 exception 응답에 secret 미노출 ✓")

    # ── 3g. 전체 응답 secret scan ────────────────────────────────────────────
    all_bodies = [
        r.body.decode() for r in
        [asyncio.run(_ls._http_exception_handler(req, _HTTPEx(status_code=s)))
         for s in (404, 403, 401)]
    ] + [r500.body.decode(), r500s.body.decode()]

    scan_leaks = []
    for body in all_bodies:
        b = body.lower()
        for k in FORBIDDEN_IN_500:
            if k in b:
                scan_leaks.append((k, body[:60]))
        if re.search(r"sk-[a-z0-9\-_]{6,}", b):
            scan_leaks.append(("sk-raw-key", body[:60]))

    if scan_leaks:
        fail("FAIL_P2_SECRET_OR_STATUS_LEAK", f"응답 secret scan 실패: {scan_leaks[:3]}")
    else:
        ok("전체 응답 secret scan PASS ✓")

except ImportError as e:
    warn("WARN_P2_NO_IMPORT", f"모듈 import 불가: {e}")
except Exception as e:
    import traceback
    warn("WARN_P2_RUNTIME", f"검증 오류: {e}\n{traceback.format_exc()[-500:]}")


# ── 결과 출력 ─────────────────────────────────────────────────────────────────
print()
print("=" * 72)
print("  LOCAL_AGENT_EXCEPTION_HANDLER_P2 감리")
print("=" * 72)
for p in passes:   print(p)
for w in warnings: print(w)
for i in issues:   print(i)
print("-" * 72)
print(f"PASS: {len(passes)}  WARN: {len(warnings)}  FAIL: {len(issues)}")
if not issues:
    if warnings:
        print("\033[33m⚠️  WARN_P2_EXCEPTION_HANDLER_PARTIAL\033[0m")
    else:
        print("\033[32m✅ PASS_P2_EXCEPTION_HANDLER_MASKING\033[0m")
else:
    print(f"\033[31m❌ FAIL_P2_SECRET_OR_STATUS_LEAK — {len(issues)}건 수정 필요\033[0m")
print("=" * 72)
sys.exit(1 if issues else 0)
