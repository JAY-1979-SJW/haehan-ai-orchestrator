"""NAVER-MAIL-BODY-PIPELINE-V2-01 — 필수 10+ 테스트."""

from __future__ import annotations

import json

from scripts.naver.mail import (
    body_pipeline_v2 as bp,
)
from scripts.naver.mail import (
    pii_mask,
)
from scripts.naver.mail import (
    unread_audit as ua,
)
from scripts.naver.mail.processing import audit_naver_mail_body_pipeline_v2 as audit

# ── PII 마스킹 ──────────────────────────────────────────────────────


def test_pii_mask_email_localpart():
    r = pii_mask.mask("contact: user@example.com here")
    assert "user@example.com" not in r.masked_text
    assert "@example.com" in r.masked_text
    assert r.types.get("EMAIL", 0) >= 1


def test_pii_mask_card_phone_rrn_biz():
    text = "카드 1234 5678 9012 3456, 전화 010-1234-5678, 주민 123456-1234567, 사업자 123-45-67890"
    r = pii_mask.mask(text)
    # 카드는 양쪽 4자리만 노출
    assert "5678 9012" not in r.masked_text
    assert "[RRN_MASKED]" in r.masked_text
    assert "[BIZREG_MASKED]" in r.masked_text
    assert "010-****-****" in r.masked_text
    assert r.detected_count >= 4


def test_pii_mask_long_number_account():
    r = pii_mask.mask("주문번호 1234567890123 / 계좌 110-123-456789")
    assert "1234567890123" not in r.masked_text
    assert "[NUMBER_MASKED]" in r.masked_text or "[ACCOUNT_MASKED]" in r.masked_text


def test_pii_mask_address_korean():
    r = pii_mask.mask("배송지 서울특별시 송파구 송파대로 570")
    assert "[ADDRESS_MASKED]" in r.masked_text


def test_pii_mask_label_value():
    r = pii_mask.mask("이름: 홍길동\n비밀번호: secret123")
    assert "홍길동" not in r.masked_text
    assert "secret123" not in r.masked_text
    assert "[VALUE_MASKED]" in r.masked_text


def test_pii_mask_otp_code():
    r = pii_mask.mask("인증번호 987654 입력")
    assert "987654" not in r.masked_text
    assert "[CODE_MASKED]" in r.masked_text


def test_pii_mask_hash_consistent():
    a = pii_mask.mask("abc 010-1234-5678")
    b = pii_mask.mask("abc 010-1234-5678")
    assert a.masked_text_hash == b.masked_text_hash
    assert len(a.masked_text_hash) == 16


def test_pii_mask_assert_no_raw_leak():
    raw_email = "user@example.com"
    raw_phone = "010-1234-5678"
    text = f"안녕 {raw_email} {raw_phone}"
    r = pii_mask.mask(text)
    leaks = pii_mask.assert_no_raw_pii(r.masked_text, original_samples=[raw_email, raw_phone])
    assert leaks == []


def test_pii_mask_empty_safe():
    r = pii_mask.mask("")
    assert r.masked_text == ""
    assert r.detected_count == 0
    assert r.masked_text_hash == ""


# ── unread_audit ────────────────────────────────────────────────────


class _FakeUnreadActions:
    def __init__(self):
        # sn -> state in unread list ("UNREAD", "READ", "NOT_IN_UNREAD_LIST")
        self.unread_state = {"100": "UNREAD", "101": "UNREAD"}
        self.body_unread_button_clickable = True
        self.last_navigated = ""

    def evaluate(self, expr):
        # state lookup
        if "li.mail-" in expr and "aria-pressed" in expr:
            import re

            m = re.search(r"li\.mail-(\d+)", expr)
            if m:
                sn = m.group(1)
                state = self.unread_state.get(sn, "NOT_IN_UNREAD_LIST")
                return state
            return "NOT_IN_UNREAD_LIST"
        # body button click
        if "button_task.svg_unread" in expr or "svg_unread" in expr:
            if self.body_unread_button_clickable:
                # mark current opened sn back to UNREAD
                if self._current_open_sn:
                    self.unread_state[self._current_open_sn] = "UNREAD"
                return "clicked"
            return "no_button"
        # body extraction
        if "JSON.stringify" in expr and "header" in expr and "body" in expr:
            return {
                "href": "",
                "title": "T",
                "header": {"subject": "s", "sender_name": "n", "sender_addr": "", "date": "d"},
                "body": "본문 010-1111-2222",
                "body_len": 12,
                "links": [],
                "img_count": 0,
                "has_attach": False,
                "attach_names": [],
            }
        return None

    def navigate(self, url):
        self.last_navigated = url
        # opening body view marks as read
        import re

        m = re.search(r"/popup/read/\d+/(\d+)", url)
        if m:
            sn = m.group(1)
            self._current_open_sn = sn
            self.unread_state[sn] = "READ"
        elif "/unread" in url:
            self._current_open_sn = None

    _current_open_sn = None

    def wait_dom(self, expr, timeout_s=8.0):
        return True


def test_unread_audit_state_change_detected_and_restored():
    fa = _FakeUnreadActions()
    snap = ua.snapshot_mail(fa, "100", folder_id="0")
    assert snap.before_state == ua.STATE_UNREAD
    ua.open_body_and_audit_state(fa, snap, folder_id="0")
    # 본문 진입 → read
    assert fa.unread_state["100"] == "READ"
    ua.restore_unread_state(fa, snap, folder_id="0")
    assert snap.after_restore_state == ua.STATE_UNREAD
    assert snap.restore_ok is True
    assert snap.state_changed_on_open is True


def test_unread_audit_restore_failure_recorded():
    fa = _FakeUnreadActions()
    fa.body_unread_button_clickable = False  # 복구 버튼 없음
    snap = ua.snapshot_mail(fa, "101", folder_id="0")
    ua.open_body_and_audit_state(fa, snap, folder_id="0")
    ua.restore_unread_state(fa, snap, folder_id="0")
    assert snap.restore_attempted is True
    assert snap.restore_ok is False


# ── body_pipeline_v2 ────────────────────────────────────────────────


def test_pipeline_dry_run_default_no_body_open():
    fa = _FakeUnreadActions()
    targets = [bp.TargetMail(sn="100", folder_id="0", folder_name="받은메일함")]
    rpt = bp.run(fa, targets, mode=bp.MODE_DRY_RUN, max_bodies=5)
    assert rpt.attempt_count == 0
    assert len(rpt.bodies) == 0
    assert fa.last_navigated == ""  # navigate 호출 없음


def test_pipeline_full_read_with_restore():
    fa = _FakeUnreadActions()
    targets = [bp.TargetMail(sn="100", folder_id="0", folder_name="받은메일함")]
    rpt = bp.run(fa, targets, mode=bp.MODE_FULL_READ, max_bodies=1)
    assert rpt.attempt_count == 1
    assert rpt.success_count == 1
    b = rpt.bodies[0]
    assert b.open_ok is True
    # PII 마스킹 — body 안 전화번호가 마스킹됨
    assert "010-1111-2222" not in b.body_redacted
    assert b.masked_text_hash != ""
    # raw body 필드 없음
    assert "body_raw" not in b.to_dict() and "raw_body" not in b.to_dict()
    # 상태 복구 OK
    ua_ = rpt.unread_audit
    assert ua_["restore_succeeded"] == 1
    assert ua_["restore_failed"] == 0


def test_pipeline_report_has_no_raw_body_field():
    fa = _FakeUnreadActions()
    targets = [bp.TargetMail(sn="100", folder_id="0", folder_name="받은메일함")]
    rpt = bp.run(fa, targets, mode=bp.MODE_FULL_READ, max_bodies=1)
    j = json.dumps(rpt.to_dict(), ensure_ascii=False)
    # 원본 본문 leak 없음
    assert "010-1111-2222" not in j
    # raw_body / body_raw 키 없음
    assert '"raw_body"' not in j
    assert '"body_raw"' not in j


def test_pipeline_attachment_download_count_zero():
    fa = _FakeUnreadActions()
    targets = [bp.TargetMail(sn="100", folder_id="0", folder_name="받은메일함")]
    rpt = bp.run(fa, targets, mode=bp.MODE_FULL_READ, max_bodies=1)
    assert rpt.attachment_download_count == 0


def test_pipeline_external_ai_call_count_zero():
    fa = _FakeUnreadActions()
    targets = [bp.TargetMail(sn="100", folder_id="0", folder_name="받은메일함")]
    rpt = bp.run(fa, targets, mode=bp.MODE_FULL_READ, max_bodies=1)
    assert rpt.external_ai_call_count == 0


# ── audit verdicts ──────────────────────────────────────────────────


def test_audit_pass_when_clean():
    fa = _FakeUnreadActions()
    targets = [bp.TargetMail(sn="100", folder_id="0", folder_name="받은메일함")]
    rpt = bp.run(fa, targets, mode=bp.MODE_FULL_READ, max_bodies=1)
    v = audit.judge(rpt)
    assert v.code == "PASS_NAVER_MAIL_BODY_PIPELINE_V2", v.reasons


def test_audit_fail_raw_body_leak():
    rpt = bp.PipelineReport(
        run_id="x",
        started_at_iso="",
        ended_at_iso="",
        mode="FULL_READ",
        raw_body_leak_check={"raw_body_field_present_in_records": True},
    )
    v = audit.judge(rpt)
    assert v.code == "FAIL_RAW_BODY_LEAK"


def test_audit_fail_attachment_downloaded():
    rpt = bp.PipelineReport(
        run_id="x",
        started_at_iso="",
        ended_at_iso="",
        mode="FULL_READ",
        attachment_download_count=2,
    )
    v = audit.judge(rpt)
    assert v.code == "FAIL_ATTACHMENT_DOWNLOADED"


def test_audit_fail_external_ai_call_via_network_log():
    rpt = bp.PipelineReport(
        run_id="x",
        started_at_iso="",
        ended_at_iso="",
        mode="FULL_READ",
    )
    v = audit.judge(rpt, network_log=["POST https://api.anthropic.com/v1/messages"])
    assert v.code == "FAIL_EXTERNAL_AI_CALL_USED"


def test_audit_warn_unread_restore_unverified():
    rpt = bp.PipelineReport(
        run_id="x",
        started_at_iso="",
        ended_at_iso="",
        mode="FULL_READ",
        unread_audit={"state_changed": 1, "restore_attempted": 1, "restore_succeeded": 0, "restore_failed": 1},
    )
    v = audit.judge(rpt)
    assert v.code == "WARN_UNREAD_RESTORE_UNVERIFIED"


def test_audit_warn_partial_body_read():
    rpt = bp.PipelineReport(
        run_id="x",
        started_at_iso="",
        ended_at_iso="",
        mode="FULL_READ",
        attempt_count=3,
        success_count=2,
        failure_count=1,
        unread_audit={"state_changed": 0, "restore_succeeded": 0, "restore_attempted": 0, "restore_failed": 0},
    )
    v = audit.judge(rpt)
    assert v.code == "WARN_PARTIAL_BODY_READ"


# ── 회귀 가드 ───────────────────────────────────────────────────────


def test_regression_smart_folder_coverage_still_imports():
    """smart_folder_collector import 가 깨지지 않음 — 회귀 가드."""
    from scripts.naver.mail import smart_folder_collector as sfc

    assert hasattr(sfc, "collect_all")


def test_regression_dynamic_folder_discovery_imports():
    from scripts.naver.mail import folder_discovery as fd
    from scripts.naver.mail import folder_profile as fpr

    assert hasattr(fd, "discover_folders")
    assert hasattr(fpr, "build_snapshot")
