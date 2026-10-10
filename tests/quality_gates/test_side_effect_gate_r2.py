"""R2 — 외부 발행·발송 승인·수신거부 장치(scripts.common.gate.require_side_effect) 와 블로그·하이웍스 연결 시험.

발송량(하루 상한)은 제한하지 않는다 — 시험도 '제한이 없음'을 고정한다.
"""

from __future__ import annotations

import pytest

from scripts.common import gate
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

    from ai_orchestrator.connectors.naver_blog import naver_blog_router as r

    opened: list[int] = []
    monkeypatch.setattr(
        "scripts.browser.cdp.connection.run_on_browser_thread", lambda fn, timeout=0: opened.append(1) or {"ok": True}
    )
    for bad in (None, "", "yes"):
        req = r.BlogWriteRequest(title="t", body="b", publish=True, publish_confirm=bad)
        with pytest.raises(HTTPException) as exc:
            r.write_to_naver(req, user={})
        assert exc.value.status_code == 403
    assert opened == []  # 브라우저를 열기 전에 차단


def test_blog_publish_passes_with_phrase_and_draft_needs_none(monkeypatch):
    from ai_orchestrator.connectors.naver_blog import naver_blog_router as r

    monkeypatch.setattr(r, "emit_event", lambda *a, **k: None)
    monkeypatch.setattr("scripts.browser.cdp.connection.run_on_browser_thread", lambda fn, timeout=0: {"ok": True})
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
    from scripts.common import gate as g

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


# ── R2b: Gmail /reply·/send, 하이웍스 CLI ─────────────────────────────


def _gmail(monkeypatch):
    from ai_orchestrator.connectors.google import gmail_router as g

    sent: list[dict] = []
    monkeypatch.setattr(g, "log_event", lambda *a, **k: None)
    monkeypatch.setattr(
        "ai_orchestrator.connectors.google.gmail_reader.send_reply", lambda **kw: sent.append(kw) or {"id": "m1"}
    )
    return g, sent


def _reply(g, **kw):
    base = {"thread_id": "t", "in_reply_to": "", "to": "Kim <kim@x.com>", "subject": "s", "body": "b", "dry_run": False}
    return g.api_reply(g.GmailReplyRequest(**{**base, **kw}), user={"actor": "a", "role": "admin"})


def test_gmail_reply_dry_run_sends_nothing(monkeypatch):
    g, sent = _gmail(monkeypatch)
    assert _reply(g, dry_run=True)["dry_run"] is True
    assert sent == []


def test_gmail_reply_without_phrase_is_403_and_sends_nothing(monkeypatch):
    from fastapi import HTTPException

    g, sent = _gmail(monkeypatch)
    for bad in (None, "", "yes", "gmail_approved_send"):
        with pytest.raises(HTTPException) as exc:
            _reply(g, send_confirm=bad)
        assert exc.value.status_code == 403
    assert sent == []


def test_gmail_reply_blocks_opt_out_even_with_display_name_and_case(monkeypatch):
    from fastapi import HTTPException

    g, sent = _gmail(monkeypatch)
    gate.add_opt_out("kim@x.com")
    with pytest.raises(HTTPException) as exc:
        _reply(g, to="Kim <KIM@x.com>, other@y.com", send_confirm=g.GMAIL_SEND_CONFIRM_TEXT)
    assert exc.value.status_code == 403 and "수신거부" in exc.value.detail
    assert sent == []


def test_gmail_reply_sends_with_phrase(monkeypatch):
    g, sent = _gmail(monkeypatch)
    out = _reply(g, send_confirm=g.GMAIL_SEND_CONFIRM_TEXT)
    assert out["ok"] is True and len(sent) == 1


def test_gmail_send_needs_confirmed_and_phrase_before_browser(monkeypatch):
    from fastapi import HTTPException

    g, _ = _gmail(monkeypatch)
    opened: list[int] = []
    monkeypatch.setattr("scripts.browser.cdp.connection.run_on_browser_thread", lambda fn, timeout=0: opened.append(1))
    user = {"actor": "a", "role": "admin"}
    with pytest.raises(HTTPException) as exc:
        g.api_send(g.GmailSendRequest(confirmed=True), user=user)
    assert exc.value.status_code == 403
    with pytest.raises(HTTPException) as exc:
        g.api_send(g.GmailSendRequest(confirmed=False, send_confirm=g.GMAIL_SEND_CONFIRM_TEXT), user=user)
    assert exc.value.status_code == 400
    assert opened == []


def test_hiworks_cli_submit_requires_typed_confirm(monkeypatch):
    from scripts.hiworks import router

    class Reached(Exception):
        pass

    monkeypatch.setattr(router, "open_hiworks", lambda *a, **k: (_ for _ in ()).throw(Reached()))
    monkeypatch.setattr(router, "work_run", lambda *a, **k: __import__("contextlib").nullcontext())
    monkeypatch.setattr(router, "load_action_catalog", dict)
    monkeypatch.setattr(router, "build_submit_execution_plan", lambda *a, **k: {})
    monkeypatch.setattr(router, "selected_targets", lambda s: {s: {"url": "u"}})
    # --approved 없이는 게이트에서 막힌다(force 불리언으로 통과하지 않는다)
    with pytest.raises(gate.GateBlocked):
        router._cmd_submit_section("svc", ["cid"])
    # --approved 가 있어도 문구가 다르면 SystemExit
    with pytest.raises(SystemExit):
        router._cmd_submit_section("svc", ["cid", "--approved", "--confirm=nope"])
    # 올바른 문구면 게이트를 지나 다음 단계(브라우저 열기)에 도달한다
    with pytest.raises(Reached):
        router._cmd_submit_section("svc", ["cid", "--approved", "--confirm=HIWORKS_APPROVED_SUBMIT"])


def test_hiworks_cli_send_batch_gate_uses_typed_confirm(monkeypatch):
    from scripts.hiworks import router

    seen: list[dict] = []

    class Reached(Exception):
        pass

    def fake_require(**kw):
        seen.append(kw)
        raise Reached

    monkeypatch.setattr(router.gates, "require_send", fake_require)
    with pytest.raises(SystemExit):
        router._cmd_send_batch("go", ["--approved", "--confirm=wrong"])
    assert seen == []
    with pytest.raises(Reached):
        router._cmd_send_batch("go", ["--approved", f"--confirm={router.APPROVAL_CONFIRM_TEXT}"])
    assert seen[0]["approval"] == router.APPROVAL_CONFIRM_TEXT
    assert seen[0]["expected"] == router.APPROVAL_CONFIRM_TEXT


def test_multiple_recipients_any_opt_out_blocks():
    gate.add_opt_out("b@t.com")
    with pytest.raises(gate.GateBlocked, match="수신거부"):
        gate.require_side_effect("gmail_send", approval=OK, expected=OK, recipient=["a@t.com", "B@t.com"])
    gate.require_side_effect("gmail_send", approval=OK, expected=OK, recipient=["a@t.com", "c@t.com"])


# ── R2c: eum 대량 SMTP, eum /sales-mail/send, hiworks /mail/send ───────


def test_eum_batch_script_blocks_without_phrase_before_smtp(monkeypatch, tmp_path):
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "eum_batch_r2c", Path(__file__).resolve().parents[2] / "scripts" / "eum" / "send_mail_batch.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    targets = tmp_path / "t.json"
    targets.write_text('[{"업체명":"A","공사명":"X","이메일":"a@t.com","공사시작일":"2026-01-01"}]', encoding="utf-8")
    monkeypatch.setattr(mod, "TARGETS_FILE", targets)
    monkeypatch.setattr(mod, "LOG_FILE", tmp_path / "log.json")
    connected: list[int] = []
    monkeypatch.setattr(mod, "connect_smtp", lambda: connected.append(1))

    for bad in (None, "", "yes"):
        with pytest.raises(gate.GateBlocked):
            mod.main(approval=bad)
    assert connected == []  # SMTP 접속 전에 차단
    mod.main(dry_run=True)  # 드라이런은 승인 불필요
    assert connected == []


def test_eum_batch_send_one_checks_phrase_and_opt_out(monkeypatch):
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "eum_batch_r2c2", Path(__file__).resolve().parents[2] / "scripts" / "eum" / "send_mail_batch.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "ACCOUNT", "me@x.com")
    monkeypatch.setattr(mod, "PASSWORD", "pw")

    class FakeServer:
        sent: list[str] = []

        def sendmail(self, frm, to, msg):
            self.sent.extend(to)

    srv = FakeServer()
    row = {"업체명": "A", "공사명": "X", "이메일": "a@t.com"}
    with pytest.raises(gate.GateBlocked):
        mod.send_one(srv, row)
    gate.add_opt_out("A@T.com")
    with pytest.raises(gate.GateBlocked, match="수신거부"):
        mod.send_one(srv, row, mod.CONFIRM_TEXT)
    assert srv.sent == []
    assert mod.send_one(srv, {**row, "이메일": "b@t.com"}, mod.CONFIRM_TEXT) is True
    assert srv.sent == ["b@t.com"]


def test_eum_batch_loop_records_gate_block_without_reconnect(tmp_path):
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "eum_batch_r2c3", Path(__file__).resolve().parents[2] / "scripts" / "eum" / "send_mail_batch.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    gate.add_opt_out("stop@t.com")
    reconnects: list[bool] = []

    def send_row(row):
        return mod.send_one(type("S", (), {"sendmail": lambda *a: None})(), row, mod.CONFIRM_TEXT)

    mod.ACCOUNT, mod.PASSWORD = "me@x.com", "pw"
    log = {"sent": [], "failed": []}
    mod.run_send_loop(
        [{"이메일": "stop@t.com", "업체명": "S"}, {"이메일": "ok@t.com", "업체명": "O"}],
        log,
        send_row,
        save=lambda _l: None,
        sleep=lambda _s: None,
        reconnect=lambda q: reconnects.append(q),
    )
    assert [e["email"] for e in log["sent"]] == ["ok@t.com"]
    assert "수신거부" in log["failed"][0]["reason"]
    assert reconnects == []


def test_eum_sales_mail_send_requires_phrase_and_checks_opt_out(monkeypatch):
    from fastapi import HTTPException

    from ai_orchestrator.connectors.eum import router as e

    opened: list[int] = []
    monkeypatch.setattr(e, "log_event", lambda *a, **k: None)
    monkeypatch.setattr("scripts.browser.cdp.connection.run_on_browser_thread", lambda fn, timeout=0: opened.append(1) or {"success": True})
    user = {"actor": "a", "role": "admin"}
    base = {"to": "Kim <kim@x.com>", "subject": "s", "body": "b", "confirmed": True}
    for bad in (None, "", "nope"):
        with pytest.raises(HTTPException) as exc:
            e.send_one(e.SendRequest(**base, send_confirm=bad), user=user)
        assert exc.value.status_code == 403
    gate.add_opt_out("kim@x.com")
    with pytest.raises(HTTPException) as exc:
        e.send_one(e.SendRequest(**base, send_confirm=e.EUM_SALES_MAIL_CONFIRM_TEXT), user=user)
    assert exc.value.status_code == 403 and "수신거부" in exc.value.detail
    assert opened == []
    with pytest.raises(HTTPException) as exc:  # confirmed=False 는 기존대로 400
        e.send_one(e.SendRequest(**{**base, "confirmed": False}, send_confirm=e.EUM_SALES_MAIL_CONFIRM_TEXT), user=user)
    assert exc.value.status_code == 400


def test_hiworks_mail_send_requires_phrase_before_browser(monkeypatch):
    from fastapi import HTTPException

    from ai_orchestrator.connectors.hiworks import mail_router as h

    opened: list[int] = []
    monkeypatch.setattr(h, "log_event", lambda *a, **k: None)
    monkeypatch.setattr("scripts.browser.cdp.connection.run_on_browser_thread", lambda fn, timeout=0: opened.append(1) or {"success": True})
    user = {"actor": "a", "role": "admin"}
    with pytest.raises(HTTPException) as exc:
        h.api_send(h.HWMailSendRequest(confirmed=True), user=user)
    assert exc.value.status_code == 403
    with pytest.raises(HTTPException) as exc:
        h.api_send(h.HWMailSendRequest(confirmed=False, send_confirm=h.HIWORKS_SEND_CONFIRM_TEXT), user=user)
    assert exc.value.status_code == 400
    assert opened == []
    h.api_send(h.HWMailSendRequest(confirmed=True, send_confirm=h.HIWORKS_SEND_CONFIRM_TEXT), user=user)
    assert opened == [1]


# ── R2d-1: 블로그 직접 호출·인스타·유튜브·스마트스토어·드라이브·하나팩스 단건 ─────────


def _all_phrases() -> set[str]:
    phrases = set(gate.CONFIRM_TEXTS.values())
    from ai_orchestrator.connectors.eum import router as eum_router
    from ai_orchestrator.connectors.google import gmail_router
    from ai_orchestrator.connectors.hiworks import mail_router as hiworks_mail_router
    from ai_orchestrator.connectors.naver_blog import naver_blog_router
    from scripts.hiworks import mail_batch

    phrases |= {
        naver_blog_router.BLOG_PUBLISH_CONFIRM_TEXT,
        gmail_router.GMAIL_SEND_CONFIRM_TEXT,
        eum_router.EUM_SALES_MAIL_CONFIRM_TEXT,
        hiworks_mail_router.HIWORKS_SEND_CONFIRM_TEXT,
        mail_batch.APPROVAL_CONFIRM_TEXT,
        "HIWORKS_APPROVED_SUBMIT",
        "EUM_APPROVED_MAIL_BATCH",
        "YOUTUBE_APPROVED_UPLOAD",
    }
    return phrases


def _assert_no_phrase(text: str) -> None:
    leaked = [p for p in _all_phrases() if p in text]
    assert not leaked, f"차단 응답에 승인 문구가 노출됨: {leaked}"


def _http_detail(fn):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        fn()
    assert exc.value.status_code in (400, 403)
    return str(exc.value.detail)


def test_blocked_http_responses_never_contain_approval_phrases(monkeypatch):
    """경로마다 '차단 응답 본문에 승인 문구 문자열이 없다'를 고정한다(R2d 정책)."""
    from ai_orchestrator.connectors.eum import router as e
    from ai_orchestrator.connectors.google import gmail_router as g
    from ai_orchestrator.connectors.hanafax import router as hf
    from ai_orchestrator.connectors.hiworks import mail_router as h
    from ai_orchestrator.connectors.naver_blog import naver_blog_router as b
    from ai_orchestrator.connectors.smartstore import reviews as rv

    for mod in (e, g, h):
        monkeypatch.setattr(mod, "log_event", lambda *a, **k: None)
    user = {"actor": "a", "role": "admin"}
    details = [
        _http_detail(lambda: b.write_to_naver(b.BlogWriteRequest(title="t", body="b", publish=True), user=user)),
        _http_detail(
            lambda: g.api_reply(
                g.GmailReplyRequest(thread_id="t", to="a@b.c", subject="s", body="b", dry_run=False), user=user
            )
        ),
        _http_detail(lambda: g.api_send(g.GmailSendRequest(confirmed=True), user=user)),
        _http_detail(
            lambda: e.send_one(e.SendRequest(to="a@b.c", subject="s", body="b", confirmed=True), user=user)
        ),
        _http_detail(lambda: h.api_send(h.HWMailSendRequest(confirmed=True), user=user)),
        _http_detail(lambda: rv.api_reviews_reply(rv.ReplyReviewsRequest(confirm=True, dry_run=False), user=user)),
        _http_detail(
            lambda: hf.send_fax(
                hf.SendRequest(receiver_fax="02-1234-5678", subject="s", body="b", confirmed=True), _=user
            )
        ),
    ]
    assert all("승인 문구" in d for d in details)
    for d in details:
        _assert_no_phrase(d)


def test_cli_error_messages_never_contain_approval_phrases():
    from scripts.hiworks import router as hr

    msgs: list[str] = []
    for call in (
        lambda: hr._cmd_submit_section("svc", ["cid", "--approved", "--confirm=nope"]),
        lambda: hr._cmd_submit_section("svc", []),
        lambda: hr._cmd_send_batch("go", ["--approved", "--confirm=nope"]),
        lambda: hr._cmd_send_batch("go", []),
    ):
        with pytest.raises(SystemExit) as exc:
            call()
        msgs.append(str(exc.value))
    for m in msgs:
        _assert_no_phrase(m)


def test_eum_batch_cli_error_message_has_no_phrase(tmp_path):
    import subprocess
    import sys
    from pathlib import Path

    script = Path(__file__).resolve().parents[2] / "scripts" / "eum" / "send_mail_batch.py"
    proc = subprocess.run(  # 승인 문구 없이 실제 발송 모드 — 대상이 없어도 게이트가 먼저 막는다
        [sys.executable, str(script), "--limit", "1"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(tmp_path),
        env={**__import__("os").environ, "GATE_DATA_DIR": str(tmp_path / "gate"), "HIWORKS_MAIL_ACCOUNT": "", "HIWORKS_MAIL_PASSWORD": ""},
        timeout=60,
        check=False,
    )
    out = proc.stdout + proc.stderr
    assert proc.returncode != 0
    _assert_no_phrase(out.replace("--confirm", ""))  # --help 문구가 아닌 오류 메시지에는 문구가 없어야 한다


# ── 블로그 직접 호출 ──


class _Boom:
    def __getattr__(self, name):
        raise AssertionError(f"승인 전에 외부 객체를 건드림: {name}")


def test_blog_inner_publish_paths_need_typed_approval():
    from scripts.naver.blog.core.ai_writer import BlogAIWriter
    from scripts.naver.blog.core.writer_pro import BlogWriterPro
    from scripts.naver.blog.management.schedule import BlogSchedule
    from scripts.naver.blog.marketing.publish import publish_one

    with pytest.raises(gate.GateBlocked):
        BlogSchedule(_Boom()).process_due()
    with pytest.raises(gate.GateBlocked):
        BlogAIWriter(_Boom()).draft_and_save("주제", publish=True)
    with pytest.raises(gate.GateBlocked):
        BlogWriterPro._publish_by_mode(_Boom(), False, None, approval="yes")
    with pytest.raises(gate.GateBlocked):
        publish_one(_Boom(), post={"title": "t", "body": "b", "tags": []}, img_paths=[])


def test_blog_pro_draft_and_schedule_modes_need_no_approval():
    from scripts.naver.blog.core.writer_pro import BlogWriterPro

    calls: list[str] = []

    class W:
        def save_draft(self):
            calls.append("draft")
            return {"ok": True}

        def schedule_publish(self, at):
            calls.append("schedule")
            return {"ok": True}

        def publish(self):
            calls.append("publish")
            return {"ok": True}

    pro = BlogWriterPro.__new__(BlogWriterPro)
    pro.writer = W()
    pro._publish_by_mode(True, None)
    pro._publish_by_mode(False, object())
    assert calls == ["draft", "schedule"]
    pro._publish_by_mode(False, None, approval=gate.CONFIRM_TEXTS["blog_publish"])
    assert calls[-1] == "publish"


@pytest.mark.parametrize("script", ["publish_ep_batch", "publish_ep_batch_gov2", "apply_cta_to_batches"])
def test_blog_batch_scripts_exit_before_browser_without_phrase(script, monkeypatch):
    import importlib

    mod = importlib.import_module(f"scripts.naver.blog.cli.{script}")
    monkeypatch.setattr("sys.argv", [script + ".py"])
    monkeypatch.setattr(mod, "get_page", lambda: (_ for _ in ()).throw(AssertionError("브라우저 접근")))
    with pytest.raises(SystemExit) as exc:
        mod.main()
    assert "발행 차단" in str(exc.value)
    _assert_no_phrase(str(exc.value))


def test_blog_ai_batch_20_blocks_before_any_work_without_phrase():
    import importlib
    import scripts.naver.blog.cli.blog_ai_batch_20 as mod
    with pytest.raises(gate.GateBlocked):
        mod.run(count=1, dry_run=False)


# ── 인스타그램 ──


def test_instagram_api_publish_requires_phrase_before_any_network(monkeypatch):
    from scripts.instagram import api_publish as ig

    touched: list[str] = []
    for name in ("create_reel_container", "create_carousel", "create_story_container", "wait_ready"):
        monkeypatch.setattr(ig, name, lambda *a, _n=name, **k: touched.append(_n) or "cid")
    monkeypatch.setattr(ig, "publish", lambda cid: touched.append("publish") or {"id": "p1"})
    for call in (
        lambda: ig.publish_reel("u", "c", confirmed=True),
        lambda: ig.publish_carousel(["a", "b"], "c", confirmed=True, approval="no"),
        lambda: ig.publish_story(image_url="u", confirmed=True),
    ):
        with pytest.raises(gate.GateBlocked):
            call()
    assert touched == []  # 컨테이너 생성 전에 막힌다
    assert ig.publish_reel("u", "c")["published"] is False  # confirmed=False(컨테이너만)는 승인 불필요
    touched.clear()
    ig.publish_reel("u", "c", confirmed=True, approval=gate.CONFIRM_TEXTS["instagram_publish"])
    assert "publish" in touched


def test_instagram_publish_case_blocks_before_browser(monkeypatch):
    from scripts.instagram import publish as ip

    monkeypatch.setattr(ip, "build_caption", lambda c: (_ for _ in ()).throw(AssertionError("승인 전 진행")))
    case = type("C", (), {"case_id": "c1", "images": []})()
    with pytest.raises(gate.GateBlocked):
        ip.publish_case(case, confirmed=True)


def test_instagram_dm_skips_opted_out_commenter_and_never_sends(monkeypatch):
    from types import SimpleNamespace

    from ai_orchestrator.connectors.instagram import instagram_dm_service as svc

    gate.add_opt_out("StopUser")
    updates: list[dict] = []
    fake_db = SimpleNamespace(
        get_account=lambda i: {"automation_enabled": 1, "instagram_user_id": "ig1"},
        list_comment_events=lambda i, limit=500: [
            {"id": "e1", "comment_text": "hi", "media_id": "m", "commenter_username": "stopuser", "comment_id": "c1"}
        ],
        list_rules=lambda i: [],
        update_comment_event_status=lambda *a, **k: None,
        try_reserve_reply_slot=lambda **k: ("log1", True),
        update_reply_result=lambda lid, **k: updates.append(k),
        set_account_status=lambda *a, **k: None,
    )
    rule = {"id": "r1", "enabled": 1, "reply_message": "x"}
    fake_engine = SimpleNamespace(
        evaluate=lambda **k: SimpleNamespace(matched=True, rule=rule, reason="", matched_keyword="k"),
        render_template=lambda t, **k: t,
    )
    monkeypatch.setattr(svc, "db", fake_db)
    monkeypatch.setattr(svc, "rule_engine", fake_engine)
    monkeypatch.setattr(svc, "_blocked_reason", lambda a, r: None)
    monkeypatch.setattr(svc, "send_private_reply", lambda *a, **k: (_ for _ in ()).throw(AssertionError("DM 발송됨")))
    svc.process_comment_event("e1", instagram_account_id="acc1")
    assert updates and updates[-1].get("blocked_reason") == "OPTED_OUT"


# ── 유튜브 ──


def test_youtube_execute_route_defaults_to_dry_run():
    from ai_orchestrator.connectors.youtube.upload import ExecuteRequest

    assert ExecuteRequest(plan_path="p", confirm="c").dry_run is True


def test_youtube_live_upload_passes_gate_only_with_phrase(tmp_path, monkeypatch):
    import json

    from scripts.youtube import uploader as u

    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps({"ready_for_approval": True}), encoding="utf-8")
    monkeypatch.setattr(u, "RESULT_DIR", tmp_path / "res")
    monkeypatch.setattr(u, "LATEST_RESULT", tmp_path / "latest.json")
    monkeypatch.setattr(u, "emit_event", lambda *a, **k: None)
    calls: list[int] = []
    monkeypatch.setattr(u, "_upload_with_official_api", lambda p: calls.append(1) or {"ok": True, "video_id": "v"})
    res, _ = u.execute_upload_plan(plan, approved=False, confirm="", dry_run=False)
    assert res["status"] == "blocked" and calls == []
    res, _ = u.execute_upload_plan(plan, approved=True, confirm=u.APPROVAL_PHRASE, dry_run=False)
    assert res["status"] == "ok" and calls == [1]


# ── 스마트스토어·드라이브·하나팩스 ──


def test_smartstore_submit_reply_blocks_before_touching_cdp():
    from scripts.naver.smartstore.inquiry_reply import submit_reply

    for bad in (None, "", "yes"):
        with pytest.raises(gate.GateBlocked):
            submit_reply(_Boom(), approval=bad)


def test_drive_share_link_blocks_before_touching_page():
    from scripts.google.drive_api import DriveAPI

    with pytest.raises(gate.GateBlocked):
        DriveAPI(_Boom()).share_link(0)


def test_hanafax_single_send_phrase_number_and_opt_out(monkeypatch):
    from fastapi import HTTPException

    from ai_orchestrator.connectors.hanafax import authorization_store as store
    from ai_orchestrator.connectors.hanafax import router as hf

    sent: list[str] = []
    monkeypatch.setattr(
        "scripts.hanafax.sender.send_fax",
        lambda receiver_fax, subject, body, receiver_name="": sent.append(receiver_fax)
        or {"success": True, "message": "ok"},
    )
    monkeypatch.setattr(store, "opt_out_numbers", lambda: {"0212345678"})
    user = {"actor": "a", "role": "admin"}
    phrase = gate.CONFIRM_TEXTS["hanafax_send"]

    def call(**kw):
        base = {"receiver_fax": "02-9999-8888", "subject": "s", "body": "b", "confirmed": True}
        return hf.send_fax(hf.SendRequest(**{**base, **kw}), _=user)

    with pytest.raises(HTTPException) as exc:
        call()
    assert exc.value.status_code == 403
    with pytest.raises(HTTPException) as exc:
        call(send_confirm=phrase, receiver_fax="abc")
    assert exc.value.status_code == 400
    with pytest.raises(HTTPException) as exc:
        call(send_confirm=phrase, receiver_fax="(02) 1234-5678")
    assert exc.value.status_code == 403 and "수신거부" in exc.value.detail
    assert sent == []
    assert call(send_confirm=phrase).ok is True
    assert sent == ["02-9999-8888"]


def test_hanafax_cli_single_send_needs_typed_phrase(monkeypatch):
    from scripts.hanafax import router as fr

    sent: list[str] = []
    monkeypatch.setattr(
        "scripts.hanafax.sender.send_fax",
        lambda receiver_fax, subject, body, **k: sent.append(receiver_fax) or {"success": True, "message": "ok"},
    )
    with pytest.raises(SystemExit) as exc:
        fr._cmd_send("02-1111-2222", ["제목"])
    _assert_no_phrase(str(exc.value))
    assert sent == []
    fr._cmd_send("02-1111-2222", ["제목", f"--confirm={gate.CONFIRM_TEXTS['hanafax_send']}"])
    assert sent == ["02-1111-2222"]


def test_is_opted_out_semantics(tmp_path):
    assert gate.is_opted_out("a@b.c") is False
    gate.add_opt_out("A@B.c")
    assert gate.is_opted_out("a@b.C") is True
    (tmp_path / "gate" / "opt_out.json").write_text("[broken", encoding="utf-8")
    assert gate.is_opted_out("zzz@b.c") is True  # 깨졌으면 보수적으로 차단


def test_blog_pro_smart_publish_passes_approval_through():
    """smart_publish 가 approval 인자를 받아 _publish_by_mode 까지 넘긴다(인자 누락 NameError 방지)."""
    import inspect

    from scripts.naver.blog.core.writer_pro import BlogWriterPro

    assert "approval" in inspect.signature(BlogWriterPro.smart_publish).parameters
    src = inspect.getsource(BlogWriterPro.smart_publish)
    assert "self._publish_by_mode(save_draft_only, schedule_at, approval)" in src
