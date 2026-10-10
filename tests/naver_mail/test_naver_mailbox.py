"""네이버 메일함 탭 — 폴더·목록·상세·첨부·상태 변경(mailbox), 첨부 규칙, 보내기 2단계(service), 라우터 응답.

가짜 IMAP/SMTP 로 검증하며 네이버 서버·브라우저를 쓰지 않는다. 기준서: docs/specs/2026-10-01_naver_mailbox_tab.md
"""

from __future__ import annotations

import base64
import imaplib
import re
import time
from email.message import EmailMessage

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_orchestrator.connectors.naver_mail import mailbox_flow as service
from ai_orchestrator.connectors.naver_mail.mailbox_router import naver_mailbox_router
from scripts.naver.mail.imap import attachments as att
from scripts.naver.mail.imap import folders as fld
from scripts.naver.mail.imap import imap_mailbox as mb
from scripts.naver.mail.imap import sender
from tools.gates.auth import get_current_user

PW = "not-a-real-value-123456"
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000a49444154789c6360000000020001e221bc330000000049454e44ae426082"
)
LIST_LINES = [
    b'(\\HasNoChildren \\Inbox) "/" "INBOX"',
    b'(\\HasNoChildren \\Sent) "/" "Sent Messages"',
    b'(\\HasNoChildren \\Drafts) "/" "Drafts"',
    b'(\\HasNoChildren \\Trash) "/" "Deleted Messages"',
    b'(\\HasNoChildren \\Junk) "/" "Junk"',
    b'(\\HasChildren) "/" "&sLSsjMT0ulTHfNVo-"',
    b'(\\HasNoChildren) "/" "&sLSsjMT0ulTHfNVo-/&yRHGlLs4wRw-"',
    b'(\\HasNoChildren) "/" "SNS"',
]


def _plain(subject, frm, body="본문"):
    m = EmailMessage()
    m["From"], m["To"], m["Subject"], m["Date"] = frm, "me@naver.com", subject, "Thu, 01 Oct 2026 10:00:00 +0900"
    m.set_content(body)
    return m


def _with_attachment():
    m = _plain("견적서 송부", "이영희 <lee@example.com>", "첨부 확인하세요")
    m.add_attachment(b"%PDF-1.4 test", maintype="application", subtype="pdf", filename="../견적서.pdf")
    m.add_attachment(b"MZ", maintype="application", subtype="octet-stream", filename="tool.exe")
    return m


def _html_with_inline():
    m = _plain("행사 안내", "마케팅 <ad@example.com>", "텍스트 본문")
    m.add_alternative('<p>안녕</p><img src="cid:logo1"><script>alert(1)</script>', subtype="html")
    m.get_payload()[1].add_related(PNG, "image", "png", cid="<logo1>")
    return m


class FakeIMAP:
    """UID 1(안 읽음, 평문) · 2(읽음, 첨부) · 3(안 읽음, HTML+인라인 이미지)."""

    def __init__(self, *, auth_ok=True):
        self.auth_ok, self.calls, self.selected, self.logged_out = auth_ok, [], None, False
        # UID 2 만 실제 첨부(disposition=attachment), 3 은 multipart 이지만 인라인 이미지뿐
        self.structure = {
            2: '(("text" "plain" NIL NIL NIL "7bit" 9 1) ("application" "pdf" ("name" "a.pdf") NIL NIL "base64" 99 ("attachment" ("filename" "a.pdf"))) "mixed")',
            3: '(("text" "plain" NIL NIL NIL "7bit" 9 1) ("image" "png" NIL "<logo1>" NIL "base64" 99 ("inline" ("filename" "l.png"))) "related")',
        }
        self.msgs = {
            1: (_plain("견적 요청", "김철수 <kim@example.com>").as_bytes(), []),
            2: (_with_attachment().as_bytes(), ["\\Seen"]),
            3: (_html_with_inline().as_bytes(), []),
        }

    def login(self, user, pw):
        if not self.auth_ok:
            raise imaplib.IMAP4.error("[AUTH] Authentication failed")
        return "OK", [b"ok"]

    def list(self):
        return "OK", LIST_LINES

    def status(self, mailbox, what):
        return "OK", [b'"x" (MESSAGES 3 UNSEEN 2)']

    def select(self, mailbox, readonly=False):
        self.selected = (mailbox, readonly)
        return "OK", [b"3"]

    def _meta(self, uid):
        raw, flags = self.msgs[uid]
        return f"{uid} (UID {uid} FLAGS ({' '.join(flags)}) RFC822.SIZE {len(raw)}"

    def uid(self, command, *args):
        self.calls.append((command, args))
        if command == "SEARCH":
            return "OK", [" ".join(str(u) for u in self.msgs).encode()]
        if command == "FETCH":
            ids = [int(u) for u in str(args[0]).split(",")]
            what = args[1]
            out = []
            for uid in ids:
                raw = self.msgs[uid][0]
                if "HEADER.FIELDS" in what:
                    head = raw.split(b"\n\n", 1)[0] + b"\n\n"
                    out += [(f"{self._meta(uid)} BODY[HEADER.FIELDS (X)] {{{len(head)}}}".encode(), head), b")"]
                elif "BODY.PEEK[]" in what:
                    out += [(f"{self._meta(uid)} BODY[] {{{len(raw)}}}".encode(), raw), b")"]
                else:
                    out.append((self._meta(uid) + ")").encode())
            return "OK", out
        return "OK", [b"done"]

    def noop(self):
        if getattr(self, "dead", False):
            raise OSError("연결이 끊어졌습니다")
        self.calls.append(("NOOP", ()))
        return "OK", [b"done"]

    def unselect(self):
        self.calls.append(("UNSELECT", ()))
        return "OK", [b"done"]

    def logout(self):
        self.logged_out = True


@pytest.fixture(autouse=True)
def _fresh_cache():
    mb.clear_row_cache()
    mb.clear_raw_cache()
    mb.clear_pool()
    yield
    mb.clear_row_cache()
    mb.clear_raw_cache()
    mb.clear_pool()


def _fake():
    return FakeIMAP()


def _call(fn, *args, fake=None, **kw):
    fake = fake or _fake()
    return fn(*args, password=PW, factory=lambda h, p: fake, **kw), fake


# ── 폴더 ────────────────────────────────────────────────────────────────


def test_utf7_round_trip_and_ampersand():
    for name in ("거래처/견적", "Reports & Plans", "plain"):
        assert fld.utf7_decode(fld.utf7_encode(name)) == name
    assert fld.utf7_decode("a&-b") == "a&b"


def test_folder_list_orders_system_folders_first_and_names_them_in_korean():
    result, fake = _call(mb.list_folders, "skyjwsin")
    names = [f["name"] for f in result["folders"]]
    assert names[:5] == ["받은편지함", "보낸메일함", "임시보관함", "스팸메일함", "휴지통"]
    assert "SNS" in names[5:]
    user = [f for f in result["folders"] if f["kind"] == "user"]
    assert all(f["total"] == 3 and f["unseen"] == 2 for f in user)
    child = next(f for f in user if f["depth"] == 1)
    assert fld.utf7_decode(child["id"]).count("/") == 1 and fake.logged_out


def test_folder_ids_are_quoted_when_selected():
    result, fake = _call(mb.list_messages, "skyjwsin", mb.ListQuery(folder="Sent Messages"))
    assert fake.selected == ('"Sent Messages"', True) and result["ok"]


# ── 목록 ────────────────────────────────────────────────────────────────


def test_list_is_newest_first_with_flags_and_attachment_marker():
    result, _ = _call(mb.list_messages, "skyjwsin", mb.ListQuery())
    rows = result["messages"]
    assert [r["uid"] for r in rows] == [3, 2, 1] and result["total"] == 3
    by_uid = {r["uid"]: r for r in rows}
    assert by_uid[2]["seen"] and not by_uid[1]["seen"]
    assert by_uid[2]["has_attachment"] and not by_uid[1]["has_attachment"]
    assert not by_uid[3]["has_attachment"]  # 인라인 이미지뿐인 메일에는 클립을 붙이지 않는다
    assert by_uid[1]["from"] == {"name": "김철수", "address": "kim@example.com"}


def test_list_paging_and_server_side_unseen_criteria():
    result, fake = _call(mb.list_messages, "skyjwsin", mb.ListQuery(page=2, per_page=2, filter="unseen"))
    assert [r["uid"] for r in result["messages"]] == [1]
    search = next(c for c in fake.calls if c[0] == "SEARCH")
    assert search[1][1:] == ("UNSEEN",)


def test_attachment_filter_and_korean_query_are_applied_client_side():
    only_attach, _ = _call(mb.list_messages, "skyjwsin", mb.ListQuery(filter="attach"))
    assert [r["uid"] for r in only_attach["messages"]] == [2]
    found, _ = _call(mb.list_messages, "skyjwsin", mb.ListQuery(query="철수"))
    assert [r["uid"] for r in found["messages"]] == [1] and found["total"] == 1
    assert _call(mb.list_messages, "skyjwsin", mb.ListQuery(filter="bogus"))[0]["error"] == "bad_filter"


def test_list_never_writes_flags():
    _, fake = _call(mb.list_messages, "skyjwsin", mb.ListQuery())
    assert not any(c[0] in ("STORE", "MOVE") for c in fake.calls) and fake.selected[1] is True


def test_headers_are_cached_but_read_flags_are_refreshed_every_time():
    first, fake1 = _call(mb.list_messages, "skyjwsin", mb.ListQuery())
    full_fetches_1 = [c for c in fake1.calls if c[0] == "FETCH" and "HEADER.FIELDS" in c[1][1]]
    assert len(full_fetches_1) == 1
    # 같은 서버 상태에서 다시 조회 — 내용을 읽는 FETCH 는 더 하지 않는다
    again, fake2 = _call(mb.list_messages, "skyjwsin", mb.ListQuery())
    assert not [c for c in fake2.calls if c[0] == "FETCH" and "HEADER.FIELDS" in c[1][1]]
    assert [r["subject"] for r in again["messages"]] == [r["subject"] for r in first["messages"]]
    # 그 사이 읽음 표시가 바뀌면 캐시와 무관하게 반영된다
    changed = _fake()
    changed.msgs[1] = (changed.msgs[1][0], [r"\Seen", r"\Flagged"])
    after, _ = _call(mb.list_messages, "skyjwsin", mb.ListQuery(), fake=changed)
    row1 = next(r for r in after["messages"] if r["uid"] == 1)
    assert row1["seen"] is True and row1["flagged"] is True


def test_cache_is_per_account_and_folder():
    _call(mb.list_messages, "skyjwsin", mb.ListQuery(folder="INBOX"))
    _, fake = _call(mb.list_messages, "skyjwsin", mb.ListQuery(folder="Sent Messages"))
    assert [c for c in fake.calls if c[0] == "FETCH" and "HEADER.FIELDS" in c[1][1]]


# ── 상세 ────────────────────────────────────────────────────────────────


def test_open_message_does_not_mark_it_read():
    result, fake = _call(mb.get_message, "skyjwsin", "INBOX", 1)
    assert result["ok"] and result["seen"] is False and "본문" in result["text"]
    assert not any(c[0] == "STORE" for c in fake.calls)
    assert all("PEEK" in c[1][1] for c in fake.calls if c[0] == "FETCH" and "BODY" in c[1][1])
    assert fake.selected[1] is True


def test_attachment_list_uses_safe_names_and_marks_previewable():
    result, _ = _call(mb.get_message, "skyjwsin", "INBOX", 2)
    files = result["attachments"]
    assert [f["filename"] for f in files] == ["견적서.pdf", "tool.exe"]
    assert files[0]["previewable"] and not files[1]["previewable"] and files[0]["size"] == len(b"%PDF-1.4 test")


def test_inline_cid_image_becomes_data_uri_and_external_scripts_stay_in_html_for_sandbox():
    result, _ = _call(mb.get_message, "skyjwsin", "INBOX", 3)
    assert "data:image/png;base64," in result["html"] and "cid:" not in result["html"]
    assert result["attachments"] == []  # 인라인 이미지는 첨부 목록에 넣지 않는다
    assert "<script>" in result["html"]  # 제거는 화면의 sandbox iframe 이 맡는다(서버는 원문 보존)


def test_download_attachment_returns_bytes_and_rejects_bad_index_or_size(monkeypatch):
    got, _ = _call(mb.get_attachment, "skyjwsin", "INBOX", 2, 0)
    assert got["ok"] and got["data"] == b"%PDF-1.4 test" and got["filename"] == "견적서.pdf"
    assert _call(mb.get_attachment, "skyjwsin", "INBOX", 2, 5)[0]["error"] == "not_found"
    monkeypatch.setattr(att, "MAX_DOWNLOAD_BYTES", 3)
    assert _call(mb.get_attachment, "skyjwsin", "INBOX", 2, 0)[0]["error"] == "too_large"


def test_oversized_message_is_refused_before_download(monkeypatch):
    monkeypatch.setattr(att, "MAX_MESSAGE_BYTES", 10)
    result, fake = _call(mb.get_message, "skyjwsin", "INBOX", 1)
    assert result["error"] == "too_large" and not any("BODY.PEEK[]" in str(c) for c in fake.calls)


def test_auth_failure_is_reported_without_secrets():
    result, _ = _call(mb.get_message, "skyjwsin", "INBOX", 1, fake=FakeIMAP(auth_ok=False))
    assert result["error"] == "auth_failed" and PW not in str(result)


# ── 상태 변경 ───────────────────────────────────────────────────────────


def test_mark_seen_and_unseen_write_flags_in_write_mode():
    ok, fake = _call(mb.set_seen, "skyjwsin", "INBOX", 1, True)
    assert ok["ok"] and fake.selected[1] is False
    assert ("STORE", ("1", "+FLAGS.SILENT", "(\\Seen)")) in fake.calls
    _, fake2 = _call(mb.set_seen, "skyjwsin", "INBOX", 1, False)
    assert ("STORE", ("1", "-FLAGS.SILENT", "(\\Seen)")) in fake2.calls


def test_trash_moves_to_the_trash_folder_and_never_deletes_permanently():
    ok, fake = _call(mb.move_to_trash, "skyjwsin", "INBOX", 1)
    assert ok == {"ok": True, "moved_to": "Deleted Messages", "count": 1}
    assert ("MOVE", ("1", '"Deleted Messages"')) in fake.calls
    assert not any(c[0] == "EXPUNGE" for c in fake.calls)
    again, fake2 = _call(mb.move_to_trash, "skyjwsin", "Deleted Messages", 1)
    assert again["error"] == "already_in_trash" and not any(c[0] == "MOVE" for c in fake2.calls)


def test_bulk_seen_and_trash_use_one_connection_and_one_command():
    ok, fake = _call(mb.set_seen, "skyjwsin", "INBOX", [1, 2, 3], True)
    assert ok["ok"] and ("STORE", ("1,2,3", "+FLAGS.SILENT", r"(\Seen)")) in fake.calls
    moved, fake2 = _call(mb.move_to_trash, "skyjwsin", "INBOX", [1, 2])
    assert moved == {"ok": True, "moved_to": "Deleted Messages", "count": 2}
    assert [c for c in fake2.calls if c[0] == "MOVE"] == [("MOVE", ("1,2", '"Deleted Messages"'))]


def test_move_to_any_existing_folder_but_not_to_itself_or_a_missing_one():
    ok, fake = _call(mb.move_messages, "skyjwsin", "INBOX", [1, 2], "SNS")
    assert ok == {"ok": True, "moved_to": "SNS", "count": 2} and ("MOVE", ("1,2", '"SNS"')) in fake.calls
    assert _call(mb.move_messages, "skyjwsin", "INBOX", [1], "INBOX")[0]["error"] == "same_folder"
    nope, fake2 = _call(mb.move_messages, "skyjwsin", "INBOX", [1], "NoSuchFolder")
    assert nope["error"] == "folder_not_found" and not any(c[0] == "MOVE" for c in fake2.calls)


@pytest.mark.parametrize("bad", [[], [0], [-1], [True], ["1"], list(range(1, 102))])
def test_uid_lists_are_validated_before_any_write(bad):
    result, fake = _call(mb.move_to_trash, "skyjwsin", "INBOX", bad)
    assert result["error"] == "bad_uid" and not any(c[0] in ("MOVE", "STORE") for c in fake.calls)


def test_purge_only_works_in_trash_or_spam_and_expunges_only_the_given_uids():
    refused, fake = _call(mb.purge, "skyjwsin", "INBOX", [1])
    assert refused["error"] == "not_purgeable" and not any(c[0] in ("STORE", "EXPUNGE") for c in fake.calls)
    ok, fake2 = _call(mb.purge, "skyjwsin", "Deleted Messages", [4, 5])
    assert ok == {"ok": True, "count": 2}
    assert [c for c in fake2.calls if c[0] in ("STORE", "EXPUNGE")] == [
        ("STORE", ("4,5", "+FLAGS.SILENT", r"(\Deleted)")),
        ("EXPUNGE", ("4,5",)),
    ]
    assert _call(mb.purge, "skyjwsin", "Junk", [9])[0]["ok"]


def test_empty_folder_is_limited_to_trash_and_spam():
    refused, fake = _call(mb.empty_folder, "skyjwsin", "SNS")
    assert refused["error"] == "not_purgeable" and not any(c[0] in ("STORE", "EXPUNGE") for c in fake.calls)
    ok, fake2 = _call(mb.empty_folder, "skyjwsin", "Junk")
    assert ok == {"ok": True, "count": 3} and ("EXPUNGE", ("1,2,3",)) in fake2.calls


# ── 연결 풀·원문 캐시·미리 데우기 (속도) ────────────────────────────────


@pytest.fixture
def server(monkeypatch):
    """imaplib.IMAP4_SSL 을 가짜로 바꿔 풀(factory=None) 경로를 시험한다. 만든 연결을 기록한다."""
    made: list[FakeIMAP] = []

    def build(host, port):
        fake = FakeIMAP()
        made.append(fake)
        return fake

    monkeypatch.setattr(imaplib, "IMAP4_SSL", build)
    monkeypatch.setenv("NAVER_MAIL_PW_SKYJWSIN", PW)
    return made


def test_connections_are_reused_instead_of_logging_in_every_time(server):
    first = mb.get_message("skyjwsin", "INBOX", 1)
    second = mb.get_message("skyjwsin", "INBOX", 2)
    assert first["ok"] and second["ok"] and len(server) == 1
    assert ("NOOP", ()) in server[0].calls and not server[0].logged_out  # 두 번째는 살아 있는지 확인 후 재사용


def test_a_dead_connection_is_replaced_and_closed(server):
    mb.get_message("skyjwsin", "INBOX", 1)
    server[0].dead = True
    again = mb.get_message("skyjwsin", "INBOX", 1)
    assert again["ok"] and len(server) == 2 and server[0].logged_out


def test_connections_idle_too_long_are_not_reused(server, monkeypatch):
    mb.get_message("skyjwsin", "INBOX", 1)
    monkeypatch.setattr(mb, "POOL_IDLE_SEC", -1)
    mb.get_message("skyjwsin", "INBOX", 1)
    assert len(server) == 2 and server[0].logged_out


def test_a_failed_operation_never_returns_its_connection_to_the_pool(server, monkeypatch):
    monkeypatch.setattr(att, "MAX_MESSAGE_BYTES", 10)
    bad = mb.get_message("skyjwsin", "INBOX", 1)  # 메일이 너무 큼 → 작업 도중 오류
    assert bad["error"] == "too_large" and server[0].logged_out
    monkeypatch.undo()  # fixture 가 건 설정까지 함께 풀리므로 비밀번호를 다시 건다(실제 저장소 자격증명에 의존하지 않게)
    monkeypatch.setenv("NAVER_MAIL_PW_SKYJWSIN", PW)
    monkeypatch.setattr(imaplib, "IMAP4_SSL", lambda h, p: server.append(FakeIMAP()) or server[-1])
    assert mb.get_message("skyjwsin", "INBOX", 1)["ok"] and len(server) == 2


def test_pool_keeps_at_most_a_few_idle_connections_per_account(server):
    with (
        mb.session("skyjwsin", "INBOX") as c1,
        mb.session("skyjwsin", "INBOX") as c2,
        mb.session("skyjwsin", "INBOX") as c3,
        mb.session("skyjwsin", "INBOX") as c4,
    ):
        assert len({id(c) for c in (c1, c2, c3, c4)}) == 4
    assert len(server) == 4 and sum(f.logged_out for f in server) == 1  # 4개 중 3개만 보관, 1개는 닫힘


def test_wrong_password_is_reported_and_nothing_is_pooled(server, monkeypatch):
    def refuse(host, port):
        fake = FakeIMAP(auth_ok=False)
        server.append(fake)
        return fake

    monkeypatch.setattr(imaplib, "IMAP4_SSL", refuse)
    result = mb.get_message("skyjwsin", "INBOX", 1)
    assert result["error"] == "auth_failed" and server[0].logged_out and PW not in str(result)


def test_folder_list_unselects_first_so_status_is_not_stale(server):
    mb.list_messages("skyjwsin", mb.ListQuery())  # INBOX 를 선택한 채 풀에 돌아감
    assert mb.list_folders("skyjwsin")["ok"] and ("UNSELECT", ()) in server[0].calls


def test_reopening_a_message_and_downloading_its_attachment_reuse_the_cached_original(server):
    first = mb.get_message("skyjwsin", "INBOX", 2)
    bodies = lambda: [c for c in server[0].calls if c[0] == "FETCH" and "BODY.PEEK[]" in c[1][1]]  # noqa: E731
    assert len(bodies()) == 1
    again = mb.get_message("skyjwsin", "INBOX", 2)
    download = mb.get_attachment("skyjwsin", "INBOX", 2, 0)
    assert again["subject"] == first["subject"] and download["ok"] and download["data"] == b"%PDF-1.4 test"
    assert len(bodies()) == 1  # 서버에서 다시 받지 않았다


def test_cached_message_still_shows_fresh_read_flags_and_refetches_when_size_changes(server):
    assert mb.get_message("skyjwsin", "INBOX", 1)["seen"] is False
    server[0].msgs[1] = (server[0].msgs[1][0], [r"\Seen"])
    assert mb.get_message("skyjwsin", "INBOX", 1)["seen"] is True  # 캐시된 원문이어도 읽음 표시는 새로 받는다
    server[0].msgs[1] = (_plain("바뀐 제목", "김철수 <kim@example.com>", "더 긴 본문 " * 20).as_bytes(), [])
    changed = mb.get_message("skyjwsin", "INBOX", 1)
    assert changed["subject"] == "바뀐 제목"  # 크기가 달라지면 캐시를 쓰지 않는다


def test_raw_cache_is_bounded(monkeypatch):
    monkeypatch.setattr(mb, "_RAW_CACHE_MAX_ITEMS", 2)
    for uid in (1, 2, 3):
        mb._raw_put(("a", "INBOX", uid, 10), b"x" * 10)
    assert mb._raw_get(("a", "INBOX", 1, 10)) is None and mb._raw_get(("a", "INBOX", 3, 10)) == b"x" * 10
    monkeypatch.setattr(mb, "_RAW_CACHE_MAX_BYTES", 100)
    mb._raw_put(("a", "INBOX", 9, 80), b"y" * 80)  # 상한의 절반을 넘는 메일은 보관하지 않는다
    assert mb._raw_get(("a", "INBOX", 9, 80)) is None


def test_next_page_headers_are_warmed_in_the_background(server, monkeypatch):
    threads = []

    class Inline:
        def __init__(self, target, daemon=True, name=""):
            self.target = target
            threads.append(self)

        def start(self):
            self.target()  # 시험에서는 바로 실행해 결과를 확인한다

    monkeypatch.setattr(mb.threading, "Thread", Inline)
    page1 = mb.list_messages("skyjwsin", mb.ListQuery(per_page=1, page=1))
    assert [r["uid"] for r in page1["messages"]] == [3] and len(threads) == 1
    page2 = mb.list_messages("skyjwsin", mb.ListQuery(per_page=1, page=2))  # 2쪽은 이미 데워져 있다
    assert [r["uid"] for r in page2["messages"]] == [2]
    fetched_uid2 = [
        c for f in server for c in f.calls if c[0] == "FETCH" and c[1][0] == "2" and "HEADER.FIELDS" in c[1][1]
    ]
    assert len(fetched_uid2) == 1  # 2번 메일의 헤더는 미리 데울 때 한 번만 받았고, 2쪽 조회는 캐시를 썼다
    assert len(threads) == 2  # 2쪽을 열 때 3쪽을 또 미리 데운다


def test_warming_is_skipped_when_a_factory_is_injected():
    result, _ = _call(mb.list_messages, "skyjwsin", mb.ListQuery(per_page=1))
    assert result["ok"] and not any(t.name == "mailbox-warm" for t in __import__("threading").enumerate())


# ── 첨부 규칙·보낼 메일 ─────────────────────────────────────────────────


def test_safe_filename_and_blocked_types():
    assert att.safe_filename("../../etc/pass:wd?.txt") == "pass_wd_.txt"
    assert att.safe_filename("") == "첨부파일" and len(att.safe_filename("a" * 400 + ".pdf")) <= 150
    for bad in ("run.exe", "x.BAT", "report.exe.txt", "a.js"):
        assert att.is_blocked(bad)
    assert not att.is_blocked("견적서.pdf") and not att.is_blocked("notes.txt")


def test_upload_validation_rules(monkeypatch):
    ok = att.validate_uploads([att.Upload("../a.pdf", "application/pdf", b"x")])
    assert ok[0].filename == "a.pdf"
    with pytest.raises(ValueError, match="형식"):
        att.validate_uploads([att.Upload("a.exe", "", b"x")])
    with pytest.raises(ValueError, match="빈 파일"):
        att.validate_uploads([att.Upload("a.txt", "", b"")])
    monkeypatch.setattr(att, "MAX_UPLOAD_FILE_BYTES", 2)
    with pytest.raises(ValueError, match="MB"):
        att.validate_uploads([att.Upload("a.txt", "", b"xyz")])
    monkeypatch.setattr(att, "MAX_UPLOAD_COUNT", 1)
    with pytest.raises(ValueError, match="최대"):
        att.validate_uploads([att.Upload("a.txt", "", b"x"), att.Upload("b.txt", "", b"x")])


def test_draft_builds_cc_bcc_attachment_and_reply_headers():
    d = sender.make_draft(
        "skyjwsin", "a@example.com", "제목", "본문", cc="b@example.com", bcc="c@example.com",
        uploads=[att.Upload("견적서.pdf", "application/pdf", b"PDF")], in_reply_to="<id1@x>", references="<id0@x> <id1@x>",
    )  # fmt: skip
    msg = sender.build_full_message(d)
    assert msg["Cc"] == "b@example.com" and msg["Bcc"] == "c@example.com" and msg["In-Reply-To"] == "<id1@x>"
    assert [p.get_filename() for p in msg.iter_attachments()] == ["견적서.pdf"]
    assert d.all_recipients == ["a@example.com", "b@example.com", "c@example.com"]


def test_draft_limits_and_header_injection():
    many = ", ".join(f"u{i}@example.com" for i in range(8))
    with pytest.raises(ValueError, match="합쳐"):
        sender.make_draft("skyjwsin", many, "s", "b", cc=many, bcc=many)
    with pytest.raises(ValueError):
        sender.make_draft("skyjwsin", "a@example.com", "s", "b", in_reply_to="<x>\nBcc: evil@example.com")
    with pytest.raises(ValueError):
        sender.make_draft("skyjwsin", "a@example.com", "s", "b", cc="not-an-address")


def test_rich_draft_is_multipart_with_text_fallback_inline_image_and_attachment():
    b64 = base64.b64encode(PNG).decode()
    html = f'<p><b>안녕하세요</b></p><script>alert(1)</script><img src="data:image/png;base64,{b64}"><a href="javascript:x()">나쁜 링크</a>'
    d = sender.make_draft(
        "skyjwsin",
        "a@example.com",
        "제목",
        "",
        html=html,
        uploads=[att.Upload("견적서.pdf", "application/pdf", b"PDF")],
    )
    assert (
        d.body.startswith("안녕하세요")
        and "<script" not in d.html
        and "javascript:" not in d.html
        and "data:image" not in d.html
    )
    msg = sender.build_full_message(d)
    kinds = [p.get_content_type() for p in msg.walk()]
    assert (
        msg.get_content_type() == "multipart/mixed"
        and "multipart/alternative" in kinds
        and "multipart/related" in kinds
    )
    assert "text/plain" in kinds and "text/html" in kinds and "image/png" in kinds and "application/pdf" in kinds
    image = next(p for p in msg.walk() if p.get_content_type() == "image/png")
    assert image["Content-ID"] == f"<{d.inline_images[0].cid}>" and f"cid:{d.inline_images[0].cid}" in d.html


def test_plain_draft_stays_plain_text():
    msg = sender.build_full_message(sender.make_draft("skyjwsin", "a@example.com", "제목", "본문"))
    assert msg.get_content_type() == "text/plain"


def test_html_only_image_mail_gets_a_text_fallback_and_empty_body_is_rejected():
    b64 = base64.b64encode(PNG).decode()
    d = sender.make_draft("skyjwsin", "a@example.com", "제목", "", html=f'<img src="data:image/png;base64,{b64}">')
    assert d.body == "[이미지]"
    with pytest.raises(ValueError, match="본문"):
        sender.make_draft("skyjwsin", "a@example.com", "제목", "", html="<p> </p>")


def test_quote_html_for_replies_is_sanitized_and_plain_mail_is_escaped():
    result, _ = _call(mb.get_message, "skyjwsin", "INBOX", 3)
    assert (
        "<script" not in result["quote_html"]
        and "<p>안녕</p>" in result["quote_html"]
        and "data:image/png" in result["quote_html"]
    )
    plain, _ = _call(mb.get_message, "skyjwsin", "INBOX", 1)
    assert plain["quote_html"] == "본문"


def test_prepare_over_http_accepts_html_without_plain_body(api, sent):
    client, _ = api
    form = {
        "account": "skyjwsin",
        "to": "a@example.com",
        "subject": "서식 메일",
        "html": "<p><b>굵게</b><script>x()</script></p>",
    }
    prep = client.post("/naver-mailbox/send/prepare", data=form)
    assert (
        prep.status_code == 200
        and prep.json()["summary"]["rich"] is True
        and prep.json()["summary"]["body_preview"] == "굵게"
    )
    assert client.post("/naver-mailbox/send/confirm", json={"token": prep.json()["token"]}).status_code == 200
    assert "<script" not in sent[0].html and sent[0].html.startswith("<p><b>굵게</b>")


# ── 서비스: 보내기 2단계 ────────────────────────────────────────────────


@pytest.fixture
def sent(monkeypatch):
    service._pending.clear()
    box = []
    monkeypatch.setattr(
        sender,
        "send_draft",
        lambda d, **k: box.append(d) or {"ok": True, "recipients": d.all_recipients, "refused": [], "attachments": []},
    )
    yield box
    service._pending.clear()


def test_prepare_sends_nothing_and_confirm_sends_exactly_once(sent):
    prepared = service.prepare_send("skyjwsin", to="a@example.com", subject="제목", body="본문", cc="b@example.com")
    assert (
        sent == [] and prepared["summary"]["to"] == ["a@example.com"] and prepared["summary"]["cc"] == ["b@example.com"]
    )
    assert service.confirm_send(prepared["token"])["ok"] and len(sent) == 1
    with pytest.raises(service.ServiceError, match="이미 처리"):
        service.confirm_send(prepared["token"])
    assert len(sent) == 1


def test_confirm_with_unknown_or_expired_token_fails(sent):
    with pytest.raises(service.ServiceError):
        service.confirm_send("nope")
    prepared = service.prepare_send("skyjwsin", to="a@example.com", subject="s", body="b")
    service._pending[prepared["token"]].expires_at = time.time() - 1
    with pytest.raises(service.ServiceError):
        service.confirm_send(prepared["token"])
    assert sent == []


def test_cancel_discards_the_pending_mail(sent):
    prepared = service.prepare_send("skyjwsin", to="a@example.com", subject="s", body="b")
    assert service.cancel_send(prepared["token"]) is True and service.cancel_send(prepared["token"]) is False
    with pytest.raises(service.ServiceError):
        service.confirm_send(prepared["token"])


def test_prepare_rejects_bad_input_and_unregistered_accounts(sent):
    with pytest.raises(service.ServiceError, match="등록되지"):
        service.prepare_send("nobody", to="a@example.com", subject="s", body="b")
    with pytest.raises(service.ServiceError):
        service.prepare_send("skyjwsin", to="bad", subject="s", body="b")
    with pytest.raises(service.ServiceError, match="형식"):
        service.prepare_send(
            "skyjwsin", to="a@example.com", subject="s", body="b", uploads=[att.Upload("x.exe", "", b"1")]
        )


def test_pending_capacity_is_limited(sent, monkeypatch):
    monkeypatch.setattr(service, "MAX_PENDING", 2)
    service.prepare_send("skyjwsin", to="a@example.com", subject="s", body="b")
    service.prepare_send("skyjwsin", to="a@example.com", subject="s", body="b")
    with pytest.raises(service.ServiceError, match="너무 많"):
        service.prepare_send("skyjwsin", to="a@example.com", subject="s", body="b")


def test_forward_pulls_original_attachments_on_the_server(sent, monkeypatch):
    calls = []

    def fake_get(account, folder, uid, index, **k):
        calls.append((folder, uid, index))
        return {"ok": True, "filename": "견적서.pdf", "content_type": "application/pdf", "data": b"PDF"}

    monkeypatch.setattr(service.mailbox, "get_attachment", fake_get)
    prepared = service.prepare_send(
        "skyjwsin",
        to="a@example.com",
        subject="Fwd: x",
        body="b",
        forward={"folder": "INBOX", "uid": 2, "indices": [0]},
    )
    assert calls == [("INBOX", 2, 0)] and prepared["summary"]["attachments"] == [{"filename": "견적서.pdf", "size": 3}]


# ── 라우터 ──────────────────────────────────────────────────────────────


@pytest.fixture
def api(sent):
    app = FastAPI()
    app.include_router(naver_mailbox_router)
    role = {"role": "owner"}
    app.dependency_overrides[get_current_user] = lambda: {"actor": "tester", "role": role["role"]}
    return TestClient(app), role


def test_router_requires_admin_role(api):
    client, role = api
    role["role"] = "viewer"
    assert client.get("/naver-mailbox/accounts").status_code == 403
    assert client.post("/naver-mailbox/send/confirm", json={"token": "x"}).status_code == 403


def test_router_maps_adapter_errors_to_http_status(api, monkeypatch):
    client, _ = api
    monkeypatch.setattr(
        service.mailbox, "list_messages", lambda *a, **k: {"ok": False, "error": "auth_failed", "message": "거부"}
    )
    assert client.get("/naver-mailbox/messages", params={"account": "skyjwsin"}).status_code == 502
    assert client.get("/naver-mailbox/messages", params={"account": "nobody"}).status_code == 400
    assert client.get("/naver-mailbox/messages", params={"account": "skyjwsin", "since": "13/13/13"}).status_code == 400


def test_attachment_download_headers_are_safe(api, monkeypatch):
    client, _ = api
    ok = {"ok": True, "filename": "견적서.pdf", "content_type": "application/pdf", "previewable": True, "data": b"PDF"}
    monkeypatch.setattr(service.mailbox, "get_attachment", lambda *a, **k: ok)
    params = {"account": "skyjwsin", "folder": "INBOX", "uid": 2, "index": 0}
    down = client.get("/naver-mailbox/attachment", params=params)
    assert down.headers["content-disposition"].startswith("attachment; filename*=UTF-8''")
    assert "%EA%B2%AC" in down.headers["content-disposition"] and down.headers["x-content-type-options"] == "nosniff"
    assert (
        down.headers["content-type"].startswith("application/octet-stream")
        and "sandbox" in down.headers["content-security-policy"]
    )
    view = client.get("/naver-mailbox/attachment", params={**params, "inline": 1})
    assert (
        view.headers["content-disposition"].startswith("inline") and view.headers["content-type"] == "application/pdf"
    )
    monkeypatch.setattr(
        service.mailbox, "get_attachment", lambda *a, **k: {**ok, "previewable": False, "content_type": "image/svg+xml"}
    )
    svg = client.get("/naver-mailbox/attachment", params={**params, "inline": 1})
    assert svg.headers["content-disposition"].startswith("attachment") and svg.headers["content-type"].startswith(
        "application/octet-stream"
    )


def test_send_flow_over_http_with_an_uploaded_file(api, sent):
    client, _ = api
    form = {"account": "skyjwsin", "to": "a@example.com", "subject": "제목", "body": "본문", "cc": "b@example.com"}
    prep = client.post(
        "/naver-mailbox/send/prepare", data=form, files=[("files", ("../보고서.pdf", b"PDFDATA", "application/pdf"))]
    )
    assert prep.status_code == 200 and sent == []
    summary = prep.json()["summary"]
    assert summary["attachments"] == [{"filename": "보고서.pdf", "size": 7}]
    done = client.post("/naver-mailbox/send/confirm", json={"token": prep.json()["token"]})
    assert done.status_code == 200 and len(sent) == 1 and sent[0].uploads[0].filename == "보고서.pdf"
    again = client.post("/naver-mailbox/send/confirm", json={"token": prep.json()["token"]})
    assert again.status_code == 400 and len(sent) == 1


def test_send_prepare_rejects_blocked_file_and_bad_forward_json(api):
    client, _ = api
    form = {"account": "skyjwsin", "to": "a@example.com", "subject": "s", "body": "b"}
    blocked = client.post(
        "/naver-mailbox/send/prepare", data=form, files=[("files", ("setup.exe", b"MZ", "application/octet-stream"))]
    )
    assert blocked.status_code == 400 and "형식" in blocked.json()["detail"]
    assert client.post("/naver-mailbox/send/prepare", data={**form, "forward": "{not json"}).status_code == 400


def test_flags_and_trash_endpoints(api, monkeypatch):
    client, _ = api
    monkeypatch.setattr(service.mailbox, "set_seen", lambda a, f, u, s, **k: {"ok": True, "seen": s})
    monkeypatch.setattr(
        service.mailbox,
        "move_to_trash",
        lambda a, f, u, **k: {"ok": False, "error": "already_in_trash", "message": "이미 휴지통"},
    )
    ref = {"account": "skyjwsin", "folder": "INBOX", "uid": 1}
    assert client.post("/naver-mailbox/flags", json={**ref, "seen": True}).json() == {"ok": True, "seen": True}
    assert client.post("/naver-mailbox/trash", json=ref).status_code == 400


def test_bulk_endpoints_accept_uid_or_uids_and_map_errors(api, monkeypatch):
    client, _ = api
    seen_args = []
    monkeypatch.setattr(
        service.mailbox,
        "move_messages",
        lambda a, f, u, d, **k: seen_args.append((f, u, d)) or {"ok": True, "moved_to": d, "count": len(u)},
    )
    ref = {"account": "skyjwsin", "folder": "INBOX"}
    assert client.post("/naver-mailbox/move", json={**ref, "uids": [1, 2], "dest": "SNS"}).json()["count"] == 2
    assert client.post("/naver-mailbox/move", json={**ref, "uid": 7, "dest": "SNS"}).status_code == 200
    assert seen_args == [("INBOX", [1, 2], "SNS"), ("INBOX", [7], "SNS")]
    monkeypatch.setattr(
        service.mailbox, "purge", lambda *a, **k: {"ok": False, "error": "not_purgeable", "message": "휴지통에서만"}
    )
    assert client.post("/naver-mailbox/purge", json={**ref, "uids": [1]}).status_code == 400
    monkeypatch.setattr(service.mailbox, "empty_folder", lambda a, f, **k: {"ok": True, "count": 3})
    assert client.post("/naver-mailbox/empty", json={**ref, "folder": "Junk"}).json() == {"ok": True, "count": 3}
    assert client.post("/naver-mailbox/empty", json={"account": "nobody", "folder": "Junk"}).status_code == 400


def test_bulk_endpoints_require_admin(api):
    client, role = api
    role["role"] = "viewer"
    for path in ("move", "purge", "empty", "trash", "flags"):
        assert (
            client.post(
                f"/naver-mailbox/{path}",
                json={"account": "skyjwsin", "folder": "Junk", "uids": [1], "dest": "x", "seen": True},
            ).status_code
            == 403
        )


def test_no_secret_or_password_is_exposed_by_accounts(api):
    client, _ = api
    body = client.get("/naver-mailbox/accounts").text
    assert PW not in body and not re.search(r"password|NAVER_MAIL_PW", body, re.I)
