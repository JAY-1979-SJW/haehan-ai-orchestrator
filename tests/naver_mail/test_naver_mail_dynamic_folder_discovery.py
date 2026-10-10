"""NAVER-MAIL-DYNAMIC-FOLDER-DISCOVERY-01 — 필수 14 테스트."""

from __future__ import annotations

import json
from dataclasses import asdict

from scripts.naver.mail import (
    folder_discovery as fd,
)
from scripts.naver.mail import (
    folder_policy as fp,
)
from scripts.naver.mail import (
    folder_profile as fpr,
)
from scripts.naver.mail.collection import audit_naver_mail_dynamic_folder_discovery as audit
from tests.naver_mail.test_naver_mail_smart_folder_coverage import (
    MultiFolderActions,
    _mk_row,
)


def _full_lnb():
    """실제 라이브에서 본 폴더 구조와 유사한 fake LNB raw."""
    return [
        {
            "name": "전체메일",
            "kind": "all",
            "cls": "mailbox_label svg_all",
            "title": "전체메일",
            "href_attr": "#",
            "unread_text": "",
            "unread_count": -1,
            "parent_group": "lnb_top",
            "depth": 0,
            "selector_evidence": {},
        },
        {
            "name": "받은메일함",
            "kind": "inbox",
            "cls": "mailbox_label svg_inbox",
            "title": "받은메일함",
            "href_attr": "#",
            "unread_text": "안 읽은 메일 2 개",
            "unread_count": 2,
            "parent_group": "lnb_top",
            "depth": 0,
            "selector_evidence": {},
        },
        {
            "name": "보낸메일함",
            "kind": "sent",
            "cls": "mailbox_label svg_sent_mail",
            "title": "",
            "href_attr": "#",
            "unread_text": "",
            "unread_count": -1,
            "parent_group": "lnb_top",
            "depth": 0,
            "selector_evidence": {},
        },
        {
            "name": "임시보관함",
            "kind": "draft",
            "cls": "mailbox_label svg_temporary",
            "title": "",
            "href_attr": "#",
            "unread_text": "",
            "unread_count": -1,
            "parent_group": "lnb_top",
            "depth": 0,
            "selector_evidence": {},
        },
        {
            "name": "프로모션",
            "kind": "smart",
            "cls": "mailbox_label svg_depth",
            "title": "",
            "href_attr": "#",
            "unread_text": "안 읽은 메일 1 개",
            "unread_count": 1,
            "parent_group": "smart_group",
            "depth": 1,
            "selector_evidence": {},
        },
        {
            "name": "SNS",
            "kind": "smart",
            "cls": "mailbox_label svg_depth",
            "title": "",
            "href_attr": "#",
            "unread_text": "안 읽은 메일 1 개",
            "unread_count": 1,
            "parent_group": "smart_group",
            "depth": 1,
            "selector_evidence": {},
        },
        {
            "name": "도면",
            "kind": "user",
            "cls": "mailbox_label svg_folder",
            "title": "도면",
            "href_attr": "#",
            "unread_text": "",
            "unread_count": -1,
            "parent_group": "lnb_top",
            "depth": 1,
            "selector_evidence": {},
        },
        {
            "name": "사랑하는 부인♥~",
            "kind": "smart",
            "cls": "mailbox_label svg_depth",
            "title": "",
            "href_attr": "#",
            "unread_text": "",
            "unread_count": -1,
            "parent_group": "smart_group",
            "depth": 1,
            "selector_evidence": {},
        },
        {
            "name": "스팸메일함",
            "kind": "spam",
            "cls": "mailbox_label svg_spam",
            "title": "스팸메일함",
            "href_attr": "#",
            "unread_text": "안 읽은 메일 270 개",
            "unread_count": 270,
            "parent_group": "lnb_top",
            "depth": 0,
            "selector_evidence": {},
        },
        {
            "name": "휴지통",
            "kind": "trash",
            "cls": "mailbox_label svg_trash",
            "title": "휴지통",
            "href_attr": "#",
            "unread_text": "안 읽은 메일 7 개",
            "unread_count": 7,
            "parent_group": "lnb_top",
            "depth": 0,
            "selector_evidence": {},
        },
        {
            "name": "신규한정폴더",
            "kind": "unknown",
            "cls": "mailbox_label mystery_class",
            "title": "",
            "href_attr": "#",
            "unread_text": "",
            "unread_count": -1,
            "parent_group": "lnb_top",
            "depth": 0,
            "selector_evidence": {},
        },
    ]


def _mk_actions(folder_responses=None, id_map=None):
    fa = MultiFolderActions(
        lnb_raw=_full_lnb(),
        folder_responses_by_url=folder_responses or {},
    )
    fa._id_map = id_map or {}
    return fa


# ── 1) LNB 전체 폴더 자동 발견 ──────────────────────────────────────


def test_lnb_discover_all_folders():
    fa = _mk_actions()
    folders = fd.discover_folders(fa, learn_ids=False)
    names = [f.name for f in folders]
    assert "받은메일함" in names
    assert "프로모션" in names
    assert "스팸메일함" in names
    assert "휴지통" in names
    assert "도면" in names
    assert "신규한정폴더" in names
    # 11 폴더 모두 발견
    assert len(folders) == len(_full_lnb())


# ── 2) 시스템 폴더 분류 ──────────────────────────────────────────────


def test_system_folder_classification():
    fa = _mk_actions()
    folders = fd.discover_folders(fa, learn_ids=False)
    by = {f.name: f for f in folders}
    assert by["받은메일함"].kind == fp.KIND_INBOX
    assert by["보낸메일함"].kind == fp.KIND_SENT
    assert by["임시보관함"].kind == fp.KIND_DRAFT
    assert by["스팸메일함"].kind == fp.KIND_SPAM
    assert by["휴지통"].kind == fp.KIND_TRASH
    assert by["전체메일"].kind == fp.KIND_ALL
    # system flag
    assert by["받은메일함"].is_system_folder is True
    assert by["스팸메일함"].is_spam is True
    assert by["휴지통"].is_trash is True


# ── 3) 스마트메일함 분류 ─────────────────────────────────────────────


def test_smart_folder_classification():
    fa = _mk_actions()
    folders = fd.discover_folders(fa, learn_ids=False)
    by = {f.name: f for f in folders}
    assert by["프로모션"].kind == fp.KIND_SMART
    assert by["프로모션"].is_smart_folder is True
    assert by["SNS"].kind == fp.KIND_SMART
    # 한글 특이문자 폴더도 smart
    assert by["사랑하는 부인♥~"].kind == fp.KIND_SMART


# ── 4) 사용자 폴더 분류 ──────────────────────────────────────────────


def test_user_folder_classification():
    fa = _mk_actions()
    folders = fd.discover_folders(fa, learn_ids=False)
    by = {f.name: f for f in folders}
    assert by["도면"].kind == fp.KIND_USER
    assert by["도면"].is_user_folder is True


# ── 5) 스팸/휴지통 기본 제외 정책 ────────────────────────────────────


def test_default_policy_excludes_spam_and_trash():
    fa = _mk_actions(
        folder_responses={
            "https://mail.naver.com/v2/folders/0": {"1": [_mk_row("100")]},
            "https://mail.naver.com/v2/folders/10": {"1": [_mk_row("200")]},
            "https://mail.naver.com/v2/folders/9": {"1": [_mk_row("300")]},
        },
        id_map={"받은메일함": "0", "프로모션": "10", "SNS": "9"},
    )
    folders = fd.discover_folders(fa, learn_ids=True)
    collectable = fd.filter_collectable(folders)
    names = [f.name for f in collectable]
    assert "스팸메일함" not in names
    assert "휴지통" not in names
    # 기본 정책: inbox + smart 만 (이 fake 에선 unread>0 인 것)
    assert "받은메일함" in names
    assert "프로모션" in names
    assert "SNS" in names


# ── 6) include_folder_names 정책 ────────────────────────────────────


def test_include_folder_names_override():
    fa = _mk_actions(id_map={"받은메일함": "0", "스팸메일함": "S"})
    # 스팸을 강제 학습 (정책상 학습 안 함이 기본이므로 직접 ID 부여)
    folders = fd.discover_folders(fa, learn_ids=False)
    for f in folders:
        if f.name == "스팸메일함":
            f.folder_id = "S"
        elif f.name == "받은메일함":
            f.folder_id = "0"
    policy = fp.FolderPolicy(include_folder_names=["스팸메일함"])
    collectable = fd.filter_collectable(folders, policy=policy)
    names = [f.name for f in collectable]
    assert "스팸메일함" in names


# ── 7) exclude_folder_names 정책 ────────────────────────────────────


def test_exclude_folder_names_override():
    fa = _mk_actions(id_map={"받은메일함": "0", "프로모션": "10"})
    folders = fd.discover_folders(fa, learn_ids=False)
    for f in folders:
        if f.name == "받은메일함":
            f.folder_id = "0"
        elif f.name == "프로모션":
            f.folder_id = "10"
    policy = fp.FolderPolicy(exclude_folder_names=["프로모션"])
    collectable = fd.filter_collectable(folders, policy=policy)
    names = [f.name for f in collectable]
    assert "프로모션" not in names
    assert "받은메일함" in names


# ── 8) unknown folder WARN 처리 ─────────────────────────────────────


def test_unknown_folder_excluded_by_default():
    fa = _mk_actions()
    folders = fd.discover_folders(fa, learn_ids=False)
    unknown = next(f for f in folders if f.name == "신규한정폴더")
    assert unknown.kind == fp.KIND_UNKNOWN
    collectable = fd.filter_collectable(folders)
    names = [f.name for f in collectable]
    assert "신규한정폴더" not in names  # 기본 include_unknown_folders=False


# ── 9) adapter 자동 선택 ────────────────────────────────────────────


def test_adapter_selection_for_known_kinds():
    a, _ = fp.select_adapter(kind=fp.KIND_INBOX, folder_id="0")
    assert a == fp.ADAPTER_URL_PAGE
    a, _ = fp.select_adapter(kind=fp.KIND_SMART, folder_id="10")
    assert a == fp.ADAPTER_URL_PAGE
    a, _ = fp.select_adapter(kind=fp.KIND_SPAM, folder_id="S")
    assert a == fp.ADAPTER_URL_PAGE


def test_adapter_unsupported_for_unknown_without_id():
    a, _ = fp.select_adapter(kind=fp.KIND_UNKNOWN, folder_id="")
    assert a == fp.ADAPTER_UNSUPPORTED
    a, _ = fp.select_adapter(kind=fp.KIND_INBOX, folder_id="")
    assert a == fp.ADAPTER_UNSUPPORTED


# ── 10) folder_profile_snapshot schema ──────────────────────────────


def test_folder_profile_snapshot_schema():
    fa = _mk_actions()
    folders = fd.discover_folders(fa, learn_ids=False)
    fd.filter_collectable(folders)
    snap = fpr.build_snapshot(folders, account_raw="user@example.com", lnb_total_unread=281)
    d = asdict(snap)
    missing = fpr.validate_schema(d)
    assert missing == []
    # account_hint_masked 는 hash, 원문 없음
    assert "user@example.com" not in json.dumps(d, ensure_ascii=False)
    assert d["account_hint_masked"].startswith("acct:")


# ── 11) 개인정보/secret 미노출 ──────────────────────────────────────


def test_no_pii_or_secret_leak_in_snapshot():
    fa = _mk_actions()
    folders = fd.discover_folders(fa, learn_ids=False)
    fd.filter_collectable(folders)
    snap = fpr.build_snapshot(folders, account_raw="skyjw@naver.com", lnb_total_unread=100)
    j = json.dumps(asdict(snap), ensure_ascii=False)
    forbidden = ["skyjw@naver.com", "password", "token", "session=", "cookie", "NID_SES", "NID_AUT"]
    for f in forbidden:
        assert f not in j, f"PII/secret leak detected: {f}"


# ── 12) 금지 동작 미호출 ─────────────────────────────────────────────


def test_no_destructive_calls_during_discovery():
    fa = _mk_actions(
        folder_responses={
            "https://mail.naver.com/v2/folders/0": {"1": [_mk_row("100")]},
            "https://mail.naver.com/v2/folders/10": {"1": [_mk_row("200")]},
            "https://mail.naver.com/v2/folders/9": {"1": [_mk_row("300")]},
        },
        id_map={"받은메일함": "0", "프로모션": "10", "SNS": "9"},
    )
    fd.discover_folders(fa, learn_ids=True)
    bad = ("send", "delete", "trash_action", "spam_action", "download", "submit", "popup/read", "captureScreenshot")
    for entry in fa.call_log + fa.click_log + fa.nav_log:
        for b in bad:
            assert b not in entry, f"forbidden: {entry}"


# ── 13) 기존 smart folder coverage 회귀 ──────────────────────────────


def test_regression_smart_folder_coverage_still_works():
    """4개 폴더 244건 시나리오에서 기존 collect_all 호출이 그대로 동작."""
    from scripts.naver.mail import smart_folder_collector as sfc

    fa = MultiFolderActions(
        lnb_raw=_full_lnb()[:6] + [_full_lnb()[3]],  # subset  # noqa: RUF005
        folder_responses_by_url={
            "https://mail.naver.com/v2/folders/0": {
                "1": [_mk_row("100", is_unread=True), _mk_row("101", is_unread=True)]
            },
            "https://mail.naver.com/v2/folders/10": {"1": [_mk_row("200", is_unread=True)]},
            "https://mail.naver.com/v2/folders/9": {"1": [_mk_row("300", is_unread=True)]},
        },
    )
    fa._id_map = {"받은메일함": "0", "프로모션": "10", "SNS": "9"}
    rpt = sfc.collect_all(fa, max_pages=5, max_items_per_folder=20)
    assert rpt.folder_collected_total == 4
    # 받은편지함 + 프로모션 + SNS = 3 폴더 (kind 매칭)
    assert len(rpt.folders) >= 3


# ── 14) audit PASS/WARN/FAIL ─────────────────────────────────────────


def test_audit_pass_when_all_conditions_met():
    fa = _mk_actions(
        folder_responses={
            "https://mail.naver.com/v2/folders/0": {"1": [_mk_row("100")]},
        },
        id_map={"받은메일함": "0", "프로모션": "10", "SNS": "9"},
    )
    folders = fd.discover_folders(fa, learn_ids=True)
    fd.filter_collectable(folders)
    # 신규한정폴더가 unknown 이라 WARN_FOLDER_POLICY_EXCLUDED 가 정상
    snap = fpr.build_snapshot(folders, lnb_total_unread=281)
    v = audit.judge(snap)
    assert v.code in (
        "PASS_NAVER_MAIL_DYNAMIC_FOLDER_DISCOVERY",
        "WARN_FOLDER_POLICY_EXCLUDED",
    )


def test_audit_fail_on_side_effect():
    fa = _mk_actions()
    folders = fd.discover_folders(fa, learn_ids=False)
    fd.filter_collectable(folders)
    snap = fpr.build_snapshot(folders)
    v = audit.judge(snap, side_effect_log=["eval:popup/read/0/100"])
    assert v.code == "FAIL_SIDE_EFFECT_OCCURRED"


def test_audit_warn_when_unknown_folder_is_collectable():
    # 강제로 unknown 폴더를 collectable 로 설정 후 audit
    fa = _mk_actions()
    folders = fd.discover_folders(fa, learn_ids=False)
    fd.filter_collectable(folders)
    for f in folders:
        if f.kind == fp.KIND_UNKNOWN:
            f.is_collectable = True
    snap = fpr.build_snapshot(folders)
    v = audit.judge(snap)
    assert v.code == "WARN_UNKNOWN_FOLDER_DETECTED"
