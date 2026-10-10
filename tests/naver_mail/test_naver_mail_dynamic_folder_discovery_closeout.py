"""NAVER-MAIL-DYNAMIC-FOLDER-DISCOVERY-CLOSEOUT-01 — 필수 12 테스트."""

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
from scripts.naver.mail import (
    smart_folder_collector as sfc,
)
from scripts.naver.mail.collection import audit_naver_mail_dynamic_folder_discovery_closeout as audit
from tests.naver_mail.test_naver_mail_smart_folder_coverage import (
    MultiFolderActions,
    _mk_row,
)


def _live_like_lnb():
    """라이브 라이브와 유사한 LNB raw — JS 단에서 isSupport/kind 미리 적용된 형태."""
    return [
        # 전체메일
        {
            "name": "전체메일",
            "kind": "all",
            "raw_kind": "all",
            "cls": "mailbox_label svg_all",
            "title": "전체메일",
            "href_attr": "#",
            "unread_text": "",
            "unread_count": -1,
            "parent_group": "lnb_top",
            "depth": 0,
            "is_support_menu": False,
            "folder_evidence_count": 3,
            "unread_count_evidence": "no_badge_assumed_zero",
            "selector_evidence": {"is_support": False},
        },
        # 받은편지함
        {
            "name": "받은메일함",
            "kind": "inbox",
            "raw_kind": "inbox",
            "cls": "mailbox_label svg_inbox",
            "title": "받은메일함",
            "href_attr": "#",
            "unread_text": "안 읽은 메일 2 개",
            "unread_count": 2,
            "parent_group": "lnb_top",
            "depth": 0,
            "is_support_menu": False,
            "folder_evidence_count": 5,
            "unread_count_evidence": "explicit_badge",
            "selector_evidence": {"is_support": False},
        },
        # 보낸/임시/수신확인/내게쓴
        {
            "name": "보낸메일함",
            "kind": "sent",
            "raw_kind": "sent",
            "cls": "mailbox_label svg_sent_mail",
            "title": "",
            "href_attr": "#",
            "unread_text": "",
            "unread_count": -1,
            "parent_group": "lnb_top",
            "depth": 0,
            "is_support_menu": False,
            "folder_evidence_count": 4,
            "unread_count_evidence": "no_badge_assumed_zero",
            "selector_evidence": {"is_support": False},
        },
        # 스마트메일함 헤더
        {
            "name": "스마트메일함",
            "kind": "smart_group_header",
            "raw_kind": "smart_group_header",
            "cls": "mailbox_label svg_smartmail",
            "title": "",
            "href_attr": "",
            "unread_text": "안 읽은 메일 26 개",
            "unread_count": 26,
            "parent_group": "smart_group",
            "depth": 0,
            "is_support_menu": False,
            "folder_evidence_count": 4,
            "unread_count_evidence": "explicit_badge",
            "selector_evidence": {"is_support": False},
        },
        # 스마트 자식 폴더들
        {
            "name": "프로모션",
            "kind": "smart",
            "raw_kind": "smart",
            "cls": "mailbox_label svg_depth",
            "title": "프로모션",
            "href_attr": "#",
            "unread_text": "안 읽은 메일 26 개",
            "unread_count": 26,
            "parent_group": "smart_group",
            "depth": 1,
            "is_support_menu": False,
            "folder_evidence_count": 5,
            "unread_count_evidence": "explicit_badge",
            "selector_evidence": {"is_support": False},
        },
        {
            "name": "SNS",
            "kind": "smart",
            "raw_kind": "smart",
            "cls": "mailbox_label svg_depth",
            "title": "SNS",
            "href_attr": "#",
            "unread_text": "안 읽은 메일 93 개",
            "unread_count": 93,
            "parent_group": "smart_group",
            "depth": 1,
            "is_support_menu": False,
            "folder_evidence_count": 5,
            "unread_count_evidence": "explicit_badge",
            "selector_evidence": {"is_support": False},
        },
        {
            "name": "카페",
            "kind": "smart",
            "raw_kind": "smart",
            "cls": "mailbox_label svg_depth",
            "title": "카페",
            "href_attr": "#",
            "unread_text": "",
            "unread_count": -1,
            "parent_group": "smart_group",
            "depth": 1,
            "is_support_menu": False,
            "folder_evidence_count": 4,
            "unread_count_evidence": "no_badge_assumed_zero",
            "selector_evidence": {"is_support": False},
        },
        # 사용자 폴더
        {
            "name": "도면",
            "kind": "user",
            "raw_kind": "user",
            "cls": "mailbox_label svg_folder",
            "title": "도면",
            "href_attr": "#",
            "unread_text": "",
            "unread_count": -1,
            "parent_group": "lnb_top",
            "depth": 1,
            "is_support_menu": False,
            "folder_evidence_count": 4,
            "unread_count_evidence": "no_badge_assumed_zero",
            "selector_evidence": {"is_support": False},
        },
        # 스팸/휴지통
        {
            "name": "스팸메일함",
            "kind": "spam",
            "raw_kind": "spam",
            "cls": "mailbox_label svg_spam",
            "title": "스팸메일함",
            "href_attr": "#",
            "unread_text": "안 읽은 메일 270 개",
            "unread_count": 270,
            "parent_group": "lnb_top",
            "depth": 0,
            "is_support_menu": False,
            "folder_evidence_count": 5,
            "unread_count_evidence": "explicit_badge",
            "selector_evidence": {"is_support": False},
        },
        {
            "name": "휴지통",
            "kind": "trash",
            "raw_kind": "trash",
            "cls": "mailbox_label svg_trash",
            "title": "휴지통",
            "href_attr": "#",
            "unread_text": "안 읽은 메일 7 개",
            "unread_count": 7,
            "parent_group": "lnb_top",
            "depth": 0,
            "is_support_menu": False,
            "folder_evidence_count": 5,
            "unread_count_evidence": "explicit_badge",
            "selector_evidence": {"is_support": False},
        },
        # nav_action 5건 (support class)
        {
            "name": "환경설정",
            "kind": "nav_action",
            "raw_kind": "unknown",
            "cls": "mailbox_label",
            "title": "",
            "href_attr": "#",
            "unread_text": "",
            "unread_count": -1,
            "parent_group": "lnb_top",
            "depth": 0,
            "is_support_menu": True,
            "folder_evidence_count": 1,
            "unread_count_evidence": "no_badge_assumed_zero",
            "selector_evidence": {"is_support": True},
        },
        {
            "name": "로그아웃",
            "kind": "nav_action",
            "raw_kind": "unknown",
            "cls": "mailbox_label",
            "title": "",
            "href_attr": "#",
            "unread_text": "",
            "unread_count": -1,
            "parent_group": "lnb_top",
            "depth": 0,
            "is_support_menu": True,
            "folder_evidence_count": 1,
            "unread_count_evidence": "no_badge_assumed_zero",
            "selector_evidence": {"is_support": True},
        },
        {
            "name": "고객센터",
            "kind": "nav_action",
            "raw_kind": "unknown",
            "cls": "mailbox_label",
            "title": "",
            "href_attr": "#",
            "unread_text": "",
            "unread_count": -1,
            "parent_group": "lnb_top",
            "depth": 0,
            "is_support_menu": True,
            "folder_evidence_count": 1,
            "unread_count_evidence": "no_badge_assumed_zero",
            "selector_evidence": {"is_support": True},
        },
        {
            "name": "메일용량",
            "kind": "nav_action",
            "raw_kind": "unknown",
            "cls": "mailbox_label",
            "title": "",
            "href_attr": "#",
            "unread_text": "",
            "unread_count": -1,
            "parent_group": "lnb_top",
            "depth": 0,
            "is_support_menu": True,
            "folder_evidence_count": 1,
            "unread_count_evidence": "no_badge_assumed_zero",
            "selector_evidence": {"is_support": True},
        },
        {
            "name": "외부메일 가져오기",
            "kind": "nav_action",
            "raw_kind": "unknown",
            "cls": "mailbox_label",
            "title": "",
            "href_attr": "#",
            "unread_text": "",
            "unread_count": -1,
            "parent_group": "lnb_top",
            "depth": 0,
            "is_support_menu": True,
            "folder_evidence_count": 1,
            "unread_count_evidence": "no_badge_assumed_zero",
            "selector_evidence": {"is_support": True},
        },
    ]


def _mk_actions(id_map=None):
    fa = MultiFolderActions(
        lnb_raw=_live_like_lnb(),
        folder_responses_by_url={
            "https://mail.naver.com/v2/folders/0": {
                "1": [_mk_row("100", is_unread=True), _mk_row("101", is_unread=True)]
            },
            "https://mail.naver.com/v2/folders/10": {"1": [_mk_row("200", is_unread=True)]},
            "https://mail.naver.com/v2/folders/9": {"1": [_mk_row("300", is_unread=True)]},
        },
    )
    fa._id_map = id_map or {"받은메일함": "0", "프로모션": "10", "SNS": "9"}
    return fa


# ── 1) LNB 메뉴/푸터 non_folder_menu 분류 ───────────────────────────


def test_lnb_menu_classified_as_nav_action():
    fa = _mk_actions()
    folders = fd.discover_folders(fa, learn_ids=False)
    by = {f.name: f for f in folders}
    for nm in ("환경설정", "로그아웃", "고객센터", "메일용량", "외부메일 가져오기"):
        assert by[nm].kind == fp.KIND_NAV_ACTION, f"{nm} kind={by[nm].kind}"
        assert by[nm].is_nav_action is True
        assert by[nm].is_support_menu is True
        assert by[nm].is_collectable is False


# ── 2) nav_action 은 unknown_folders 에 들어가지 않음 ───────────────


def test_nav_actions_not_in_unknown_folders():
    fa = _mk_actions()
    folders = fd.discover_folders(fa, learn_ids=False)
    fd.filter_collectable(folders)
    snap = fpr.build_snapshot(folders, lnb_total_unread=521)
    for nm in ("환경설정", "로그아웃", "고객센터", "메일용량", "외부메일 가져오기"):
        assert nm not in snap.unknown_folders, f"{nm} 가 unknown 에 있음"
        assert nm in snap.non_folder_menus


# ── 3) 실제 폴더 evidence 2개 이상 요구 ─────────────────────────────


def test_folder_evidence_count_threshold():
    fa = _mk_actions()
    folders = fd.discover_folders(fa, learn_ids=False)
    # 받은메일함은 evidence 5개
    inbox = next(f for f in folders if f.name == "받은메일함")
    assert inbox.folder_evidence_count >= 2
    # nav_action 은 1개 (only mailbox_item)
    setup = next(f for f in folders if f.name == "환경설정")
    assert setup.folder_evidence_count <= 1


# ── 4) 스마트메일함 헤더 count 중복 합산 제외 ───────────────────────


def test_smart_group_header_excluded_from_real_sum():
    fa = _mk_actions()
    folders = fd.discover_folders(fa, learn_ids=False)
    fd.filter_collectable(folders)
    snap = fpr.build_snapshot(folders, lnb_total_unread=521)
    rec = snap.reconciliation
    # raw 합은 헤더 26 포함
    assert rec["smart_group_header_duplicate_sum"] == 26
    # reconciled = raw - 26
    assert rec["reconciled_real_sum"] == rec["raw_lnb_sum"] - 26


# ── 5) reconciliation formula ───────────────────────────────────────


def test_reconciliation_formula_explained():
    fa = _mk_actions()
    folders = fd.discover_folders(fa, learn_ids=False)
    fd.filter_collectable(folders)
    snap = fpr.build_snapshot(folders, lnb_total_unread=521)
    rec = snap.reconciliation
    # inbox 2 + smart (26+93) = 121, spam 270, trash 7 → 합 398
    # 헤더 26 = duplicate → raw 합 424, 헤더 빼면 398
    assert rec["active_inbox_smart_sum"] == 2 + 26 + 93
    assert rec["spam_unread_sum"] == 270
    assert rec["trash_unread_sum"] == 7
    assert rec["explained"] is True
    assert "raw" in rec["formula"] and "reconciled" in rec["formula"]


# ── 6) unread=-1 smart folder 상태 분류 ─────────────────────────────


def test_unread_minus_one_smart_folder_handled_as_zero():
    fa = _mk_actions()
    folders = fd.discover_folders(fa, learn_ids=False)
    cafe = next(f for f in folders if f.name == "카페")
    # no_badge_assumed_zero → 0 으로 보정
    assert cafe.unread_count == 0
    assert cafe.unread_count_evidence == "no_badge_assumed_zero"
    assert cafe.unread_count_unknown is False
    assert cafe.requires_click_probe is False


# ── 7) collect_user_folders=True 정책 ───────────────────────────────


def test_collect_user_folders_true_policy():
    fa = _mk_actions()
    folders = fd.discover_folders(fa, learn_ids=False)
    # 도면에 folder_id 주입 (학습 단계 우회)
    for f in folders:
        if f.name == "도면":
            f.folder_id = "11"
            f.unread_count = 3  # 임의 unread 부여 (테스트용)
    policy = fp.FolderPolicy(collect_user_folders=True)
    collectable = fd.filter_collectable(folders, policy=policy)
    names = [f.name for f in collectable]
    assert "도면" in names


# ── 8) collect_user_folders=False 기본 제외 ─────────────────────────


def test_collect_user_folders_false_default():
    fa = _mk_actions()
    folders = fd.discover_folders(fa, learn_ids=False)
    for f in folders:
        if f.name == "도면":
            f.folder_id = "11"
            f.unread_count = 3
    collectable = fd.filter_collectable(folders)
    names = [f.name for f in collectable]
    assert "도면" not in names


# ── 9) 기존 smart folder coverage 244 회귀 ──────────────────────────


def test_regression_smart_folder_244_still_works():
    fa = MultiFolderActions(
        lnb_raw=_live_like_lnb(),
        folder_responses_by_url={
            "https://mail.naver.com/v2/folders/0": {"1": [_mk_row(str(i), is_unread=True) for i in range(2)]},
            "https://mail.naver.com/v2/folders/10": {"1": [_mk_row(str(i), is_unread=True) for i in range(100, 101)]},
            "https://mail.naver.com/v2/folders/9": {"1": [_mk_row(str(i), is_unread=True) for i in range(200, 201)]},
        },
    )
    fa._id_map = {"받은메일함": "0", "프로모션": "10", "SNS": "9"}
    rpt = sfc.collect_all(fa, max_pages=5, max_items_per_folder=20)
    # nav_action / smart_group_header 가 수집 대상이 아님을 검증
    folder_names = [f.folder_name for f in rpt.folders]
    assert "환경설정" not in folder_names
    assert "로그아웃" not in folder_names
    assert "스마트메일함" not in folder_names
    # 받은편지함 / 프로모션 / SNS 는 포함
    assert "받은메일함" in folder_names
    assert "프로모션" in folder_names
    assert "SNS" in folder_names


# ── 10) 개인정보/secret 미노출 ──────────────────────────────────────


def test_no_pii_or_secret_leak_in_closeout_snapshot():
    fa = _mk_actions()
    folders = fd.discover_folders(fa, learn_ids=False)
    fd.filter_collectable(folders)
    snap = fpr.build_snapshot(folders, account_raw="skyjw@naver.com", lnb_total_unread=547)
    j = json.dumps(asdict(snap), ensure_ascii=False)
    bad = ["skyjw@naver.com", "password", "token", "cookie", "session=", "NID_SES", "NID_AUT"]
    for b in bad:
        assert b not in j, f"leak: {b}"


# ── 11) 금지 동작 미호출 ────────────────────────────────────────────


def test_no_destructive_calls_in_closeout_discovery():
    fa = _mk_actions()
    fd.discover_folders(fa, learn_ids=True)
    bad = (
        "send",
        "delete",
        "trash_action",
        "spam_action",
        "download",
        "submit",
        "popup/read",
        "captureScreenshot",
        "label_change",
    )
    for entry in fa.call_log + fa.click_log + fa.nav_log:
        for b in bad:
            assert b not in entry, f"forbidden: {entry}"


# ── 12) audit PASS/WARN/FAIL ────────────────────────────────────────


def test_audit_pass_when_no_unknown_and_reconciled():
    fa = _mk_actions()
    folders = fd.discover_folders(fa, learn_ids=False)
    fd.filter_collectable(folders)
    snap = fpr.build_snapshot(folders, lnb_total_unread=521)
    v = audit.judge_closeout(snap)
    assert v.code == "PASS_NAVER_MAIL_DYNAMIC_FOLDER_DISCOVERY_CLOSEOUT", v.reasons
    assert v.passed is True


def test_audit_warn_when_reconciliation_unexplained():
    fa = _mk_actions()
    folders = fd.discover_folders(fa, learn_ids=False)
    fd.filter_collectable(folders)
    snap = fpr.build_snapshot(folders, lnb_total_unread=521)
    # 강제로 reconciliation 미설명 만들기
    snap.reconciliation["explained"] = False
    v = audit.judge_closeout(snap)
    assert v.code == "WARN_LNB_COUNT_RECONCILIATION_REMAINS"


def test_audit_fail_on_side_effect():
    fa = _mk_actions()
    folders = fd.discover_folders(fa, learn_ids=False)
    snap = fpr.build_snapshot(folders)
    v = audit.judge_closeout(snap, side_effect_log=["eval:popup/read/0/100"])
    assert v.code == "FAIL_SIDE_EFFECT_OCCURRED"
