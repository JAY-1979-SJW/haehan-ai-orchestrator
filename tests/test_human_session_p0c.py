"""R2d-2 P0c — 사람 승인 발급 API 와 프록시 증명(HMAC) 시험.

인증 방식 행렬, 증명 변조·재전송·시각 초과, 비밀 미설정 503, node 서명 ↔ 파이썬 검증 교차 시험,
MCP 레지스트리에 발급 경로가 없음, 발급 함수 호출처 계약, `/auth/me` 계약 불변을 고정한다.
"""

from __future__ import annotations

import ast
import base64
import json
import shutil
import subprocess
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_orchestrator import config
from ai_orchestrator.gates import auth, human_session
from ai_orchestrator.gates import human_approval as ha
from ai_orchestrator.routers.human_approval_router import human_approval_router

ROOT = Path(__file__).resolve().parents[1]
SECRET = "unit-test-secret-" + "x" * 24
CONTENT = {"title": "제목", "body": "본문"}
USERS = {
    "tok-owner": {"email": "o@x.com", "role": "owner"},
    "tok-admin": {"email": "a@x.com", "role": "admin"},
    "tok-op": {"email": "op@x.com", "role": "operator"},
    "tok-view": {"email": "v@x.com", "role": "viewer"},
}


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("HUMAN_APPROVAL_DB", str(tmp_path / "ha.db"))
    monkeypatch.setenv(human_session.SECRET_ENV, SECRET)
    monkeypatch.setattr(config, "AUTH_ENABLED", True)
    monkeypatch.setattr(auth, "_bearer_resolver", lambda tok: USERS.get(tok))
    monkeypatch.setattr(auth, "_load_users", lambda: {"svc": {"enabled": True, "role": "admin", "password_hash": "pw"}})
    human_session._seen.clear()


@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(human_approval_router)
    return TestClient(app)


_counter = iter(range(10**9))


def _nonce() -> str:
    return f"testnonce{next(_counter):012d}"


def _proof(
    method="POST", path="/approvals/x/approve", body=b"", bearer="tok-owner", secret=SECRET, now=None, nonce=None
):
    ts = str(int(now if now is not None else time.time()))
    nonce = nonce or _nonce()
    return f"{ts}.{nonce}.{human_session.sign(secret, method, path, ts, nonce, body, bearer)}"


def _pending(client) -> str:
    r = client.post(
        "/approvals/requests",
        json={"op": "blog_publish", "target": "b1", "content": CONTENT},
        headers={"Authorization": "Bearer tok-op"},
    )
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _issue(client, rid, action="approve", bearer="tok-owner", body=b"", proof=True, **proof_kw):
    path = f"/approvals/{rid}/{action}"
    headers = {"Authorization": f"Bearer {bearer}"} if bearer else {}
    if proof:
        headers[human_session.HEADER] = _proof(path=path, body=body, bearer=bearer or "", **proof_kw)
    return client.post(path, content=body, headers={**headers, "content-type": "application/json"})


def _pending_no_auth(client, monkeypatch) -> str:
    monkeypatch.setattr(config, "AUTH_ENABLED", False)
    r = client.post("/approvals/requests", json={"op": "blog_publish", "target": "b1", "content": CONTENT})
    assert r.status_code == 200
    return r.json()["id"]


# ── 제안·조회 ──


def test_propose_needs_login_and_never_approves(client):
    assert client.post("/approvals/requests", json={"op": "o", "target": "t", "content": 1}).status_code == 401
    rid = _pending(client)
    assert ha.get_request(rid)["status"] == "pending"
    with pytest.raises(ha.ApprovalNotFound):
        ha.consume_approval("blog_publish", "b1", CONTENT)


def test_viewer_cannot_propose(client):
    r = client.post(
        "/approvals/requests",
        json={"op": "o", "target": "t", "content": 1},
        headers={"Authorization": "Bearer tok-view"},
    )
    assert r.status_code == 403


def test_pending_and_detail_show_snapshot(client):
    rid = _pending(client)
    h = {"Authorization": "Bearer tok-op"}
    assert [i["id"] for i in client.get("/approvals/pending", headers=h).json()["items"]] == [rid]
    assert client.get(f"/approvals/{rid}", headers=h).json()["content_snapshot"] == CONTENT
    assert client.get("/approvals/nope", headers=h).status_code == 404


# ── 인증 방식 행렬 ──


@pytest.mark.parametrize("bearer,code", [("tok-owner", 200), ("tok-admin", 200), ("tok-op", 403), ("tok-view", 403)])
def test_jwt_role_matrix_for_issuing(client, bearer, code):
    rid = _pending(client)
    r = _issue(client, rid, bearer=bearer)
    assert r.status_code == code, r.text
    if code == 200:
        assert r.json()["approved_via"] == "jwt"
        assert r.json()["approved_by"] in {"o@x.com", "a@x.com"}


def test_unauthenticated_is_401(client):
    rid = _pending(client)
    assert _issue(client, rid, bearer=None, proof=False).status_code == 401


def test_basic_credentials_cannot_issue_even_with_a_valid_proof(client):
    rid = _pending(client)
    path = f"/approvals/{rid}/approve"
    basic = "Basic " + base64.b64encode(b"svc:pw").decode()
    # 같은 비밀로 서명했더라도(최악: 비밀이 샌 경우) Basic 은 발급할 수 없다
    r = client.post(
        path, content=b"", headers={"Authorization": basic, human_session.HEADER: _proof(path=path, bearer=basic)}
    )
    assert r.status_code == 403
    assert ha.get_request(rid)["status"] == "pending"


def test_auth_disabled_standalone_can_issue_with_proof(client, monkeypatch):
    rid = _pending_no_auth(client, monkeypatch)
    path = f"/approvals/{rid}/approve"
    r = client.post(path, content=b"", headers={human_session.HEADER: _proof(path=path, bearer="")})
    assert r.status_code == 200
    assert r.json()["approved_by"] == human_session.LOCAL_ACTOR


def test_auth_disabled_still_needs_proof(client, monkeypatch):
    rid = _pending_no_auth(client, monkeypatch)
    assert client.post(f"/approvals/{rid}/approve", content=b"").status_code == 403


# ── 증명 검증 ──


def test_missing_proof_is_403_and_leaks_nothing(client):
    rid = _pending(client)
    r = _issue(client, rid, proof=False)
    assert r.status_code == 403
    assert SECRET not in r.text
    assert ha.get_request(rid)["status"] == "pending"


@pytest.mark.parametrize("mutate", ["secret", "path", "body", "bearer", "method", "garbage"])
def test_tampered_proof_is_403(client, mutate):
    rid = _pending(client)
    path = f"/approvals/{rid}/approve"
    kw: dict = {"secret": SECRET, "path": path, "body": b"", "bearer": "tok-owner"}
    if mutate == "secret":
        kw["secret"] = "other-secret"
    elif mutate == "path":
        kw["path"] = f"/approvals/{rid}/reject"
    elif mutate == "body":
        kw["body"] = b'{"ttl_seconds": 99999}'
    elif mutate == "bearer":
        kw["bearer"] = "tok-admin"
    elif mutate == "method":
        kw["method"] = "PUT"
    header = "garbage" if mutate == "garbage" else _proof(**kw)
    r = client.post(path, content=b"", headers={"Authorization": "Bearer tok-owner", human_session.HEADER: header})
    assert r.status_code == 403
    assert ha.get_request(rid)["status"] == "pending"


def test_body_swap_after_signing_is_rejected(client):
    rid = _pending(client)
    path = f"/approvals/{rid}/approve"
    header = _proof(path=path, body=b'{"ttl_seconds": 60}')
    r = client.post(
        path,
        content=b'{"ttl_seconds": 604800}',
        headers={"Authorization": "Bearer tok-owner", human_session.HEADER: header, "content-type": "application/json"},
    )
    assert r.status_code == 403


def test_stale_and_future_timestamps_are_rejected(client):
    now = time.time()
    for skew in (-(human_session.MAX_SKEW_S + 5), human_session.MAX_SKEW_S + 5):
        rid = _pending(client)
        assert _issue(client, rid, now=now + skew).status_code == 403
    rid = _pending(client)
    assert _issue(client, rid, now=now - (human_session.MAX_SKEW_S - 10)).status_code == 200


def test_replayed_nonce_is_rejected(client):
    r1, r2 = _pending(client), _pending(client)
    ts = int(time.time())
    p1 = _proof(path=f"/approvals/{r1}/approve", now=ts, nonce="replaynonce000001")
    h = {"Authorization": "Bearer tok-owner", human_session.HEADER: p1}
    assert client.post(f"/approvals/{r1}/approve", content=b"", headers=h).status_code == 200
    # 같은 증명을 다시 보내면 상태 전이(409)에 닿기 전에 증명 단계에서 먼저 막힌다
    assert client.post(f"/approvals/{r1}/approve", content=b"", headers=h).status_code == 403
    # 같은 nonce 로 다른 요청을 서명해도 이미 쓴 nonce 라 거부
    p2 = _proof(path=f"/approvals/{r2}/approve", now=ts, nonce="replaynonce000001")
    h2 = {"Authorization": "Bearer tok-owner", human_session.HEADER: p2}
    assert client.post(f"/approvals/{r2}/approve", content=b"", headers=h2).status_code == 403


def test_forged_signature_does_not_burn_the_nonce():
    ts = str(int(time.time()))
    nonce = "burnattempt00001"
    kw = {"method": "POST", "path": "/p", "body": b"", "bearer": "b", "secret": SECRET}
    assert not human_session.verify_proof(f"{ts}.{nonce}.{'0' * 64}", **kw)
    good = f"{ts}.{nonce}.{human_session.sign(SECRET, 'POST', '/p', ts, nonce, b'', 'b')}"
    assert human_session.verify_proof(good, **kw)


def test_missing_secret_fails_closed_with_503(client, monkeypatch):
    rid = _pending(client)
    monkeypatch.delenv(human_session.SECRET_ENV)
    r = _issue(client, rid)
    assert r.status_code == 503
    assert ha.get_request(rid)["status"] == "pending"
    # 제안·조회는 계속 열려 있다
    assert client.get("/approvals/pending", headers={"Authorization": "Bearer tok-op"}).status_code == 200


def test_reject_and_revoke_need_the_same_proof(client):
    r1, r2 = _pending(client), _pending(client)
    assert _issue(client, r1, "reject", proof=False).status_code == 403
    assert _issue(client, r1, "reject").status_code == 200
    assert _issue(client, r2).status_code == 200
    assert _issue(client, r2, "revoke", proof=False).status_code == 403
    assert _issue(client, r2, "revoke").status_code == 200
    with pytest.raises(ha.ApprovalNotFound):
        ha.consume_approval("blog_publish", "b1", CONTENT)


def test_state_conflicts_are_409(client):
    rid = _pending(client)
    assert _issue(client, rid).status_code == 200
    assert _issue(client, rid).status_code == 409


# ── 교차 언어: node 서명 ↔ 파이썬 검증 ──


@pytest.mark.skipif(shutil.which("node") is None, reason="node 필요")
def test_node_signature_matches_python():
    ts = int(time.time())
    uri = (ROOT / "admin-web/src/lib/approvalProxy.ts").as_uri()
    path = "/api/v1/approvals/ha_abc/approve"
    script = (
        f"import {{signApproval, canonical}} from '{uri}';"
        "const body = new TextEncoder().encode(JSON.stringify({ttl_seconds: 900, memo: '한글'}));"
        f"const sig = signApproval({{secret: '{SECRET}', method: 'post', path: '{path}', body, bearer: 'tok.한글', "
        f"nowSeconds: {ts}, nonce: 'crosslang00000001'}});"
        f"console.log(JSON.stringify({{sig, canon: canonical('POST', '{path}', '1', 'n', body, 'b')}}));"
    )
    out = subprocess.run(
        ["node", "--input-type=module", "-e", script], capture_output=True, text=True, encoding="utf-8", timeout=60
    )
    assert out.returncode == 0, out.stderr
    got = json.loads(out.stdout.strip().splitlines()[-1])
    body = json.dumps({"ttl_seconds": 900, "memo": "한글"}, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    want = human_session.sign(SECRET, "POST", path, str(ts), "crosslang00000001", body, "tok.한글")
    assert got["sig"] == f"{ts}.crosslang00000001.{want}"
    assert got["canon"] == human_session.canonical("POST", path, "1", "n", body, "b")
    assert human_session.verify_proof(got["sig"], method="POST", path=path, body=body, bearer="tok.한글", secret=SECRET)


# ── 계약 ──


def test_issue_endpoints_are_not_in_mcp_registry():
    from ai_orchestrator import mcp_server

    text = json.dumps(mcp_server.API_REGISTRY, ensure_ascii=False)
    assert "/approvals" not in text
    assert "human_approval" not in text


def _callers(attr_names: set[str], receivers: set[str]) -> set[str]:
    found: set[str] = set()
    for base in ("ai_orchestrator", "scripts", "apps"):
        for p in (ROOT / base).rglob("*.py"):
            if "__pycache__" in p.parts:
                continue
            try:
                tree = ast.parse(p.read_text(encoding="utf-8"))
            except SyntaxError, UnicodeDecodeError:
                continue
            for n in ast.walk(tree):
                if (
                    isinstance(n, ast.Call)
                    and isinstance(n.func, ast.Attribute)
                    and n.func.attr in attr_names
                    and getattr(n.func.value, "id", "") in receivers
                ):
                    found.add(p.relative_to(ROOT).as_posix())
    return found


def test_human_approve_has_a_single_caller():
    assert _callers({"approve"}, {"ha", "human_approval"}) == {"ai_orchestrator/routers/human_approval_router.py"}
    assert _callers({"approve_cas"}, {"store", "human_approval_store"}) == {"ai_orchestrator/gates/human_approval.py"}


def test_auth_py_is_untouched_by_p0c():
    src = (ROOT / "ai_orchestrator/gates/auth.py").read_text(encoding="utf-8")
    assert "approved_via" not in src
    assert "human_session" not in src
    assert "APPROVAL_PROXY" not in src


def test_proxy_route_ignores_client_authorization_and_basic_for_issue_paths():
    text = (ROOT / "admin-web/src/app/api/proxy/[...path]/route.ts").read_text(encoding="utf-8")
    start = text.index("function buildApprovalHeaders")
    fn = text[start : text.index("async function proxy")]
    assert "API_PASS" not in fn
    assert "req.headers" not in fn  # 클라이언트 Authorization 을 읽지 않는다
    assert "buildUpstreamHeaders" not in fn
    assert "isApprovalIssuePath" in text
    assert "APPROVAL_PROXY_SECRET" in text
