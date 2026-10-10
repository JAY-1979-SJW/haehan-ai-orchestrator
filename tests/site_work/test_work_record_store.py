"""ai_orchestrator.site_work.work_record_store (L7) — tmp_path 임시 DB·합성 데이터만. 실제 data/·storage/ 접촉 없음."""

from __future__ import annotations

import hashlib
import sqlite3
import threading

import pytest

from ai_orchestrator.site_work.work_record import (
    ArtifactSpec,
    InvalidTransitionError,
    JobDraft,
    JobPatch,
    JobQuery,
    JobStatus,
    NotFoundError,
    Scope,
    StepDraft,
    StepStatus,
    StepUpdate,
    ValidationError,
)
from ai_orchestrator.site_work import work_record_store as wrs
from ai_orchestrator.persistence.sqlite_schema import SchemaTooNewError

J = JobStatus
OWNER = Scope.owner_only("alice")
WIDE = Scope.tenant_wide()


@pytest.fixture
def store(tmp_path):
    (tmp_path / "data" / "work_records").mkdir(parents=True)
    (tmp_path / "data" / "site_task_map").mkdir(parents=True)
    return wrs.WorkRecordStore(tmp_path / "wrs.db", base_dir=tmp_path)


def _list(store, scope, *, limit=30, offset=0, **kw):
    return store.list_jobs(scope, JobQuery(**kw), limit=limit, offset=offset)


def _job(store, **kw):
    base = {"kind": "manual", "title": "t", "actor": "alice"}
    base.update(kw)
    return store.create_job(JobDraft(**base))


def _file(tmp_path, rel="data/work_records/a.bin", data=b"hello"):
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return p


# ── 스키마 ────────────────────────────────────────────────────────────────
def test_schema_and_reopen_idempotent(tmp_path):
    db = tmp_path / "wrs.db"
    s1 = wrs.WorkRecordStore(db, base_dir=tmp_path)
    jid = _job(s1)
    s2 = wrs.WorkRecordStore(db, base_dir=tmp_path)
    assert s2.get_job(jid, OWNER) is not None
    con = sqlite3.connect(db)
    assert con.execute("PRAGMA user_version").fetchone()[0] == len(wrs._SCHEMA_STEPS) == 1
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"wrs_jobs", "wrs_steps", "wrs_artifacts", "wrs_events", "wrs_links", "wrs_job_tags"} <= tables
    idx = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    expected = {
        "idx_wrs_jobs_status", "idx_wrs_jobs_host", "idx_wrs_jobs_kind", "idx_wrs_jobs_rerun_of",
        "idx_wrs_jobs_input_hash", "idx_wrs_tags_tag",
    }  # fmt: skip
    assert expected <= idx
    con.close()


def test_schema_too_new(tmp_path):
    db = tmp_path / "wrs.db"
    con = sqlite3.connect(db)
    con.execute("PRAGMA user_version = 99")
    con.close()
    with pytest.raises(SchemaTooNewError):
        wrs.WorkRecordStore(db, base_dir=tmp_path).list_jobs(OWNER)


# ── job 생성·조회 ──────────────────────────────────────────────────────────
def test_create_get(store):
    jid = _job(store, title="제목", host="a.com", params={"host": "a.com", "mode": "x"}, tags=["x", "y"])
    job = store.get_job(jid, OWNER)
    assert job.status == J.DRAFT and job.tenant_id == "default" and job.created_by == "alice"
    assert job.tags == ("x", "y") and job.params["mode"] == "x" and job.version == 1
    assert len(job.input_hash) == 64
    assert [e.event for e in store.list_events(jid, OWNER)] == ["job_created"]


def test_version_increments_for_same_input(store):
    a = _job(store, params={"note": "n"})
    b = _job(store, params={"note": "n"})
    c = _job(store, params={"note": "other"})
    assert [store.get_job(i, OWNER).version for i in (a, b, c)] == [1, 2, 1]


def test_onboard_kind(store):
    jid = _job(store, kind="site.onboard:eum.cw.or.kr")
    assert store.get_job(jid, OWNER).host == "eum.cw.or.kr"
    with pytest.raises(ValidationError):
        _job(store, kind="site.onboard:a.com", host="b.com")
    with pytest.raises(ValidationError):
        _job(store, kind="site.onboard:Bad Host")
    with pytest.raises(ValidationError):
        _job(store, kind="unknown_kind")


def test_initial_status_restricted(store):
    assert store.get_job(_job(store, status=J.RUNNING), OWNER).status == J.RUNNING
    with pytest.raises(ValidationError):
        _job(store, status=J.SUCCEEDED)


@pytest.mark.parametrize(
    "kw",
    [
        {"params": {"unknown": 1}},
        {"params": {"password": "x"}},
        {"params": {"note": "x" * 600}},
        {"params": {"url": "https://a.com/?q=1"}},
        {"title": ""},
        {"title": "x" * 201},
        {"actor": "bad actor!"},
        {"tenant_id": "Bad Tenant"},
        {"host": "http://a.com"},
        {"retention_class": "forever"},
        {"tags": ["bad tag"]},
    ],
)
def test_create_rejects_bad_input(store, kw):
    with pytest.raises(ValidationError):
        _job(store, **kw)


# ── 상태 전이 ──────────────────────────────────────────────────────────────
_ALLOWED = {
    (J.DRAFT, J.PENDING_APPROVAL), (J.DRAFT, J.CANCELLED),
    (J.PENDING_APPROVAL, J.RUNNING), (J.PENDING_APPROVAL, J.CANCELLED), (J.PENDING_APPROVAL, J.EXPIRED),
    (J.RUNNING, J.SUCCEEDED), (J.RUNNING, J.FAILED), (J.RUNNING, J.PAUSED), (J.RUNNING, J.CANCELLED),
    (J.PAUSED, J.RESUMABLE), (J.PAUSED, J.CANCELLED),
    (J.RESUMABLE, J.RUNNING), (J.RESUMABLE, J.CANCELLED),
}  # fmt: skip

_PATH_TO = {  # 각 상태에 도달하는 경로
    J.DRAFT: [],
    J.PENDING_APPROVAL: [J.PENDING_APPROVAL],
    J.RUNNING: [J.PENDING_APPROVAL, J.RUNNING],
    J.PAUSED: [J.PENDING_APPROVAL, J.RUNNING, J.PAUSED],
    J.RESUMABLE: [J.PENDING_APPROVAL, J.RUNNING, J.PAUSED, J.RESUMABLE],
    J.SUCCEEDED: [J.PENDING_APPROVAL, J.RUNNING, J.SUCCEEDED],
    J.FAILED: [J.PENDING_APPROVAL, J.RUNNING, J.FAILED],
    J.CANCELLED: [J.CANCELLED],
    J.EXPIRED: [J.PENDING_APPROVAL, J.EXPIRED],
}


@pytest.mark.parametrize("src", list(J))
@pytest.mark.parametrize("dst", list(J))
def test_transition_matrix(store, src, dst):
    jid = _job(store)
    for step in _PATH_TO[src]:
        store.transition_job(jid, step, actor="alice")
    assert store.get_job(jid, OWNER).status == src
    if (src, dst) in _ALLOWED:
        store.transition_job(jid, dst, actor="alice", detail="ok")
        assert store.get_job(jid, OWNER).status == dst
    else:
        with pytest.raises(InvalidTransitionError):
            store.transition_job(jid, dst, actor="alice")
        assert store.get_job(jid, OWNER).status == src


def test_transition_records_event_and_unknown_job(store):
    jid = _job(store)
    store.transition_job(jid, J.PENDING_APPROVAL, actor="bob", detail="요청")
    ev = store.list_events(jid, OWNER)
    assert ev[-1].event == "status_changed" and ev[-1].actor == "bob" and "pending_approval" in (ev[-1].detail or "")
    assert store.get_job(jid, OWNER).updated_by == "bob"
    with pytest.raises(NotFoundError):
        store.transition_job("nope", J.CANCELLED, actor="alice")


def test_concurrent_transition_one_winner(tmp_path):
    (tmp_path / "data" / "work_records").mkdir(parents=True)
    s = wrs.WorkRecordStore(tmp_path / "wrs.db", base_dir=tmp_path)
    jid = _job(s, status=J.RUNNING)
    results: list[str] = []
    barrier = threading.Barrier(2)

    def go(target):
        barrier.wait()
        try:
            s.transition_job(jid, target, actor="alice")
            results.append("ok")
        except InvalidTransitionError:
            results.append("lost")

    ts = [threading.Thread(target=go, args=(t,)) for t in (J.SUCCEEDED, J.FAILED)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert sorted(results) == ["lost", "ok"]
    assert s.get_job(jid, OWNER).status in (J.SUCCEEDED, J.FAILED)
    assert sum(e.event == "status_changed" for e in s.list_events(jid, OWNER)) == 1


# ── step ──────────────────────────────────────────────────────────────────
def test_steps(store):
    jid = _job(store, status=J.RUNNING)
    s1 = store.add_step(jid, StepDraft(kind="explore", risk="read"))
    s2 = store.add_step(jid, StepDraft(kind="dry_run", risk="write", irreversible=True))
    assert (s1, s2) == (1, 2)
    with pytest.raises(ValidationError):
        store.add_step(jid, StepDraft(kind="explore", risk="read", seq=2))  # 중복 seq
    store.update_step(jid, 1, StepUpdate(status=StepStatus.RUNNING))
    store.update_step(jid, 1, StepUpdate(status=StepStatus.SUCCEEDED, output_summary="열 3개"))
    steps = store.list_steps(jid, OWNER)
    assert steps[0].status == StepStatus.SUCCEEDED and steps[0].started_at and steps[0].finished_at
    assert steps[0].output_summary == "열 3개" and steps[1].irreversible is True
    with pytest.raises(InvalidTransitionError):
        store.update_step(jid, 1, StepUpdate(status=StepStatus.RUNNING))
    store.update_step(jid, 2, StepUpdate(status=StepStatus.FAILED, error="boom"))
    store.update_step(jid, 2, StepUpdate(status=StepStatus.RUNNING))  # 재시도
    assert store.list_steps(jid, OWNER)[1].attempt == 2
    with pytest.raises(NotFoundError):
        store.update_step(jid, 9, StepUpdate(status=StepStatus.RUNNING))


@pytest.mark.parametrize(
    "draft",
    [
        StepDraft(kind="hack", risk="read"),
        StepDraft(kind="read", risk="bad"),
        StepDraft(kind="read", risk="read", input_summary="x" * 1001),
        StepDraft(kind="read", risk="read", error="x" * 501),
        StepDraft(kind="read", risk="read", output_summary="https://a.com/p?token=1"),
        StepDraft(kind="read", risk="read", seq=0),
    ],
)
def test_step_rejects_bad(store, draft):
    jid = _job(store)
    with pytest.raises(ValidationError):
        store.add_step(jid, draft)


def test_no_step_on_terminal_job(store):
    jid = _job(store)
    store.transition_job(jid, J.CANCELLED, actor="alice")
    with pytest.raises(InvalidTransitionError):
        store.add_step(jid, StepDraft(kind="read", risk="read"))


# ── artifact ──────────────────────────────────────────────────────────────
def test_artifact_attach_and_verify(store, tmp_path):
    jid = _job(store)
    p = _file(tmp_path, data=b"hello")
    aid = store.attach_artifact(jid, ArtifactSpec(kind="report", src_path=str(p), media_type="text/plain"))
    art = store.get_artifact(aid, OWNER)
    assert art.sha256 == hashlib.sha256(b"hello").hexdigest() and art.size_bytes == 5
    assert art.path == "data/work_records/a.bin" and art.sensitivity == "internal"
    assert store.verify_artifact(aid, OWNER) is True
    p.write_bytes(b"tampered")
    assert store.verify_artifact(aid, OWNER) is False
    p.unlink()
    assert store.verify_artifact(aid, OWNER) is False
    assert [a.artifact_id for a in store.list_artifacts(jid, OWNER)] == [aid]


def test_artifact_second_root_and_relative_src(store, tmp_path):
    jid = _job(store)
    p = _file(tmp_path, "data/site_task_map/_history/a.com/r1.json", b"{}")
    aid = store.attach_artifact(jid, ArtifactSpec(kind="site_map_snapshot", src_path=str(p)))
    assert store.get_artifact(aid, OWNER).path == "data/site_task_map/_history/a.com/r1.json"
    _file(tmp_path)
    aid2 = store.attach_artifact(jid, ArtifactSpec(kind="report", src_path="data/work_records/a.bin"))
    assert store.get_artifact(aid2, OWNER).path == "data/work_records/a.bin"


def test_artifact_path_rejections(store, tmp_path):
    jid = _job(store)
    outside = tmp_path / "other" / "x.bin"
    outside.parent.mkdir()
    outside.write_bytes(b"x")
    _file(tmp_path)
    for src in (
        str(outside),
        str(tmp_path / "data" / "work_records" / ".." / ".." / "other" / "x.bin"),
        "data/work_records/../../other/x.bin",
        "../x.bin",
        str(tmp_path / "data" / "work_records" / "missing.bin"),
        str(tmp_path / "data" / "work_records"),  # 디렉터리
    ):
        with pytest.raises(ValidationError):
            store.attach_artifact(jid, ArtifactSpec(kind="report", src_path=src))


def test_artifact_symlink_escape_rejected(store, tmp_path):
    jid = _job(store)
    target = tmp_path / "other.bin"
    target.write_bytes(b"x")
    link = tmp_path / "data" / "work_records" / "ln.bin"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlink 생성 불가 환경")
    with pytest.raises(ValidationError):
        store.attach_artifact(jid, ArtifactSpec(kind="report", src_path=str(link)))


def test_artifact_validation_and_size_cap(store, tmp_path, monkeypatch):
    jid = _job(store)
    p = _file(tmp_path)
    for spec in (
        ArtifactSpec(kind="exe", src_path=str(p)),
        ArtifactSpec(kind="report", src_path=str(p), sensitivity="secret"),
        ArtifactSpec(kind="report", src_path=str(p), media_type="bad type"),
        ArtifactSpec(kind="report", src_path=str(p), step_seq=5),  # 없는 step
    ):
        with pytest.raises((ValidationError, NotFoundError)):
            store.attach_artifact(jid, spec)
    monkeypatch.setattr(wrs, "ARTIFACT_MAX_BYTES", 3)
    with pytest.raises(ValidationError):
        store.attach_artifact(jid, ArtifactSpec(kind="report", src_path=str(p)))


# ── event append-only ─────────────────────────────────────────────────────
def test_events_append_only(store, tmp_path):
    jid = _job(store)
    eid = store.append_event(jid, event="note", actor="alice", detail="메모")
    assert eid > 0
    assert not any(hasattr(store, n) for n in ("update_event", "delete_event", "edit_event", "remove_event"))
    con = sqlite3.connect(tmp_path / "wrs.db")
    with pytest.raises(sqlite3.DatabaseError):
        con.execute("UPDATE wrs_events SET detail='x'")
    with pytest.raises(sqlite3.DatabaseError):
        con.execute("DELETE FROM wrs_events")
    con.close()
    with pytest.raises(ValidationError):
        store.append_event(jid, event="Bad Event", actor="alice")
    with pytest.raises(ValidationError):
        store.append_event(jid, event="note", actor="alice", detail="x" * 1001)
    with pytest.raises(NotFoundError):
        store.append_event("nope", event="note", actor="alice")
    assert [e.event for e in store.list_events(jid, OWNER)] == ["job_created", "note"]


# ── links / 계보 ──────────────────────────────────────────────────────────
def test_links_idempotent(store):
    jid = _job(store)
    store.add_link(jid, link_type="approval", ref_store="approval_record", ref_id="ap-1")
    store.add_link(jid, link_type="approval", ref_store="approval_record", ref_id="ap-1")
    store.add_link(jid, link_type="explore_request", ref_store="site_task_map_request", ref_id="r1")
    assert len(store.list_links(jid, OWNER)) == 2
    with pytest.raises(ValidationError):
        store.add_link(jid, link_type="weird", ref_store="x", ref_id="y")
    with pytest.raises(ValidationError):
        store.add_link(jid, link_type="audit", ref_store="x", ref_id="has space")


def test_lineage_links(store):
    parent = _job(store)
    re_ = _job(store, rerun_of=parent)
    res = _job(store, resumed_from=parent)
    fk = _job(store, forked_from=parent)
    assert store.get_job(re_, OWNER).rerun_of == parent
    assert store.get_job(res, OWNER).resumed_from == parent
    assert store.get_job(fk, OWNER).forked_from == parent
    assert {j.job_id for j in store.list_children(parent, OWNER, relation="rerun_of")} == {re_}
    assert {j.job_id for j in store.list_children(parent, OWNER, relation="resumed_from")} == {res}
    with pytest.raises(ValidationError):
        _job(store, rerun_of=parent, resumed_from=parent)  # 하나만
    with pytest.raises(NotFoundError):
        _job(store, rerun_of="nope")
    with pytest.raises(ValidationError):
        store.list_children(parent, OWNER, relation="bogus")


# ── 필터·페이징·범위 ───────────────────────────────────────────────────────
def test_filters_and_paging(store):
    ids = []
    for i in range(7):
        even = i % 2 == 0
        ids.append(_job(store, title=f"작업 {i}", host="a.com" if even else "b.com", tags=["even"] if even else []))
    store.transition_job(ids[0], J.PENDING_APPROVAL, actor="alice")
    store.patch_job(ids[1], JobPatch(starred=True), actor="alice")
    assert len(_list(store, OWNER).items) == 7
    p = _list(store, OWNER, limit=3, offset=0)
    p2 = _list(store, OWNER, limit=3, offset=3)
    assert p.total == 7 and len(p.items) == 3 and len(p2.items) == 3
    assert not ({j.job_id for j in p.items} & {j.job_id for j in p2.items})
    assert _list(store, OWNER, status="pending_approval").total == 1
    assert _list(store, OWNER, host="a.com").total == 4
    assert _list(store, OWNER, tag="even").total == 4
    assert _list(store, OWNER, starred=True).total == 1
    assert _list(store, OWNER, kind="manual").total == 7
    assert _list(store, OWNER, text="작업 3").total == 1
    assert _list(store, OWNER, created_from="2000-01-01").total == 7
    assert _list(store, OWNER, created_to="2000-01-01").total == 0
    assert _list(store, OWNER, limit=1000).limit == 100
    with pytest.raises(ValidationError):
        _list(store, OWNER, created_from="yesterday")


def test_kind_prefix_filter(store):
    _job(store, kind="site.onboard:a.com")
    _job(store, kind="site.onboard:b.com")
    _job(store)
    assert _list(store, OWNER, kind_prefix="site.onboard:").total == 2


def test_like_wildcards_escaped(store):
    _job(store, title="100% done")
    _job(store, title="other")
    assert _list(store, OWNER, text="%").total == 1
    assert _list(store, OWNER, text="_").total == 0


def test_tenant_and_owner_filters_default_on(store):
    mine = _job(store)
    other_owner = _job(store, actor="bob")
    other_tenant = _job(store, tenant_id="t2")
    assert {j.job_id for j in _list(store, OWNER).items} == {mine}
    assert {j.job_id for j in _list(store, WIDE).items} == {mine, other_owner}
    assert store.get_job(other_tenant, WIDE) is None
    assert store.get_job(other_owner, OWNER) is None
    assert store.get_job(other_tenant, Scope.tenant_wide("t2")) is not None
    assert [j.job_id for j in _list(store, Scope.owner_only("alice", "t2")).items] == [other_tenant]
    assert _list(store, Scope.owner_only("bob", "t2")).total == 0
    with pytest.raises(TypeError):
        store.list_jobs(query=None)  # 범위 없이 조회 불가


# ── patch / 소프트 삭제 ────────────────────────────────────────────────────
def test_patch_whitelist(store):
    jid = _job(store)
    store.patch_job(jid, JobPatch(title="새 제목", tags=["a", "b"], starred=True, archived=True), actor="alice")
    job = store.get_job(jid, OWNER)
    assert (job.title, job.tags, job.starred, job.archived) == ("새 제목", ("a", "b"), True, True)
    store.patch_job(jid, JobPatch(tags=["c"]), actor="alice")
    assert store.get_job(jid, OWNER).tags == ("c",) and _list(store, OWNER, tag="a").total == 0
    forbidden = {"status": "succeeded"}
    with pytest.raises(TypeError):
        store.patch_job(jid, JobPatch(**forbidden), actor="alice")
    with pytest.raises(ValidationError):
        store.patch_job(jid, JobPatch(title=""), actor="alice")


def test_soft_delete_keeps_events(store):
    jid = _job(store)
    store.transition_job(jid, J.CANCELLED, actor="alice")
    store.soft_delete_job(jid, actor="alice")
    assert store.get_job(jid, OWNER) is None
    assert store.get_job(jid, OWNER, include_deleted=True).deleted_at
    assert _list(store, OWNER).total == 0
    assert _list(store, OWNER, include_deleted=True).total == 1
    assert [e.event for e in store.list_events(jid, OWNER, include_deleted=True)][-1] == "job_deleted"
    with pytest.raises(NotFoundError):
        store.transition_job(jid, J.EXPIRED, actor="alice")
    with pytest.raises(NotFoundError):
        store.soft_delete_job(jid, actor="alice")


def test_cannot_soft_delete_running(store):
    jid = _job(store, status=J.RUNNING)
    with pytest.raises(InvalidTransitionError):
        store.soft_delete_job(jid, actor="alice")


def test_no_hard_delete_api(store):
    assert not any(n.startswith(("delete_", "purge_", "remove_")) for n in dir(store))


def test_params_verdict_robots_stored_and_rejected(store):
    jid = _job(store, params={"verdict": "use_api", "robots_status": "missing", "host": "a.com"})
    assert store.get_job(jid, OWNER).params == {"verdict": "use_api", "robots_status": "missing", "host": "a.com"}
    for bad in ({"verdict": "maybe"}, {"robots_status": 1}, {"verdict": ""}):
        with pytest.raises(ValidationError):
            _job(store, params=bad)
