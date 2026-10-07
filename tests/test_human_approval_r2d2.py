"""R2d-2 P0b — 사람 발급 1회용 승인 저장소(ai_orchestrator/gates/human_approval.py) 시험.

HTTP·인증 없이 저장·소진 로직만 검증한다. 발급 API(P0c)의 인증 보장은 P0c 시험이 맡는다.
"""

from __future__ import annotations

import ast
import multiprocessing as mp
import sqlite3
import threading
from pathlib import Path

import pytest

from ai_orchestrator.gates import gate_core
from ai_orchestrator.gates import human_approval as ha

ROOT = Path(__file__).resolve().parents[1]
CONTENT = {"title": "제목", "body": "본문", "tags": ["a", "b"], "to": ["B@x.com", "a@x.com"]}


@pytest.fixture(autouse=True)
def _db(tmp_path, monkeypatch):
    monkeypatch.setenv("HUMAN_APPROVAL_DB", str(tmp_path / "ha.db"))


def _approved(content=CONTENT, op="blog_publish", target="blog1", **kw):
    rid = ha.request_approval(op, target, content, requested_by="agent:mcp")
    ha.approve(rid, approved_by="owner@x.com", approved_via="jwt", **kw)
    return rid


# ── 해시 ──


def test_hash_ignores_recipient_order_case_and_whitespace_only():
    a = {"to": ["B@x.com", "a@x.com"], "subject": " 안녕 ", "body": "본문"}
    b = {"body": "본문", "subject": "안녕", "to": ["a@x.com", "b@X.com", "a@x.com"]}
    assert ha.content_hash(a) == ha.content_hash(b)
    assert ha.target_hash(["B@x.com", "a@x.com"]) == ha.target_hash(["a@x.com", "b@x.com"])


@pytest.mark.parametrize(
    "mutate",
    [
        lambda c: {**c, "body": c["body"] + "."},
        lambda c: {**c, "title": "다른 제목"},
        lambda c: {**c, "tags": ["a"]},
        lambda c: {**c, "to": [*c["to"], "c@x.com"]},
        lambda c: {**c, "extra": 1},
    ],
)
def test_any_content_change_changes_hash(mutate):
    assert ha.content_hash(mutate(CONTENT)) != ha.content_hash(CONTENT)


# ── 정상 흐름 ──


def test_request_approve_consume_once():
    rid = ha.request_approval("blog_publish", "blog1", CONTENT, requested_by="agent:mcp")
    assert ha.get_request(rid)["status"] == "pending"
    with pytest.raises(ha.ApprovalNotFound):  # 승인 전에는 소진 불가
        ha.consume_approval("blog_publish", "blog1", CONTENT)
    ha.approve(rid, approved_by="owner@x.com", approved_via="jwt")
    rec = ha.consume_approval("blog_publish", "blog1", CONTENT)
    assert rec["id"] == rid and rec["status"] == "used" and rec["approved_by"] == "owner@x.com"
    with pytest.raises(ha.ApprovalNotFound):  # 1회 — 두 번째는 실패
        ha.consume_approval("blog_publish", "blog1", CONTENT)


def test_snapshot_is_what_the_human_sees():
    rid = ha.request_approval("mail_send", ["a@x.com"], {"to": ["A@x.com"], "body": "hi"}, requested_by="u")
    snap = ha.get_request(rid)["content_snapshot"]
    assert snap == {"body": "hi", "to": ["a@x.com"]}
    assert len(ha.list_pending()) == 1


# ── 결속: 한 글자라도 다르면 실행 불가 ──


def test_changed_content_target_or_op_cannot_consume():
    _approved()
    with pytest.raises(ha.ApprovalNotFound):
        ha.consume_approval("blog_publish", "blog1", {**CONTENT, "body": "본문!"})
    with pytest.raises(ha.ApprovalNotFound):
        ha.consume_approval("blog_publish", "blog2", CONTENT)
    with pytest.raises(ha.ApprovalNotFound):
        ha.consume_approval("mail_send", "blog1", CONTENT)
    assert ha.consume_approval("blog_publish", "blog1", CONTENT)["status"] == "used"  # 정확히 같으면 통과


def test_expiry_blocks_consume_and_can_be_swept():
    rid = _approved(ttl_seconds=60, now=1000.0)
    with pytest.raises(ha.ApprovalNotFound):
        ha.consume_approval("blog_publish", "blog1", CONTENT, now=1060.0)  # 만료 시각 이상은 거부
    assert ha.expire_due(now=1061.0) == 1
    assert ha.get_request(rid)["status"] == "expired"


def test_reject_and_revoke_block_consume():
    r1 = ha.request_approval("blog_publish", "b", CONTENT, requested_by="u")
    ha.reject(r1, rejected_by="owner")
    with pytest.raises(ha.ApprovalError):
        ha.approve(r1, approved_by="owner", approved_via="jwt")  # 거부된 요청은 승인 불가
    r2 = _approved(target="b2")
    ha.revoke(r2, revoked_by="owner")
    with pytest.raises(ha.ApprovalNotFound):
        ha.consume_approval("blog_publish", "b2", CONTENT)


def test_used_approval_cannot_be_revoked_or_reapproved():
    rid = _approved()
    ha.consume_approval("blog_publish", "blog1", CONTENT)
    with pytest.raises(ha.ApprovalError):
        ha.revoke(rid, revoked_by="owner")
    with pytest.raises(ha.ApprovalError):
        ha.approve(rid, approved_by="owner", approved_via="jwt")


def test_max_uses_allows_that_many_consumptions():
    rid = ha.request_approval("mail_send", "t", CONTENT, requested_by="u", max_uses=3)
    ha.approve(rid, approved_by="owner", approved_via="jwt")
    for _ in range(3):
        ha.consume_approval("mail_send", "t", CONTENT)
    with pytest.raises(ha.ApprovalNotFound):
        ha.consume_approval("mail_send", "t", CONTENT)


# ── 발급 경로: 도구·서비스 경로 값은 승인으로 인정하지 않는다 ──


@pytest.mark.parametrize("via", ["basic", "mcp", "agent", "telegram", "disabled", "", "JWT"])
def test_approve_rejects_non_human_paths(via):
    rid = ha.request_approval("blog_publish", "b", CONTENT, requested_by="agent:mcp")
    with pytest.raises(ha.ApprovalError):
        ha.approve(rid, approved_by="owner", approved_via=via)
    assert ha.get_request(rid)["status"] == "pending"
    with pytest.raises(ha.ApprovalNotFound):
        ha.consume_approval("blog_publish", "b", CONTENT)


def test_requesting_never_grants_approval():
    """에이전트는 제안만 할 수 있다 — 제안 직후 소진은 실패해야 한다."""
    ha.request_approval("blog_publish", "b", CONTENT, requested_by="agent:mcp")
    with pytest.raises(ha.ApprovalNotFound):
        ha.consume_approval("blog_publish", "b", CONTENT)


def test_approve_requires_named_approver():
    rid = ha.request_approval("blog_publish", "b", CONTENT, requested_by="u")
    with pytest.raises(ha.ApprovalError):
        ha.approve(rid, approved_by="  ", approved_via="jwt")


# ── 예약에 묶인 승인 ──


def test_job_bound_approval_only_for_that_job_and_revoked_on_change():
    rid = ha.request_approval("scheduled:blog_publish", "job1", CONTENT, requested_by="u", schedule_job_id="job1")
    ha.approve(rid, approved_by="owner", approved_via="jwt+pin", ttl_seconds=3600)
    with pytest.raises(ha.ApprovalNotFound):  # 예약 없이는 소진 불가
        ha.consume_approval("scheduled:blog_publish", "job1", CONTENT)
    with pytest.raises(ha.ApprovalNotFound):  # 다른 예약도 불가
        ha.consume_approval("scheduled:blog_publish", "job1", CONTENT, schedule_job_id="job2")
    assert ha.revoke_for_job("job1", revoked_by="system") == 1  # 예약 수정 시 승인 철회
    with pytest.raises(ha.ApprovalNotFound):
        ha.consume_approval("scheduled:blog_publish", "job1", CONTENT, schedule_job_id="job1")


def test_unbound_approval_cannot_be_used_by_a_job():
    _approved(op="scheduled:blog_publish", target="job1")
    with pytest.raises(ha.ApprovalNotFound):
        ha.consume_approval("scheduled:blog_publish", "job1", CONTENT, schedule_job_id="job1")


# ── 경쟁 ──


def test_concurrent_threads_consume_exactly_once():
    _approved()
    wins: list[int] = []

    def work():
        try:
            ha.consume_approval("blog_publish", "blog1", CONTENT)
            wins.append(1)
        except ha.ApprovalNotFound:
            pass

    threads = [threading.Thread(target=work) for _ in range(16)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len(wins) == 1


def _proc_consume(db: str, q) -> None:
    import os

    os.environ["HUMAN_APPROVAL_DB"] = db
    from ai_orchestrator.gates import human_approval as h

    try:
        h.consume_approval("blog_publish", "blog1", CONTENT)
        q.put(1)
    except h.ApprovalNotFound:
        q.put(0)


def test_concurrent_processes_consume_exactly_once(tmp_path):
    _approved()
    ctx = mp.get_context("spawn")
    q = ctx.Queue()
    db = str(tmp_path / "ha.db")
    procs = [ctx.Process(target=_proc_consume, args=(db, q)) for _ in range(4)]
    [p.start() for p in procs]
    [p.join(120) for p in procs]
    assert all(p.exitcode == 0 for p in procs)
    results = [q.get(timeout=10) for _ in procs]
    assert sum(results) == 1


# ── 비노출 ──


def test_error_messages_and_public_records_do_not_leak_hash_or_id():
    rid = _approved()
    chash = ha.content_hash(CONTENT)
    with pytest.raises(ha.ApprovalNotFound) as exc:
        ha.consume_approval("blog_publish", "blog1", {**CONTENT, "body": "x"})
    text = str(exc.value) + repr(exc.value.result)
    assert chash not in text and rid not in text and chash[:8] not in text
    pub = ha.get_request(rid)
    assert "content_hash" not in pub and chash not in repr(pub)  # 공개 필드는 앞 8자만


def test_audit_events_are_emitted_without_content(monkeypatch):
    seen: list[tuple[str, dict]] = []
    monkeypatch.setattr(gate_core, "_audit_sink", lambda name, **f: seen.append((name, f)))
    rid = ha.request_approval("blog_publish", "b", {"body": "비밀 본문"}, requested_by="agent:mcp")
    ha.approve(rid, approved_by="owner", approved_via="jwt")
    ha.consume_approval("blog_publish", "b", {"body": "비밀 본문"})
    with pytest.raises(ha.ApprovalNotFound):
        ha.consume_approval("blog_publish", "b", {"body": "비밀 본문"})
    names = [n for n, _ in seen]
    assert names == ["approval.requested", "approval.approved", "approval.consumed", "approval.consume_denied"]
    assert "비밀 본문" not in repr(seen)


# ── 구조 ──


def test_module_does_not_import_scripts():
    tree = ast.parse((ROOT / "ai_orchestrator" / "gates" / "human_approval.py").read_text(encoding="utf-8"))
    mods = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    mods |= {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert mods
    assert not {m for m in mods if m == "scripts" or m.startswith("scripts.")}


def test_schema_version_and_wal(tmp_path):
    ha.request_approval("blog_publish", "b", CONTENT, requested_by="u")
    con = sqlite3.connect(str(tmp_path / "ha.db"))
    try:
        assert con.execute("PRAGMA user_version").fetchone()[0] == ha.SCHEMA_VERSION
        assert con.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    finally:
        con.close()


def test_only_issue_api_module_may_call_approve():
    """approve() 호출처는 이 모듈과 시험뿐이어야 한다(P0c 에서 발급 API 모듈 1곳이 추가됨). 에이전트 경로가 직접 부르는 코드를 막는 계약."""
    allowed_dirs = ("tests",)
    offenders: list[str] = []
    for base in ("ai_orchestrator", "scripts", "browser_api"):
        for path in (ROOT / base).rglob("*.py"):
            rel = path.relative_to(ROOT).as_posix()
            if rel == "ai_orchestrator/gates/human_approval.py" or rel.startswith(allowed_dirs) or "__pycache__" in rel:
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError, UnicodeDecodeError:
                continue
            for n in ast.walk(tree):
                if isinstance(n, ast.ImportFrom) and (n.module or "").endswith("human_approval"):
                    if any(a.name == "approve" for a in n.names):  # from ...human_approval import approve
                        offenders.append(rel)
                if isinstance(n, ast.Call):
                    f = n.func
                    name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
                    recv = ast.unparse(f.value) if isinstance(f, ast.Attribute) else ""
                    if name == "approve" and recv in {"human_approval", "ha"}:
                        offenders.append(rel)
    assert not offenders, f"human_approval.approve 를 직접 호출하는 코드: {offenders}"
