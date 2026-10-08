"""메일 AI 초안 — 정책(mail_draft_policy)과 저장소(naver_mail_draft_store). 네트워크·실제 메일함을 쓰지 않는다."""

from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ai_orchestrator.connectors.naver_mail import draft_policy as pol
from ai_orchestrator.connectors.naver_mail import draft_store as store


@pytest.fixture(autouse=True)
def _db(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "_DB_PATH", tmp_path / "drafts.db")


# ── 정책: 상태 전이·한도 ────────────────────────────────────────────────


def test_state_machine_allows_only_the_intended_paths():
    assert pol.can_transition(pol.PENDING, pol.SENDING)
    assert (
        pol.can_transition(pol.SENDING, pol.SENT)
        and pol.can_transition(pol.SENDING, pol.UNKNOWN)
        and pol.can_transition(pol.SENDING, pol.FAILED)
    )
    assert pol.can_transition(pol.FAILED, pol.SENDING)  # 명확한 실패는 사람이 다시 눌러 재시도할 수 있다
    for terminal in (pol.SENT, pol.UNKNOWN, pol.CANCELLED, pol.EXPIRED):
        assert not any(pol.can_transition(terminal, t) for t in pol.STATUSES)  # 끝난 상태는 되돌릴 수 없다
    assert not pol.can_transition(pol.PENDING, pol.SENT)  # 전송 중을 거치지 않고 '보냄'이 될 수 없다
    assert not pol.can_transition(pol.UNKNOWN, pol.SENDING)  # 결과가 불확실하면 자동 재전송 금지


def test_create_limits():
    assert pol.check_create(pending_count=0, recipient_count=1).allowed
    assert not pol.check_create(pending_count=0, recipient_count=0).allowed
    assert not pol.check_create(pending_count=0, recipient_count=pol.MAX_RECIPIENTS + 1).allowed
    assert not pol.check_create(pending_count=pol.MAX_PENDING_DRAFTS, recipient_count=1).allowed
    assert not pol.check_create(pending_count=0, recipient_count=1, attachment_count=pol.MAX_ATTACH_FILES + 1).allowed


def test_send_decision_covers_status_expiry_and_daily_cap():
    assert pol.check_send(status=pol.PENDING, expired=False, sent_today=0, cap=5).allowed
    assert pol.check_send(status=pol.FAILED, expired=False, sent_today=4, cap=5).allowed
    assert "상한" in pol.check_send(status=pol.PENDING, expired=False, sent_today=5, cap=5).reason
    assert "만료" in pol.check_send(status=pol.PENDING, expired=True, sent_today=0, cap=5).reason
    assert "이미 보낸" in pol.check_send(status=pol.SENT, expired=False, sent_today=0, cap=5).reason
    assert "불확실" in pol.check_send(status=pol.UNKNOWN, expired=False, sent_today=0, cap=5).reason
    for status in (pol.SENDING, pol.CANCELLED, pol.EXPIRED):
        assert not pol.check_send(status=status, expired=False, sent_today=0, cap=5).allowed


def test_daily_cap_comes_from_env_and_is_clamped(monkeypatch):
    assert pol.daily_cap() == pol.DEFAULT_DAILY_SEND_CAP
    monkeypatch.setenv("HAEHAN_MAIL_DAILY_CAP", "7")
    assert pol.daily_cap() == 7
    monkeypatch.setenv("HAEHAN_MAIL_DAILY_CAP", "999999")
    assert pol.daily_cap() == 1000
    monkeypatch.setenv("HAEHAN_MAIL_DAILY_CAP", "abc")
    assert pol.daily_cap() == pol.DEFAULT_DAILY_SEND_CAP


# ── 정책: 첨부 경로 안전 ────────────────────────────────────────────────


@pytest.fixture
def home(tmp_path):
    h = tmp_path / "home"
    for name in ("Documents", "Downloads", "Desktop"):
        (h / name).mkdir(parents=True)
    return h


def _file(path: Path, data: bytes = b"hello") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def test_normal_files_in_allowed_folders_are_accepted(home):
    allowed = pol.allowed_attachment_dirs(home, extra_env="")
    f = _file(home / "Documents" / "견적서.pdf")
    assert pol.validate_attachment_path(str(f), allowed_dirs=allowed) == f.resolve()
    assert pol.validate_attachment_path(str(_file(home / "Downloads" / "sub" / "도면.dwg")), allowed_dirs=allowed)


def test_files_outside_the_allowed_folders_are_rejected(home, tmp_path):
    allowed = pol.allowed_attachment_dirs(home, extra_env="")
    outside = _file(tmp_path / "elsewhere" / "a.pdf")
    with pytest.raises(pol.PathRejected, match="허용된 폴더"):
        pol.validate_attachment_path(str(outside), allowed_dirs=allowed)


@pytest.mark.parametrize("raw", ["", "상대/경로.pdf", "C:\\없는폴더\\없는파일.pdf"])
def test_relative_empty_or_missing_paths_are_rejected(home, raw):
    with pytest.raises(pol.PathRejected):
        pol.validate_attachment_path(raw, allowed_dirs=pol.allowed_attachment_dirs(home, extra_env=""))


def test_nul_byte_and_directories_are_rejected(home):
    allowed = pol.allowed_attachment_dirs(home, extra_env="")
    with pytest.raises(pol.PathRejected):
        pol.validate_attachment_path("C:\\a\x00b.pdf", allowed_dirs=allowed)
    with pytest.raises(pol.PathRejected, match="파일이 아닙니다"):
        pol.validate_attachment_path(str(home / "Documents"), allowed_dirs=allowed)


@pytest.mark.parametrize(
    "relative",
    [
        ".env",
        "계정 비밀번호.txt",
        "secret_notes.txt",
        "id_rsa",
        "client_secret.json",
        "token.json",
        "my.pem",
        "store.sqlite",
        "vault.kdbx",
        ".git/config",
        "AppData/x.pdf",
        "_backup_cred/a.pdf",
        "secrets/a.pdf",
    ],
)
def test_secret_looking_files_and_sensitive_folders_are_rejected(home, relative):
    allowed = pol.allowed_attachment_dirs(home, extra_env="")
    f = _file(home / "Documents" / relative)
    with pytest.raises(pol.PathRejected):
        pol.validate_attachment_path(str(f), allowed_dirs=allowed)


def test_app_internal_folders_are_rejected_even_when_inside_an_allowed_folder(home):
    allowed = pol.allowed_attachment_dirs(home, extra_env="")
    f = _file(home / "Documents" / "project" / "config.json")
    with pytest.raises(pol.PathRejected, match="앱 내부"):
        pol.validate_attachment_path(str(f), allowed_dirs=allowed, deny_roots=[home / "Documents" / "project"])


def test_symlink_escape_is_blocked(home, tmp_path):
    target = _file(tmp_path / "outside" / "private.pdf")
    link = home / "Documents" / "link.pdf"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("이 환경에서는 심볼릭 링크를 만들 수 없다")
    with pytest.raises(pol.PathRejected, match="허용된 폴더"):
        pol.validate_attachment_path(str(link), allowed_dirs=pol.allowed_attachment_dirs(home, extra_env=""))


def test_size_rules(home, monkeypatch):
    allowed = pol.allowed_attachment_dirs(home, extra_env="")
    with pytest.raises(pol.PathRejected, match="빈 파일"):
        pol.validate_attachment_path(str(_file(home / "Documents" / "empty.txt", b"")), allowed_dirs=allowed)
    monkeypatch.setattr(pol, "MAX_ATTACH_BYTES", 3)
    with pytest.raises(pol.PathRejected, match="MB"):
        pol.validate_attachment_path(str(_file(home / "Documents" / "big.txt", b"12345")), allowed_dirs=allowed)


def test_extra_allowed_folders_come_from_the_environment(home, tmp_path):
    shared = tmp_path / "shared"
    shared.mkdir()
    dirs = pol.allowed_attachment_dirs(home, extra_env=str(shared))
    assert shared in dirs
    assert pol.validate_attachment_path(str(_file(shared / "a.pdf")), allowed_dirs=dirs)


# ── 저장소 ──────────────────────────────────────────────────────────────


def _draft(**over):
    base = {"to": ["a@example.com"], "subject": "제목", "body_text": "본문"}
    return store.create_draft("skyjwsin", **{**base, **over})


def test_create_and_read_back_all_fields():
    d = _draft(
        cc=["b@example.com"],
        bcc=["c@example.com"],
        body_html="<p>본문</p>",
        attachments=[{"kind": "path", "name": "a.pdf", "size": 3}],
        in_reply_to="<x@y>",
        references="<w@z> <x@y>",
    )
    got = store.get_draft(d["id"])
    assert got["status"] == pol.PENDING and got["created_by"] == "ai" and len(got["id"]) == 32
    assert got["to"] == ["a@example.com"] and got["cc"] == ["b@example.com"] and got["bcc"] == ["c@example.com"]
    assert (
        got["attachments"][0]["name"] == "a.pdf"
        and got["in_reply_to"] == "<x@y>"
        and got["references"] == "<w@z> <x@y>"
    )
    assert got["result"] == {} and store.get_draft("0" * 32) is None


def test_listing_filters_by_account_and_status():
    a = _draft()
    store.create_draft("other", to=["z@example.com"], subject="s", body_text="b")
    assert [d["id"] for d in store.list_drafts("skyjwsin")] == [a["id"]]
    assert len(store.list_drafts()) == 2
    assert store.list_drafts("skyjwsin", statuses=(pol.SENT,)) == []
    assert store.count_pending("skyjwsin") == 1


def test_only_one_of_two_concurrent_sends_wins():
    d = _draft()
    wins = []

    def attempt():
        wins.append(
            store.transition(
                d["id"],
                pol.SENDING,
                only_from=pol.OPEN_STATUSES,
                approved_by="owner",
                approved_at="2026-10-02T00:00:00+00:00",
            )
        )

    threads = [threading.Thread(target=attempt) for _ in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert wins.count(True) == 1 and store.get_draft(d["id"])["status"] == pol.SENDING


def test_invalid_transitions_are_refused_and_nothing_changes():
    d = _draft()
    assert not store.transition(d["id"], pol.SENT, only_from=(pol.PENDING,))  # 전송 중을 건너뛸 수 없다
    assert store.get_draft(d["id"])["status"] == pol.PENDING
    assert store.transition(d["id"], pol.CANCELLED, only_from=(pol.PENDING,))
    assert not store.transition(
        d["id"], pol.SENDING, only_from=(pol.PENDING, pol.CANCELLED)
    )  # 취소된 초안은 보낼 수 없다


def test_result_and_sent_time_are_recorded_with_the_transition():
    d = _draft()
    store.transition(d["id"], pol.SENDING, only_from=(pol.PENDING,))
    assert store.transition(
        d["id"],
        pol.SENT,
        only_from=(pol.SENDING,),
        sent_at="2026-10-02T01:00:00+00:00",
        result={"ok": True, "recipients": 1},
    )
    got = store.get_draft(d["id"])
    assert (
        got["status"] == pol.SENT
        and got["sent_at"] == "2026-10-02T01:00:00+00:00"
        and got["result"] == {"ok": True, "recipients": 1}
    )


def test_unknown_field_names_cannot_be_injected_into_the_update():
    d = _draft()
    with pytest.raises(KeyError):
        store.transition(d["id"], pol.SENDING, only_from=(pol.PENDING,), **{"status = 'sent', subject": "x"})
    assert store.get_draft(d["id"])["status"] == pol.PENDING


def test_old_drafts_expire_but_finished_ones_do_not(monkeypatch):
    old, finished = _draft(), _draft()
    store.transition(finished["id"], pol.SENDING, only_from=(pol.PENDING,))
    store.transition(finished["id"], pol.SENT, only_from=(pol.SENDING,))
    future = datetime.now(UTC) + timedelta(days=pol.DRAFT_TTL_DAYS + 1)

    class Later(datetime):
        @classmethod
        def now(cls, tz=None):
            return future if tz else future.replace(tzinfo=None)

    monkeypatch.setattr(store, "datetime", Later)
    assert store.is_expired(store.get_draft(old["id"]))
    assert store.expire_old() == 1
    assert store.get_draft(old["id"])["status"] == pol.EXPIRED and store.get_draft(finished["id"])["status"] == pol.SENT


def test_daily_counter_accumulates_per_account_and_day(monkeypatch):
    assert store.sent_today("skyjwsin") == 0
    store.add_sent("skyjwsin")
    store.add_sent("skyjwsin", 2)
    store.add_sent("other")
    assert store.sent_today("skyjwsin") == 3 and store.sent_today("other") == 1
    monkeypatch.setattr(store, "today", lambda: "2099-01-01")
    assert store.sent_today("skyjwsin") == 0  # 날짜가 바뀌면 새로 센다


def test_instructions_are_saved_per_account_and_replaced():
    assert store.get_instructions("skyjwsin") == ""
    store.set_instructions("skyjwsin", "서명은 신재우")
    store.set_instructions("skyjwsin", "서명은 해한 AI")
    store.set_instructions("other", "다른 계정")
    assert store.get_instructions("skyjwsin") == "서명은 해한 AI" and store.get_instructions("other") == "다른 계정"


def test_audit_events_never_contain_recipient_addresses():
    d = _draft(to=["secret.person@example.com"])
    store.transition(d["id"], pol.CANCELLED, only_from=(pol.PENDING,))
    log = store.events(d["id"])
    assert [e["event"] for e in log] == ["created", "status:cancelled"]
    assert "secret.person" not in str(log) and "recipients=1" in log[0]["detail"]


def test_schema_is_versioned_and_reopening_is_safe():
    _draft()
    import sqlite3

    with sqlite3.connect(str(store._DB_PATH)) as con:
        assert con.execute("PRAGMA user_version").fetchone()[0] == len(store._SCHEMA_STEPS)
    assert len(store.list_drafts()) == 1  # 다시 열어도(스키마 재적용) 데이터가 그대로
