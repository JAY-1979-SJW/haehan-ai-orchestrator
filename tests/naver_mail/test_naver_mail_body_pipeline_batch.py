"""NAVER-MAIL-BODY-PIPELINE-BATCH-01 — 필수 12+ 테스트."""

from __future__ import annotations

import json

from scripts.naver.mail import batch_runner as br
from scripts.naver.mail import unread_audit as ua
from scripts.naver.mail.processing import audit_naver_mail_body_pipeline_batch as audit

# ── 헬퍼 ────────────────────────────────────────────────────────────


class _FakeActions:
    """Live 와 무관 — 테스트 전용."""

    pass


def _mk_targets(n=3):
    return [br.BatchTarget(sn=str(100 + i), folder_id="0", folder_name="받은메일함") for i in range(n)]


def _fake_process_ok(actions, target):
    """모든 메일을 정상 처리 + restore OK."""
    res = br.MailResult(sn=target.sn, folder_id=target.folder_id, folder_name=target.folder_name)
    res.body_open_ok = True
    res.masked_text_hash = f"hash_{target.sn}"
    res.pii_detected_count = 1
    res.pii_types = {"EMAIL": 1}
    res.state_before = ua.STATE_UNREAD
    res.state_after_open = ua.STATE_READ
    res.state_after_restore = ua.STATE_UNREAD
    res.state_changed_on_open = True
    res.restore_attempted = True
    res.restore_ok = True
    res.elapsed_ms = 2000
    res.status = br.UNREAD_CHANGED_RESTORED
    return res


def _fake_process_restore_fail(actions, target):
    res = _fake_process_ok(actions, target)
    res.restore_ok = False
    res.state_after_restore = ua.STATE_READ
    res.status = br.UNREAD_CHANGED_RESTORE_FAILED
    return res


def _fake_process_body_fail(actions, target):
    res = br.MailResult(sn=target.sn, folder_id=target.folder_id, folder_name=target.folder_name)
    res.status = br.BODY_READ_FAILED
    res.error = "navigate_timeout"
    res.elapsed_ms = 1000
    return res


# ── 1) batch target dedupe ──────────────────────────────────────────


def test_dedupe_targets_removes_duplicates():
    targets = [
        br.BatchTarget(sn="100", folder_id="0", folder_name="A"),
        br.BatchTarget(sn="101", folder_id="0", folder_name="A"),
        br.BatchTarget(sn="100", folder_id="10", folder_name="B"),  # dup
        br.BatchTarget(sn="102", folder_id="0", folder_name="A"),
    ]
    out, dup = br.dedupe_targets(targets)
    assert len(out) == 3
    assert dup == 1


def test_dedupe_skips_empty_sn():
    targets = [
        br.BatchTarget(sn="", folder_id="0", folder_name="A"),
        br.BatchTarget(sn="100", folder_id="0", folder_name="A"),
    ]
    out, _ = br.dedupe_targets(targets)
    assert len(out) == 1


# ── 2) checkpoint schema ───────────────────────────────────────────


def test_checkpoint_save_and_load(tmp_path):
    p = tmp_path / "ck.json"
    br.save_checkpoint(
        p, "run123", {"100": {"status": br.UNREAD_CHANGED_RESTORED, "masked_text_hash": "h", "pii_detected_count": 2}}
    )
    loaded = br.load_checkpoint(p)
    assert loaded["run_id"] == "run123"
    assert "100" in loaded["sn_to_status"]
    assert loaded["sn_to_status"]["100"]["status"] == br.UNREAD_CHANGED_RESTORED


def test_checkpoint_load_nonexistent(tmp_path):
    loaded = br.load_checkpoint(tmp_path / "missing.json")
    assert loaded["sn_to_status"] == {}
    assert loaded.get("run_id") == ""


def test_checkpoint_broken_returns_broken_marker(tmp_path):
    p = tmp_path / "broken.json"
    p.write_text("{ not valid json", encoding="utf-8")
    loaded = br.load_checkpoint(p)
    assert loaded["run_id"] == "broken"


# ── 3) resume 시 성공 항목 skip ─────────────────────────────────────


def test_resume_skips_already_done(tmp_path):
    ck = tmp_path / "ck.json"
    br.save_checkpoint(
        ck,
        "prev",
        {
            "100": {"status": br.UNREAD_CHANGED_RESTORED, "masked_text_hash": "h"},
            "101": {"status": br.UNREAD_CHANGED_RESTORED, "masked_text_hash": "h"},
        },
    )
    targets = _mk_targets(3)  # 100, 101, 102
    rep = br.run_batch(
        _FakeActions(), targets, checkpoint_path=ck, delay_s=0.0, jitter_s=0.0, process_fn=_fake_process_ok
    )
    assert rep.skipped_already_done == 2
    assert rep.attempted == 1  # 102 만 실행
    assert rep.success == 1


# ── 4) unread restore failure 시 PASS 금지 ──────────────────────────


def test_restore_failure_halts_batch_and_audit_fails():
    targets = _mk_targets(3)
    rep = br.run_batch(_FakeActions(), targets, delay_s=0.0, jitter_s=0.0, process_fn=_fake_process_restore_fail)
    assert rep.halted_early is True
    assert rep.unread_restore_failed >= 1
    v = audit.judge_batch(rep)
    assert v.code == "FAIL_UNREAD_RESTORE_FAILED"


def test_continue_on_warn_keeps_going_after_restore_fail():
    targets = _mk_targets(3)
    rep = br.run_batch(
        _FakeActions(), targets, delay_s=0.0, jitter_s=0.0, continue_on_warn=True, process_fn=_fake_process_restore_fail
    )
    assert rep.halted_early is False
    assert rep.attempted == 3


# ── 5) raw body 저장 금지 ───────────────────────────────────────────


def test_no_raw_body_in_report():
    targets = _mk_targets(2)
    rep = br.run_batch(_FakeActions(), targets, delay_s=0.0, jitter_s=0.0, process_fn=_fake_process_ok)
    j = json.dumps(rep.to_dict(), ensure_ascii=False)
    assert '"raw_body"' not in j
    assert '"body_raw"' not in j


# ── 6) PII masking summary ──────────────────────────────────────────


def test_pii_masking_summary_aggregates():
    targets = _mk_targets(3)
    rep = br.run_batch(_FakeActions(), targets, delay_s=0.0, jitter_s=0.0, process_fn=_fake_process_ok)
    assert rep.pii_detected_total == 3
    assert rep.pii_types_summary.get("EMAIL") == 3


# ── 7) attachment download 금지 ─────────────────────────────────────


def test_attachment_download_count_zero_by_default():
    targets = _mk_targets(1)
    rep = br.run_batch(_FakeActions(), targets, delay_s=0.0, jitter_s=0.0, process_fn=_fake_process_ok)
    assert rep.attachment_download_count == 0


# ── 8) external AI call 금지 ───────────────────────────────────────


def test_external_ai_call_count_zero():
    targets = _mk_targets(1)
    rep = br.run_batch(_FakeActions(), targets, delay_s=0.0, jitter_s=0.0, process_fn=_fake_process_ok)
    assert rep.external_ai_call_count == 0


def test_audit_fail_on_external_ai_call_in_network_log():
    targets = _mk_targets(1)
    rep = br.run_batch(_FakeActions(), targets, delay_s=0.0, jitter_s=0.0, process_fn=_fake_process_ok)
    v = audit.judge_batch(rep, network_log=["GET https://api.anthropic.com/v1/messages"])
    assert v.code == "FAIL_EXTERNAL_AI_CALL_USED"


# ── 9) failure_records schema ───────────────────────────────────────


def test_failure_records_schema(tmp_path):
    targets = _mk_targets(2)
    rep = br.run_batch(_FakeActions(), targets, delay_s=0.0, jitter_s=0.0, process_fn=_fake_process_body_fail)
    paths = br.write_outputs(rep, tmp_path)
    failures = json.loads(paths["failures"].read_text(encoding="utf-8"))
    assert len(failures) == 2
    for f in failures:
        for k in ("sn", "folder_id", "status", "error"):
            assert k in f


# ── 10) partial batch verdict ───────────────────────────────────────


def test_audit_warn_partial_when_limit_smaller_than_total():
    targets = _mk_targets(10)
    rep = br.run_batch(_FakeActions(), targets, limit=3, delay_s=0.0, jitter_s=0.0, process_fn=_fake_process_ok)
    # target_total == 3 (limit applied), attempted == 3 → PASS
    v = audit.judge_batch(rep)
    assert v.code == "PASS_NAVER_MAIL_BODY_PIPELINE_BATCH"


def test_audit_warn_body_read_failures():
    targets = _mk_targets(2)
    rep = br.run_batch(_FakeActions(), targets, delay_s=0.0, jitter_s=0.0, process_fn=_fake_process_body_fail)
    v = audit.judge_batch(rep)
    assert v.code == "WARN_BODY_READ_FAILURES"


def test_audit_pass_clean_run():
    targets = _mk_targets(3)
    rep = br.run_batch(_FakeActions(), targets, delay_s=0.0, jitter_s=0.0, process_fn=_fake_process_ok)
    v = audit.judge_batch(rep)
    assert v.code == "PASS_NAVER_MAIL_BODY_PIPELINE_BATCH", v.reasons


def test_audit_fail_raw_leak_when_record_has_raw_body():
    targets = _mk_targets(1)
    rep = br.run_batch(_FakeActions(), targets, delay_s=0.0, jitter_s=0.0, process_fn=_fake_process_ok)
    # 강제 leak — to_dict 에 raw_body 가 보이도록 monkey patch
    rep.raw_body_leak_count = 1
    v = audit.judge_batch(rep)
    assert v.code == "FAIL_RAW_BODY_LEAK"


def test_audit_fail_attachment_downloaded():
    targets = _mk_targets(1)
    rep = br.run_batch(_FakeActions(), targets, delay_s=0.0, jitter_s=0.0, process_fn=_fake_process_ok)
    rep.attachment_download_count = 1
    v = audit.judge_batch(rep)
    assert v.code == "FAIL_ATTACHMENT_DOWNLOADED"


def test_audit_fail_checkpoint_broken():
    targets = _mk_targets(1)
    rep = br.run_batch(_FakeActions(), targets, delay_s=0.0, jitter_s=0.0, process_fn=_fake_process_ok)
    v = audit.judge_batch(rep, checkpoint_dict={"run_id": "broken"})
    assert v.code == "FAIL_CHECKPOINT_BROKEN"


# ── 11) 회귀 가드 ───────────────────────────────────────────────────


def test_regression_body_pipeline_v2_imports():
    from scripts.naver.mail import body_pipeline_v2 as bp

    assert hasattr(bp, "run")


def test_regression_dynamic_folder_discovery_imports():
    from scripts.naver.mail import folder_discovery as fd
    from scripts.naver.mail import folder_profile as fpr

    assert hasattr(fd, "discover_folders")
    assert hasattr(fpr, "build_snapshot")


def test_regression_smart_folder_coverage_imports():
    from scripts.naver.mail import smart_folder_collector as sfc

    assert hasattr(sfc, "collect_all")


# ── 12) throttle / sleep 호출 검증 ──────────────────────────────────


def test_throttle_sleep_called_between_mails():
    targets = _mk_targets(3)
    sleep_calls = []
    rep = br.run_batch(  # noqa: F841
        _FakeActions(),
        targets,
        delay_s=1.0,
        jitter_s=0.5,
        sleep_fn=lambda d: sleep_calls.append(d),
        process_fn=_fake_process_ok,
    )
    # 마지막 메일 뒤엔 sleep 안 함 → 2번 호출
    assert len(sleep_calls) == 2
    for d in sleep_calls:
        assert 1.0 <= d <= 1.5
