"""메일 순차 대량 발송 서비스·예약 액션·AI 허용 목록 — 가짜 SMTP 만 사용(실제 메일 없음). 기준서 B2."""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfoNotFoundError

import pytest

from ai_orchestrator.connectors.naver_mail import bulk_policy as pol
from ai_orchestrator.connectors.naver_mail import bulk_service as service
from ai_orchestrator.connectors.naver_mail import bulk_store as store
from ai_orchestrator.connectors.naver_mail import draft_policy as draft_policy
from ai_orchestrator.server import mcp_server
from ai_orchestrator.services import scheduled_job_actions as actions


class FakeSmtp:
    """BulkSmtp 대용 — 보낸 Draft 를 모으고 미리 정한 결과를 돌려준다."""

    sent: list = []
    results: list = []

    def __init__(self, account):
        self.account = account

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return None

    def send(self, draft):
        FakeSmtp.sent.append(draft)
        return FakeSmtp.results.pop(0) if FakeSmtp.results else {"ok": True, "refused": []}


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "_DB_PATH", tmp_path / "bulk.db")
    monkeypatch.setattr(service, "_smtp", FakeSmtp)
    # 허용 시간대 판정이 시험 실행 시각에 좌우되지 않게 항상 낮 10시(현지)로 둔다
    fixed = datetime.now().astimezone().replace(hour=10, minute=0, second=0, microsecond=0)
    monkeypatch.setattr(service, "_now_local", lambda: fixed)
    monkeypatch.setattr(store, "_now", lambda: fixed.astimezone(UTC).isoformat(timespec="seconds"))
    monkeypatch.setattr(draft_policy, "allowed_attachment_dirs", lambda *_a, **_k: [tmp_path])
    FakeSmtp.sent, FakeSmtp.results = [], []
    return tmp_path


def _payload(n=3, **over):
    base = {
        "account": "skyjwsin",
        "kind": "transaction",
        "subject": "{업체명} 안내",
        "body": "{이름}님 안녕하세요",
        "recipients": [{"email": f"u{i}@example.com", "name": f"고객{i}", "company": f"회사{i}"} for i in range(n)],
        "interval_sec": 5,
    }
    base.update(over)
    return base


def _wait_idle(auth_id, timeout=15.0):
    end = time.time() + timeout
    while time.time() < end:
        if not service.status(auth_id)["running"]:
            return
        time.sleep(0.05)
    raise AssertionError("실행이 끝나지 않았습니다")


# ── 승인서 만들기 ────────────────────────────────────────────────────────


def test_create_masks_addresses_in_view_and_defaults(env):
    view = service.create(_payload(), user="t")
    assert view["approved"] is False
    assert view["recipient_count"] == 3
    assert "u0@example.com" not in str(view)
    assert view["recipients_preview"][0]["email"] == "u*@example.com"
    assert (view["max_per_day"], view["interval_sec"], view["allowed_start"], view["allowed_end"]) == (
        200,
        5,
        "09:00",
        "18:00",
    )


@pytest.mark.parametrize(
    ("over", "msg"),
    [
        ({"kind": "promo", "subject": "신제품", "body": "본문"}, "(광고)"),
        ({"kind": "other"}, "성격"),
        ({"subject": ""}, "제목과 본문"),
        ({"recipients": []}, "비어"),
        ({"recipients": [{"email": "bad"}]}, "형식"),
        ({"max_per_day": 99999}, "하루 상한"),
        ({"interval_sec": 1}, "발송 간격"),
        ({"allowed_start": "25:00"}, "HH:MM"),
        ({"account": "nobody"}, "등록되지 않은"),
    ],
)
def test_create_rejects_bad_input(env, over, msg):
    with pytest.raises(ValueError, match=msg):
        service.create(_payload(**over), user="t")


def test_duplicate_recipients_are_collapsed_and_promo_with_required_items_ok(env):
    p = _payload(kind="promo", subject="(광고) 신제품", body="본문\n수신거부는 회신 주세요")
    p["recipients"] = [{"email": "A@x.com"}, {"email": "a@x.com"}, {"email": "b@x.com"}]
    assert service.create(p, user="t")["recipient_count"] == 2


# ── 가져오기 ───────────────────────────────────────────────────────────


def test_import_csv_counts_invalid_duplicate_and_optout(env):
    store.add_opt_out("no@example.com")
    f = env / "list.csv"
    f.write_text(
        "업체명,이름,이메일\n가,김,a@example.com\n나,이,A@example.com\n다,박,bad\n라,최,no@example.com\n마,정,b@example.com\n",
        encoding="utf-8",
    )
    recipients, stats = service.import_recipients(str(f))
    assert [r["email"] for r in recipients] == ["a@example.com", "b@example.com"]
    assert recipients[0] == {"email": "a@example.com", "name": "김", "company": "가"}
    assert stats == {"rows": 5, "invalid": 1, "duplicate": 1, "opted_out": 1, "usable": 2}


def test_import_rejects_path_outside_allowed_dirs_and_missing_column(env, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside") / "x.csv"
    outside.write_text("이메일\na@example.com\n", encoding="utf-8")
    with pytest.raises(ValueError):
        service.import_recipients(str(outside))
    inside = env / "noemail.csv"
    inside.write_text("이름\n김\n", encoding="utf-8")
    with pytest.raises(ValueError, match="이메일"):
        service.import_recipients(str(inside))


# ── 시험 발송·승인 ─────────────────────────────────────────────────────


def test_live_approval_needs_self_test_and_self_test_sends_one_mail(env):
    a = service.create(_payload(), user="t")
    with pytest.raises(ValueError, match="시험 발송"):
        service.approve(a["id"], user="t", live=True)
    got = service.send_self_test(a["id"], "me@example.com")
    assert got == {"ok": True, "to": pol.mask_email("me@example.com")}
    assert len(FakeSmtp.sent) == 1
    assert FakeSmtp.sent[0].to == ["me@example.com"]
    assert FakeSmtp.sent[0].subject == "[시험] 회사0 안내"  # 첫 수신자 값으로 채움
    assert service.approve(a["id"], user="t", live=True)["live"] is True


def test_self_test_subject_does_not_double_the_test_mark(env):
    a = service.create(_payload(subject="[시험] {업체명} 안내"), user="t")
    service.send_self_test(a["id"], "me@example.com")
    assert FakeSmtp.sent[0].subject == "[시험] 회사0 안내"


def test_failed_self_test_does_not_unlock_live_approval(env):
    a = service.create(_payload(), user="t")
    FakeSmtp.results = [{"ok": False, "error": "send_failed", "message": "denied"}]
    with pytest.raises(ValueError, match="시험 발송에 실패"):
        service.send_self_test(a["id"], "me@example.com")
    with pytest.raises(ValueError, match="시험 발송"):
        service.approve(a["id"], user="t", live=True)


# ── 백그라운드 실행 ─────────────────────────────────────────────────────


def _live(env, n=3):
    a = service.create(_payload(n), user="t")
    service.send_self_test(a["id"], "me@example.com")
    FakeSmtp.sent.clear()
    service.approve(a["id"], user="t", live=True)
    return a["id"]


def test_start_runs_in_background_sequentially_and_reports_status(env, monkeypatch):
    monkeypatch.setattr("ai_orchestrator.connectors.naver_mail.bulk_workflow.time.sleep", lambda _s: None)
    auth_id = _live(env, 3)
    service.start(auth_id)
    _wait_idle(auth_id)
    st = service.status(auth_id)
    assert st["last"]["status"] == "done"
    assert st["last"]["summary"]["sent"] == 3
    assert st["counts"] == {"sent": 3}
    assert st["remaining"] == 0
    assert [d.to[0] for d in FakeSmtp.sent] == ["u0@example.com", "u1@example.com", "u2@example.com"]


def test_start_rejects_unapproved_revoked_paused_and_running(env):
    a = service.create(_payload(), user="t")
    with pytest.raises(ValueError, match="승인되지 않은"):
        service.start(a["id"])
    auth_id = _live(env, 2)
    service.pause(auth_id)
    with pytest.raises(ValueError, match="멈춘"):
        service.start(auth_id)
    service.resume(auth_id)
    service.revoke(auth_id, user="t")
    with pytest.raises(ValueError, match="취소"):
        service.start(auth_id)


def test_dry_run_authorization_never_uses_smtp(env, monkeypatch):
    monkeypatch.setattr("ai_orchestrator.connectors.naver_mail.bulk_workflow.time.sleep", lambda _s: None)
    a = service.create(_payload(2), user="t")
    service.approve(a["id"], user="t", live=False)
    service.start(a["id"])
    _wait_idle(a["id"])
    assert FakeSmtp.sent == []
    assert service.status(a["id"])["counts"] == {"dry_run": 2}


def test_send_log_masks_addresses(env, monkeypatch):
    monkeypatch.setattr("ai_orchestrator.connectors.naver_mail.bulk_workflow.time.sleep", lambda _s: None)
    auth_id = _live(env, 2)
    service.start(auth_id)
    _wait_idle(auth_id)
    assert "u0@example.com" not in str(service.send_log(auth_id))


# ── 예약 작업 액션 ─────────────────────────────────────────────────────


def test_scheduled_action_validates_and_starts(env, monkeypatch):
    spec = actions.get_action("naver_mail_bulk_send")
    assert spec is not None
    assert spec.risk_action == "mail_send_authorized"
    with pytest.raises(ValueError, match="알 수 없는"):
        spec.validate({"authorization_id": "x", "to": "a@b.com"})
    with pytest.raises(ValueError, match="찾을 수 없"):
        spec.validate({"authorization_id": "0" * 32})
    a = service.create(_payload(), user="t")
    with pytest.raises(ValueError, match="승인되지 않았"):
        spec.validate({"authorization_id": a["id"]})
    service.approve(a["id"], user="t", live=False)
    params = spec.validate({"authorization_id": a["id"]})
    monkeypatch.setattr("ai_orchestrator.connectors.naver_mail.bulk_workflow.time.sleep", lambda _s: None)
    assert "시작" in spec.run(params)
    _wait_idle(a["id"])


# ── AI 에게는 열지 않는다 ─────────────────────────────────────────────


def test_ai_registry_has_no_bulk_mail_paths():
    text = " ".join(f"{v.get('path', '')} {v.get('method', '')}" for v in mcp_server.API_REGISTRY.values())
    assert "mail-bulk" not in text


# ── 한국 시간 ─────────────────────────────────────────────────────────


def test_korea_time_is_utc_plus_9_regardless_of_pc_timezone():
    assert datetime.now(service.KST).utcoffset() == timedelta(hours=9)
    # 허용 시간대(09~18)는 이 시각의 시·분으로 판정한다 — UTC 02:00 은 한국 11:00 이다
    kst_11 = datetime(2026, 10, 5, 2, 0, tzinfo=UTC).astimezone(service.KST)
    assert kst_11.hour == 11


def test_korea_tz_falls_back_to_fixed_offset_without_tzdata(monkeypatch):
    def missing(_name):
        raise ZoneInfoNotFoundError("no tzdata")

    monkeypatch.setattr(service, "ZoneInfo", missing)
    tz = service._korea_tz()
    assert datetime(2026, 10, 5, 2, 0, tzinfo=UTC).astimezone(tz).hour == 11
