"""메일함 AI 업무 창 — 허용 API 고정, 초안 생성/보내기 업무 흐름, 중복 발송 방지, API.

가짜 발송기·가짜 메일함만 쓴다(실제 메일을 보내거나 읽지 않는다). 기준서: docs/specs/2026-10-02_mailbox_ai_window.md
"""

from __future__ import annotations

import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_orchestrator.connectors.naver_mail import draft_policy as pol
from ai_orchestrator.connectors.naver_mail import draft_store as store
from ai_orchestrator.connectors.naver_mail import drafts_workflow as drafts
from ai_orchestrator.connectors.naver_mail.mailbox_flow import ServiceError
from ai_orchestrator.connectors.naver_mail.mailbox_router import naver_mailbox_router
from ai_orchestrator.server.mcp_server import API_REGISTRY
from scripts.naver.mail.imap import sender
from tools.gates.auth import get_current_user

ME = "skyjwsin"


@pytest.fixture
def env(tmp_path, monkeypatch):
    """임시 DB + 임시 '문서' 폴더 + 가짜 발송기(보낸 Draft 를 모아 둔다)."""
    monkeypatch.setattr(store, "_DB_PATH", tmp_path / "drafts.db")
    docs = tmp_path / "home" / "Documents"
    docs.mkdir(parents=True)
    monkeypatch.setattr(pol, "allowed_attachment_dirs", lambda *a, **k: [docs])
    sent: list[sender.Draft] = []
    outcome = {"result": None}

    def fake_send(d, **_kw):
        sent.append(d)
        if isinstance(outcome["result"], Exception):
            raise outcome["result"]
        return outcome["result"] or {
            "ok": True,
            "recipients": d.all_recipients,
            "refused": [],
            "attachments": [u.filename for u in d.uploads],
        }

    monkeypatch.setattr(sender, "send_draft", fake_send)
    return type("Env", (), {"docs": docs, "sent": sent, "outcome": outcome})()


def _mk(env, **over):
    base = {"to": "a@example.com", "subject": "견적 회신", "body": "안녕하세요"}
    return drafts.create_draft(ME, **{**base, **over})


def _file(env, name="견적서.pdf", data=b"PDFDATA"):
    f = env.docs / name
    f.write_bytes(data)
    return f


# ── 허용 API 고정 (AI 는 읽기 + 초안 생성만) ─────────────────────────────


def test_ai_allowlist_is_exactly_read_plus_draft_creation():
    mail = {k: v for k, v in API_REGISTRY.items() if k.startswith("mailbox.")}
    assert set(mail) == {
        "mailbox.folders",
        "mailbox.list",
        "mailbox.new",
        "mailbox.read",
        "mailbox.draft",
        "mailbox.drafts",
    }
    posts = {k for k, v in mail.items() if v["method"] != "GET"}
    assert posts == {"mailbox.draft"} and mail["mailbox.draft"]["path"] == "/api/v1/naver-mailbox/drafts"


def test_no_registered_endpoint_can_send_delete_move_or_change_state():
    forbidden = ("/send", "/trash", "/move", "/purge", "/empty", "/flags", "/cancel", "/instructions", "/attachment")
    for key, entry in API_REGISTRY.items():
        if "/naver-mailbox/" in entry["path"]:
            assert not any(entry["path"].endswith(f) or f + "/" in entry["path"] for f in forbidden), key
    assert not any("naver-mailbox/drafts/" in e["path"] for e in API_REGISTRY.values())  # {id}/send · {id}/cancel 포함


def test_draft_description_tells_the_agent_to_hand_over_to_a_human_card():
    desc = API_REGISTRY["mailbox.draft"]["desc"]
    assert "[[mail-draft:<id>]]" in desc and "전송하지 않음" in desc and "카드 버튼" in desc


# ── 초안 만들기 ─────────────────────────────────────────────────────────


def test_creating_a_draft_never_sends_and_returns_a_public_view(env):
    d = _mk(env, cc="b@example.com")
    assert env.sent == [] and d["status"] == "pending" and d["to"] == ["a@example.com"] and d["cc"] == ["b@example.com"]
    assert d["created_by"] == "ai" and len(d["id"]) == 32 and d["body_preview"] == "안녕하세요"
    assert "path" not in str(d["attachments"]) and "sha256" not in str(d)


@pytest.mark.parametrize(
    "bad",
    [
        {"to": "not-an-address"},
        {"to": ""},
        {"subject": ""},
        {"subject": "줄\n바꿈"},
        {"body": ""},
        {"to": ",".join(f"u{i}@example.com" for i in range(21))},
    ],
)
def test_invalid_input_is_refused_with_a_readable_reason(env, bad):
    with pytest.raises(ServiceError):
        _mk(env, **bad)
    assert store.list_drafts() == []


def test_html_body_is_sanitized_and_gets_a_text_fallback(env):
    d = _mk(env, body="", html="<p><b>굵게</b></p><script>alert(1)</script>")
    saved = store.get_draft(d["id"])
    assert "<script" not in saved["body_html"] and saved["body_text"] == "굵게" and d["rich"] is True


def test_pending_limit_blocks_more_drafts(env, monkeypatch):
    monkeypatch.setattr(pol, "MAX_PENDING_DRAFTS", 2)
    _mk(env)
    _mk(env)
    with pytest.raises(ServiceError, match="너무 많"):
        _mk(env)


def test_unregistered_account_is_refused(env):
    with pytest.raises(ServiceError, match="등록되지"):
        drafts.create_draft("nobody", to="a@example.com", subject="s", body="b")


def test_attachment_paths_are_checked_hashed_and_shown_by_name_only(env):
    f = _file(env)
    d = _mk(env, attachment_paths=[str(f)])
    assert d["attachments"] == [{"name": "견적서.pdf", "size": 7, "kind": "path"}]
    assert store.get_draft(d["id"])["attachments"][0]["sha256"]


@pytest.mark.parametrize("name", [".env", "계정 비밀번호.txt", "tool.exe"])
def test_secret_looking_or_blocked_attachments_are_refused(env, name):
    with pytest.raises(ServiceError):
        _mk(env, attachment_paths=[str(_file(env, name))])


def test_attachment_outside_the_allowed_folders_is_refused(env, tmp_path):
    outside = tmp_path / "elsewhere.pdf"
    outside.write_bytes(b"x")
    with pytest.raises(ServiceError, match="허용된 폴더"):
        _mk(env, attachment_paths=[str(outside)])


def test_forwarding_pulls_original_attachments_and_stores_their_hash(env, monkeypatch):
    monkeypatch.setattr(
        drafts.mailbox,
        "get_attachment",
        lambda a, f, u, i, **k: {
            "ok": True,
            "filename": "도면.dwg",
            "content_type": "application/octet-stream",
            "data": b"DWG",
        },
    )
    d = _mk(env, forward={"folder": "INBOX", "uid": 7, "indices": [0]})
    meta = store.get_draft(d["id"])["attachments"][0]
    assert (
        d["attachments"] == [{"name": "도면.dwg", "size": 3, "kind": "forward"}] and meta["uid"] == 7 and meta["sha256"]
    )


# ── 보내기 (사람 전용) ──────────────────────────────────────────────────


def test_sending_marks_the_draft_sent_counts_it_and_builds_the_real_message(env):
    f = _file(env)
    d = _mk(env, cc="b@example.com", attachment_paths=[str(f)], in_reply_to="<x@y>", references="<w@z> <x@y>")
    out = drafts.send_draft(d["id"], actor="owner")
    assert out["status"] == "sent" and out["approved_by"] == "owner" and out["sent_at"] and store.sent_today(ME) == 1
    assert len(env.sent) == 1
    built = env.sent[0]
    assert built.to == ["a@example.com"] and built.cc == ["b@example.com"] and built.in_reply_to == "<x@y>"
    assert [u.filename for u in built.uploads] == ["견적서.pdf"] and built.uploads[0].data == b"PDFDATA"


def test_result_keeps_only_counts_not_addresses(env):
    d = _mk(env, to="secret.person@example.com")
    out = drafts.send_draft(d["id"], actor="owner")
    assert out["result"]["recipient_count"] == 1 and "secret.person" not in str(out["result"])


def test_a_sent_draft_cannot_be_sent_again(env):
    d = _mk(env)
    drafts.send_draft(d["id"], actor="owner")
    with pytest.raises(ServiceError, match="이미 보낸"):
        drafts.send_draft(d["id"], actor="owner")
    assert len(env.sent) == 1


def test_two_simultaneous_clicks_send_exactly_one_mail(env, monkeypatch):
    d = _mk(env)
    real = sender.send_draft

    def slow(draft, **kw):
        time.sleep(0.15)
        return real(draft, **kw)

    monkeypatch.setattr(sender, "send_draft", slow)
    results = []

    def click():
        try:
            results.append(drafts.send_draft(d["id"], actor="owner")["status"])
        except ServiceError as e:
            results.append(str(e))

    threads = [threading.Thread(target=click) for _ in range(6)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len(env.sent) == 1 and results.count("sent") == 1
    assert store.sent_today(ME) == 1


def test_uncertain_outcome_stops_in_unknown_and_is_never_retried(env):
    d = _mk(env)
    env.outcome["result"] = {"ok": False, "error": "send_unknown", "message": "연결이 끊겼습니다"}
    assert drafts.send_draft(d["id"], actor="owner")["status"] == "unknown"
    with pytest.raises(ServiceError, match="불확실"):
        drafts.send_draft(d["id"], actor="owner")
    assert len(env.sent) == 1 and store.sent_today(ME) == 0


def test_an_unexpected_exception_while_sending_is_treated_as_unknown(env):
    d = _mk(env)
    env.outcome["result"] = TimeoutError("timeout")
    out = drafts.send_draft(d["id"], actor="owner")
    assert out["status"] == "unknown" and out["result"]["message"] == "TimeoutError"
    with pytest.raises(ServiceError):
        drafts.send_draft(d["id"], actor="owner")
    assert len(env.sent) == 1


@pytest.mark.parametrize("error", ["send_failed", "auth_failed", "connect_failed", "no_password"])
def test_definite_failures_can_be_retried_by_the_user(env, error):
    d = _mk(env)
    env.outcome["result"] = {"ok": False, "error": error, "message": "거부됨"}
    assert drafts.send_draft(d["id"], actor="owner")["status"] == "failed"
    env.outcome["result"] = None
    assert drafts.send_draft(d["id"], actor="owner")["status"] == "sent"
    assert len(env.sent) == 2 and store.sent_today(ME) == 1  # 실패한 시도는 하루 한도에 세지 않는다


def test_a_file_changed_after_the_draft_was_made_is_not_sent(env):
    f = _file(env)
    d = _mk(env, attachment_paths=[str(f)])
    f.write_bytes(b"SOMETHING ELSE")
    with pytest.raises(ServiceError, match="바뀌었습니다"):
        drafts.send_draft(d["id"], actor="owner")
    assert env.sent == [] and store.get_draft(d["id"])["status"] == "pending"


def test_a_file_that_became_forbidden_is_not_sent(env):
    f = _file(env)
    d = _mk(env, attachment_paths=[str(f)])
    f.unlink()
    with pytest.raises(ServiceError, match="찾을 수 없습니다"):
        drafts.send_draft(d["id"], actor="owner")
    assert env.sent == []


def test_daily_cap_blocks_sending(env, monkeypatch):
    monkeypatch.setenv("HAEHAN_MAIL_DAILY_CAP", "1")
    first, second = _mk(env), _mk(env, subject="둘째")
    drafts.send_draft(first["id"], actor="owner")
    with pytest.raises(ServiceError, match="상한"):
        drafts.send_draft(second["id"], actor="owner")
    assert len(env.sent) == 1 and store.get_draft(second["id"])["status"] == "pending"


def test_cancelled_and_expired_drafts_cannot_be_sent(env, monkeypatch):
    cancelled = _mk(env)
    assert drafts.cancel_draft(cancelled["id"])["status"] == "cancelled"
    with pytest.raises(ServiceError, match="취소"):
        drafts.send_draft(cancelled["id"], actor="owner")
    old = _mk(env, subject="오래됨")
    future = datetime.now(UTC) + timedelta(days=pol.DRAFT_TTL_DAYS + 1)

    class Later(datetime):
        @classmethod
        def now(cls, tz=None):
            return future if tz else future.replace(tzinfo=None)

    monkeypatch.setattr(store, "datetime", Later)
    with pytest.raises(ServiceError, match="만료"):
        drafts.send_draft(old["id"], actor="owner")
    assert env.sent == []


def test_cancel_only_works_on_open_drafts(env):
    d = _mk(env)
    drafts.send_draft(d["id"], actor="owner")
    with pytest.raises(ServiceError, match="취소할 수 없는"):
        drafts.cancel_draft(d["id"])
    with pytest.raises(ServiceError, match="찾을 수 없습니다"):
        drafts.send_draft("0" * 32, actor="owner")


def test_listing_shows_open_drafts_by_default_and_all_on_request(env):
    keep, done = _mk(env), _mk(env, subject="보낸 것")
    drafts.send_draft(done["id"], actor="owner")
    assert [d["id"] for d in drafts.list_drafts(ME)] == [keep["id"]]
    assert {d["id"] for d in drafts.list_drafts(ME, only_open=False)} == {keep["id"], done["id"]}


# ── 업무 지침 · AI 용 읽기 ──────────────────────────────────────────────


def test_instructions_roundtrip_trim_and_limit(env):
    assert drafts.get_instructions(ME) == ""
    assert (
        drafts.set_instructions(ME, "  서명은 신재우  ") == "서명은 신재우"
        and drafts.get_instructions(ME) == "서명은 신재우"
    )
    with pytest.raises(ServiceError, match="4000"):
        drafts.set_instructions(ME, "가" * (pol.INSTRUCTIONS_MAX_CHARS + 1))


def test_compact_message_is_text_only_and_bounded(env, monkeypatch):
    big = {
        "ok": True, "uid": 5, "folder": "INBOX", "subject": "견적", "from": {"name": "김", "address": "k@example.com"}, "to": [], "cc": [],
        "date": "d", "message_id": "<m@x>", "references": "", "seen": False, "text": "", "html": "<p>" + "가" * 20000 + "</p><script>x()</script>",
        "attachments": [{"index": 0, "filename": "a.pdf", "size": 3, "content_type": "application/pdf", "previewable": True}], "quote_html": "<p>x</p>",
    }  # fmt: skip
    monkeypatch.setattr(drafts.mailbox, "get_message", lambda *a, **k: big)
    out = drafts.compact_message(ME, "INBOX", 5)
    assert len(out["text"]) == drafts.COMPACT_TEXT_LIMIT and out["truncated"] is True
    assert "html" not in out and "quote_html" not in out and "script" not in out["text"]
    assert out["attachments"] == [{"index": 0, "filename": "a.pdf", "size": 3, "content_type": "application/pdf"}]


def test_compact_message_passes_errors_through(env, monkeypatch):
    monkeypatch.setattr(
        drafts.mailbox,
        "get_message",
        lambda *a, **k: {"ok": False, "error": "not_found", "message": "해당 메일이 없습니다"},
    )
    assert drafts.compact_message(ME, "INBOX", 9)["error"] == "not_found"


# ── API ─────────────────────────────────────────────────────────────────


@pytest.fixture
def api(env):
    app = FastAPI()
    app.include_router(naver_mailbox_router)
    role = {"role": "owner"}
    app.dependency_overrides[get_current_user] = lambda: {"actor": "tester", "role": role["role"]}
    return TestClient(app), role


def test_api_creates_a_pending_draft_and_only_a_human_call_sends_it(api, env):
    client, _ = api
    made = client.post(
        "/naver-mailbox/drafts", json={"account": ME, "to": "a@example.com", "subject": "제목", "body": "본문"}
    )
    assert made.status_code == 200 and made.json()["status"] == "pending" and env.sent == []
    draft_id = made.json()["id"]
    assert client.get(f"/naver-mailbox/drafts/{draft_id}").json()["id"] == draft_id
    assert [d["id"] for d in client.get("/naver-mailbox/drafts", params={"account": ME}).json()["drafts"]] == [draft_id]
    sent = client.post(f"/naver-mailbox/drafts/{draft_id}/send")
    assert sent.status_code == 200 and sent.json()["status"] == "sent" and sent.json()["approved_by"] == "tester"
    assert client.post(f"/naver-mailbox/drafts/{draft_id}/send").status_code == 400  # 두 번째는 거부


def test_api_validation_errors_are_400_and_bad_ids_are_rejected(api):
    client, _ = api
    assert (
        client.post("/naver-mailbox/drafts", json={"account": ME, "to": "bad", "subject": "s", "body": "b"}).status_code
        == 400
    )
    assert (
        client.post(
            "/naver-mailbox/drafts", json={"account": "nobody", "to": "a@example.com", "subject": "s", "body": "b"}
        ).status_code
        == 400
    )
    assert client.get("/naver-mailbox/drafts/not-a-valid-id").status_code == 422
    assert client.post("/naver-mailbox/drafts/ZZZ/send").status_code == 422
    assert client.get(f"/naver-mailbox/drafts/{'0' * 32}").status_code == 404


def test_api_requires_admin_for_everything_here(api):
    client, role = api
    role["role"] = "viewer"
    calls = [
        ("get", "/naver-mailbox/new?account=skyjwsin"),
        ("get", "/naver-mailbox/message/compact?account=skyjwsin&folder=INBOX&uid=1"),
        ("post", "/naver-mailbox/drafts"),
        ("get", "/naver-mailbox/drafts?account=skyjwsin"),
        ("post", f"/naver-mailbox/drafts/{'0' * 32}/send"),
        ("post", f"/naver-mailbox/drafts/{'0' * 32}/cancel"),
        ("get", "/naver-mailbox/instructions?account=skyjwsin"),
        ("post", "/naver-mailbox/instructions"),
    ]
    for method, url in calls:
        assert getattr(client, method)(url, **({"json": {}} if method == "post" else {})).status_code == 403, url


def test_api_cancel_and_instructions(api, env):
    client, _ = api
    draft_id = client.post(
        "/naver-mailbox/drafts", json={"account": ME, "to": "a@example.com", "subject": "s", "body": "b"}
    ).json()["id"]
    assert client.post(f"/naver-mailbox/drafts/{draft_id}/cancel").json()["status"] == "cancelled"
    assert client.post(f"/naver-mailbox/drafts/{draft_id}/cancel").status_code == 400
    assert client.post("/naver-mailbox/instructions", json={"account": ME, "text": "존댓말"}).json()["text"] == "존댓말"
    assert client.get("/naver-mailbox/instructions", params={"account": ME}).json()["text"] == "존댓말"
    assert client.post("/naver-mailbox/instructions", json={"account": ME, "text": "가" * 5000}).status_code == 400


def test_api_new_mail_and_compact_message_delegate(api, monkeypatch):
    client, _ = api
    monkeypatch.setattr(
        drafts.reader,
        "list_new",
        lambda account, **k: {
            "ok": True,
            "baseline_set": False,
            "last_uid": 9,
            "total_new": 1,
            "messages": [{"uid": "9"}],
            "args": k,
        },
    )
    got = client.get("/naver-mailbox/new", params={"account": ME, "limit": 5, "advance": "true"}).json()
    assert got["messages"] == [{"uid": "9"}] and got["args"] == {"limit": 5, "advance": True}
    monkeypatch.setattr(
        drafts.mailbox, "get_message", lambda *a, **k: {"ok": False, "error": "not_found", "message": "없음"}
    )
    assert (
        client.get("/naver-mailbox/message/compact", params={"account": ME, "folder": "INBOX", "uid": 1}).status_code
        == 404
    )
    assert client.get("/naver-mailbox/new", params={"account": "nobody"}).status_code == 400


def test_draft_files_never_leave_the_documents_area_via_the_api(api, env, tmp_path):
    client, _ = api
    secret = tmp_path / "outside.pdf"
    secret.write_bytes(b"x")
    r = client.post(
        "/naver-mailbox/drafts",
        json={"account": ME, "to": "a@example.com", "subject": "s", "body": "b", "attachment_paths": [str(secret)]},
    )
    assert r.status_code == 400 and "허용된 폴더" in r.json()["detail"] and store.list_drafts() == []
    assert Path(str(secret)).exists()
