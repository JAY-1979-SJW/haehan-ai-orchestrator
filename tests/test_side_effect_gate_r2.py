"""R2 — 외부 발행·발송 승인·수신거부 장치(scripts.gate.require_side_effect) 와 블로그·하이웍스 연결 시험.

발송량(하루 상한)은 제한하지 않는다 — 시험도 '제한이 없음'을 고정한다.
"""

from __future__ import annotations

import pytest

from scripts import gate
from scripts.hiworks import mail_batch

OK = "OK_PHRASE"


@pytest.fixture(autouse=True)
def _gate_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("GATE_DATA_DIR", str(tmp_path / "gate"))


def test_approval_phrase_required():
    for bad in (None, "", "ok_phrase", "yes"):
        with pytest.raises(gate.GateBlocked):
            gate.require_side_effect("blog_publish", approval=bad, expected=OK)
    assert gate.require_side_effect("blog_publish", approval=OK, expected=OK).allowed


def test_no_count_limit_many_sends_pass():
    for _ in range(200):
        gate.require_side_effect("mail_send", approval=OK, expected=OK, recipient="x@y.z")


def test_opt_out_blocks_recipient_case_insensitive():
    gate.add_opt_out("Stop@Example.com")
    with pytest.raises(gate.GateBlocked, match="수신거부"):
        gate.require_side_effect("mail_send", approval=OK, expected=OK, recipient="stop@example.COM")
    gate.require_side_effect("mail_send", approval=OK, expected=OK, recipient="other@example.com")


def test_corrupt_opt_out_file_blocks_instead_of_passing(tmp_path):
    state = tmp_path / "gate"
    state.mkdir()
    (state / "opt_out.json").write_text("[broken", encoding="utf-8")
    with pytest.raises(gate.GateBlocked, match="읽을 수 없음"):
        gate.require_side_effect("mail_send", approval=OK, expected=OK, recipient="a@b.c")


def test_opt_out_file_written_atomically_no_tmp_left(tmp_path):
    gate.add_opt_out("a@b.c")
    gate.add_opt_out("c@d.e")
    assert sorted(p.name for p in (tmp_path / "gate").iterdir()) == ["opt_out.json"]
    assert gate.opt_out_list() == {"a@b.c", "c@d.e"}


# ── 하이웍스 배치 연결 ─────────────────────────────────────────────


def _patch_mail(monkeypatch, tmp_path, sent_to):
    monkeypatch.setattr(mail_batch, "DATA_DIR", tmp_path)
    monkeypatch.setattr(mail_batch, "LATEST_SEND_RESULT_PATH", tmp_path / "latest.json")
    monkeypatch.setattr(mail_batch, "SEND_RESULT_DIR", tmp_path / "results")
    monkeypatch.setattr(
        "scripts.hiworks.mail.fill_compose", lambda page, *, to, subject, body: sent_to.append(to) or {"ok": True}
    )
    monkeypatch.setattr("scripts.hiworks.mail.send_mail", lambda page: {"success": True})
    monkeypatch.setattr(mail_batch, "time", type("T", (), {"sleep": staticmethod(lambda _: None)})())


def _plan(n):
    return {
        "items": [
            {"index": i, "to": f"u{i}@t.com", "subject": f"S{i}", "body": "B", "delay_seconds": 0}
            for i in range(1, n + 1)
        ]
    }


def test_batch_without_approval_sends_nothing(tmp_path, monkeypatch):
    sent: list[str] = []
    _patch_mail(monkeypatch, tmp_path, sent)
    for bad in (None, "True", ""):
        with pytest.raises(gate.GateBlocked):
            mail_batch.execute_send_batch(_plan(2), page=object(), approval=bad)
    assert sent == []


def test_batch_skips_opt_out_and_has_no_count_cap(tmp_path, monkeypatch):
    sent: list[str] = []
    _patch_mail(monkeypatch, tmp_path, sent)
    gate.add_opt_out("u1@t.com")
    result = mail_batch.execute_send_batch(_plan(60), page=object(), approval=mail_batch.APPROVAL_CONFIRM_TEXT)
    assert "u1@t.com" not in sent
    assert len(sent) == 59  # 60통 중 수신거부 1통만 제외 — 건수 제한 없음
    assert result["sent"] == 59 and result["failed"] == 0 and result["skipped"] == 1
    assert result["items"][0]["skipped_reason"] == "수신거부 대상"


# ── 블로그 발행 연결 ───────────────────────────────────────────────


def test_blog_publish_requires_confirm_phrase_before_browser(monkeypatch):
    from fastapi import HTTPException

    from ai_orchestrator.connectors import naver_blog_router as r

    opened: list[int] = []
    monkeypatch.setattr(
        "scripts.web_connector.run_on_browser_thread", lambda fn, timeout=0: opened.append(1) or {"ok": True}
    )
    for bad in (None, "", "yes"):
        req = r.BlogWriteRequest(title="t", body="b", publish=True, publish_confirm=bad)
        with pytest.raises(HTTPException) as exc:
            r.write_to_naver(req, user={})
        assert exc.value.status_code == 403
    assert opened == []  # 브라우저를 열기 전에 차단


def test_blog_publish_passes_with_phrase_and_draft_needs_none(monkeypatch):
    from ai_orchestrator.connectors import naver_blog_router as r

    monkeypatch.setattr(r, "emit_event", lambda *a, **k: None)
    monkeypatch.setattr("scripts.web_connector.run_on_browser_thread", lambda fn, timeout=0: {"ok": True})
    ok = r.write_to_naver(
        r.BlogWriteRequest(title="t", body="b", publish=True, publish_confirm=r.BLOG_PUBLISH_CONFIRM_TEXT), user={}
    )
    assert ok["ok"] is True and ok["publish"] is True
    draft = r.write_to_naver(r.BlogWriteRequest(title="t", body="b", publish=False), user={})
    assert draft["ok"] is True and draft["publish"] is False


# ── 수신거부 동시 추가(프로세스 간) ──────────────────────────────────


def _add_many(state_dir: str, prefix: str, n: int) -> None:
    import os

    os.environ["GATE_DATA_DIR"] = state_dir
    from scripts import gate as g

    for i in range(n):
        g.add_opt_out(f"{prefix}{i}@t.com")


def test_two_processes_adding_opt_out_concurrently_keep_all(tmp_path):
    import multiprocessing as mp

    state = str(tmp_path / "gate")
    ctx = mp.get_context("spawn")
    procs = [ctx.Process(target=_add_many, args=(state, p, 25)) for p in ("a", "b", "c")]
    [p.start() for p in procs]
    [p.join(120) for p in procs]
    assert all(p.exitcode == 0 for p in procs)
    got = gate.opt_out_list()
    expected = {f"{p}{i}@t.com" for p in ("a", "b", "c") for i in range(25)}
    assert got == expected  # 75건 모두 남아야 한다 — 하나라도 사라지면 수신거부 누락
    assert not (tmp_path / "gate" / "opt_out.lock").exists()


def test_stale_lock_file_is_cleared(tmp_path):
    import os
    import time

    state = tmp_path / "gate"
    state.mkdir()
    lock = state / "opt_out.lock"
    lock.write_text("", encoding="utf-8")
    old = time.time() - 120
    os.utime(lock, (old, old))
    gate.add_opt_out("z@t.com")
    assert gate.is_opted_out("z@t.com") if hasattr(gate, "is_opted_out") else "z@t.com" in gate.opt_out_list()
