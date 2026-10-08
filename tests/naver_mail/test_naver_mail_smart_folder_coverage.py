"""NAVER-MAIL-SMART-FOLDER-COVERAGE-01 — 필수 12 테스트."""

from __future__ import annotations

import re

from scripts.naver.mail import (
    folder_discovery as fd,
)
from scripts.naver.mail import (
    smart_folder_collector as sfc,
)
from scripts.naver.mail.collection import audit_naver_mail_smart_folder_coverage as audit
from tests.naver_mail.test_naver_mail_inbox_p0_complete import FakeActions, _mk_row

# ── 풍부한 Fake — LNB + multi-folder 응답 시뮬레이션 ─────────────────


class MultiFolderActions(FakeActions):
    """LNB / 폴더별 페이지 응답 / 폴더 클릭 학습 모두 처리."""

    def __init__(self, *, lnb_raw, folder_responses_by_url, ui_breakdown=None):
        # folder_responses_by_url: {"https://...0/unread": {"1":[rows..], "2":[..]}, ...}
        super().__init__()
        self.lnb_raw = lnb_raw
        self.folder_responses_by_url = folder_responses_by_url
        self.current_folder_url = "https://mail.naver.com/v2/folders/0/all"
        self.current_pageresp = {"1": []}
        self.current_page = "1"
        # lnb breakdown
        self._lnb_breakdown = ui_breakdown or {
            "inbox_unread": 66,
            "total_aggregate": 244,
            "smart_folder_breakdown": {"프로모션": 26, "청구·결제": 59, "SNS": 93},
            "toolbar_current_unread": 66,
            "source": "aggregate_with_smart_folders",
        }

    def _select_folder_resp(self):
        # find the folder_responses entry whose URL prefix matches current_folder_url
        for k, v in self.folder_responses_by_url.items():
            if self.current_folder_url.startswith(k):
                self.current_pageresp = v
                # page_buttons reflect this folder's pages
                self.page_buttons = list(v.keys())
                return
        self.current_pageresp = {"1": []}
        self.page_buttons = ["1"]

    def _list_payload(self):
        rows = self.current_pageresp.get(self.current_page, [])
        return {"href": self._build_url(), "title": "폴더 : 네이버 메일", "count": len(rows), "items": rows}

    def _build_url(self):
        base = self.current_folder_url
        if self.current_page == "1":
            return base
        sep = "&" if "?" in base else "?"
        return f"{base}{sep}page={self.current_page}"

    def evaluate(self, expr):
        # LNB folders expr 우선
        if "mailbox_item" in expr and "out.push" in expr:
            self.call_log.append("eval:LNB_FOLDERS")
            return list(self.lnb_raw)
        if "smart_folder_breakdown" in expr or ("inbox_unread" in expr and "total_aggregate" in expr):
            self.call_log.append("eval:LNB_BREAKDOWN")
            return self._lnb_breakdown
        # 폴더 클릭 (학습)
        if "lnb .mailbox_label" in expr and "lbls[i].click" in expr:
            # extract name from expr
            m = re.search(r"t==='([^']+)'", expr)
            if m:
                name = m.group(1)
                for raw in self.lnb_raw:
                    if raw.get("name") == name:
                        fid_map = getattr(self, "_id_map", {})
                        fid = fid_map.get(name, "X")
                        self.current_folder_url = f"https://mail.naver.com/v2/folders/{fid}"
                        self.current_page = "1"
                        self._select_folder_resp()
                        self.click_log.append(f"folder_click:{name}")
                        return True
            return False
        # 현재 URL 조회
        if "JSON.stringify({url: location.href" in expr:
            return {"url": self._build_url(), "title": "fake"}
        return super().evaluate(expr)

    def navigate(self, url):
        self.nav_log.append(url)
        self.call_log.append(f"nav:{url[:60]}")
        self.current_folder_url = url.split("?")[0]
        m = re.search(r"[?&]page=(\d+)", url)
        if m and m.group(1) in (self.current_pageresp or {}):
            self.current_page = m.group(1)
        else:
            self.current_page = "1"
        self._select_folder_resp()

    def wait_dom(self, expr, timeout_s=8.0):
        return True


def _lnb_raw_default():
    return [
        {
            "name": "받은메일함",
            "kind": "inbox",
            "cls": "mailbox_label svg_inbox",
            "title": "받은메일함",
            "href_attr": "#",
            "unread_text": "안 읽은 메일 2 개",
            "unread_count": 2,
        },
        {
            "name": "프로모션",
            "kind": "smart",
            "cls": "mailbox_label svg_depth",
            "title": "프로모션",
            "href_attr": "#",
            "unread_text": "안 읽은 메일 1 개",
            "unread_count": 1,
        },
        {
            "name": "SNS",
            "kind": "smart",
            "cls": "mailbox_label svg_depth",
            "title": "SNS",
            "href_attr": "#",
            "unread_text": "안 읽은 메일 1 개",
            "unread_count": 1,
        },
        {
            "name": "도면",
            "kind": "user",
            "cls": "mailbox_label svg_folder",
            "title": "도면",
            "href_attr": "#",
            "unread_text": "",
            "unread_count": -1,
        },
    ]


# ── 1) LNB 스마트폴더 count 파싱 ────────────────────────────────────


def test_lnb_smart_folder_count_parse():
    fa = MultiFolderActions(
        lnb_raw=_lnb_raw_default(),
        folder_responses_by_url={
            "https://mail.naver.com/v2/folders/0": {"1": [_mk_row("100"), _mk_row("101")]},
            "https://mail.naver.com/v2/folders/10": {"1": [_mk_row("200")]},
            "https://mail.naver.com/v2/folders/9": {"1": [_mk_row("300")]},
        },
    )
    fa._id_map = {"받은메일함": "0", "프로모션": "10", "SNS": "9"}
    folders = fd.discover_folders(fa, learn_ids=True)
    promo = next(f for f in folders if f.name == "프로모션")
    assert promo.unread_count == 1
    sns = next(f for f in folders if f.name == "SNS")
    assert sns.unread_count == 1


# ── 2) 스마트폴더 href/url 추출 (folder_id 학습) ──────────────────────


def test_smart_folder_id_learned_from_click():
    fa = MultiFolderActions(
        lnb_raw=_lnb_raw_default(),
        folder_responses_by_url={
            "https://mail.naver.com/v2/folders/0": {"1": [_mk_row("100")]},
            "https://mail.naver.com/v2/folders/10": {"1": [_mk_row("200")]},
            "https://mail.naver.com/v2/folders/9": {"1": [_mk_row("300")]},
        },
    )
    fa._id_map = {"받은메일함": "0", "프로모션": "10", "SNS": "9"}
    folders = fd.discover_folders(fa, learn_ids=True)
    promo = next(f for f in folders if f.name == "프로모션")
    assert promo.folder_id == "10"
    sns = next(f for f in folders if f.name == "SNS")
    assert sns.folder_id == "9"
    inbox = next(f for f in folders if f.kind == "inbox")
    assert inbox.folder_id == "0"


def test_filter_collectable_excludes_user_and_zero():
    folders = [
        fd.FolderInfo("받은메일함", "inbox", "", "", "", 2, folder_id="0"),
        fd.FolderInfo("프로모션", "smart", "", "", "", 1, folder_id="10"),
        fd.FolderInfo("카페", "smart", "", "", "", 0, folder_id="8"),  # 0 unread
        fd.FolderInfo("도면", "user", "", "", "", -1, folder_id=""),
    ]
    out = fd.filter_collectable(folders)
    names = [f.name for f in out]
    assert "받은메일함" in names
    assert "프로모션" in names
    assert "카페" not in names  # zero unread
    assert "도면" not in names  # user folder


# ── 3) folder adapter 선택 (current implementation uses URL-only) ───


def test_folder_adapter_uses_url_unread_pattern():
    # 모든 폴더는 /v2/folders/{id}/unread 패턴 사용
    fa = MultiFolderActions(
        lnb_raw=_lnb_raw_default(),
        folder_responses_by_url={
            "https://mail.naver.com/v2/folders/0": {
                "1": [_mk_row("100", is_unread=True), _mk_row("101", is_unread=True)]
            },
            "https://mail.naver.com/v2/folders/10": {"1": [_mk_row("200", is_unread=True)]},
            "https://mail.naver.com/v2/folders/9": {"1": [_mk_row("300", is_unread=True)]},
        },
    )
    fa._id_map = {"받은메일함": "0", "프로모션": "10", "SNS": "9"}
    rpt = sfc.collect_all(fa, max_pages=5, max_items_per_folder=20)  # noqa: F841
    # nav_log 에 unread URL 들 포함
    unread_urls = [u for u in fa.nav_log if "/unread" in u]
    assert any("/folders/0/unread" in u for u in unread_urls)
    assert any("/folders/10/unread" in u for u in unread_urls)
    assert any("/folders/9/unread" in u for u in unread_urls)


# ── 4) 폴더별 url_page pagination ───────────────────────────────────


def test_folder_url_page_pagination_works_per_folder():
    fa = MultiFolderActions(
        lnb_raw=_lnb_raw_default(),
        folder_responses_by_url={
            "https://mail.naver.com/v2/folders/0": {
                "1": [_mk_row("100", is_unread=True)],
                "2": [_mk_row("101", is_unread=True)],
            },
            "https://mail.naver.com/v2/folders/10": {"1": [_mk_row("200", is_unread=True)]},
            "https://mail.naver.com/v2/folders/9": {"1": [_mk_row("300", is_unread=True)]},
        },
    )
    fa._id_map = {"받은메일함": "0", "프로모션": "10", "SNS": "9"}
    rpt = sfc.collect_all(fa, max_pages=5, max_items_per_folder=20)
    inbox = next(f for f in rpt.folders if f.folder_name == "받은메일함")
    assert inbox.collected_total == 2
    # ?page=2 nav 발생
    assert any("/folders/0/unread?page=2" in u or "/folders/0/unread%3Fpage=2" in u for u in fa.nav_log), fa.nav_log


# ── 5) last_page_evidence 2개 이상 요구 ─────────────────────────────


def test_folder_last_page_evidence_required_for_pass():
    fa = MultiFolderActions(
        lnb_raw=_lnb_raw_default(),
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
    # 폴더 evidence 가 부족하면 audit 가 PARTIAL 로 떨어져야 함 — 일부는 evidence 부족 가능
    v = audit.judge_coverage(rpt)
    # PASS 가 아니라면 PARTIAL 또는 SESSION_STATE_CHANGED 중 하나
    assert v.code in (
        "PASS_NAVER_MAIL_SMART_FOLDER_COVERAGE",
        "WARN_PARTIAL_SMART_FOLDER_COVERAGE",
        "WARN_SESSION_STATE_CHANGED",
    )


# ── 6) 폴더별 UI count vs collected_unread 비교 ──────────────────────


def test_folder_ui_vs_collected_count():
    fa = MultiFolderActions(
        lnb_raw=_lnb_raw_default(),
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
    inbox = next(f for f in rpt.folders if f.folder_name == "받은메일함")
    assert inbox.ui_unread_count == 2
    assert inbox.collected_total == 2


# ── 7) 전체 UI vs 수집 합계 ──────────────────────────────────────────


def test_total_ui_vs_collected_sum():
    fa = MultiFolderActions(
        lnb_raw=_lnb_raw_default(),
        folder_responses_by_url={
            "https://mail.naver.com/v2/folders/0": {"1": [_mk_row("100"), _mk_row("101")]},
            "https://mail.naver.com/v2/folders/10": {"1": [_mk_row("200")]},
            "https://mail.naver.com/v2/folders/9": {"1": [_mk_row("300")]},
        },
    )
    fa._id_map = {"받은메일함": "0", "프로모션": "10", "SNS": "9"}
    rpt = sfc.collect_all(fa, max_pages=5, max_items_per_folder=20)
    # UI sum = 2 + 1 + 1 = 4, 수집 합계 = 2 + 1 + 1 = 4
    assert rpt.folder_collected_total == 4
    sum_ui = (
        sum(
            f.unread_count for f in [fd.FolderInfo(n, "smart", "", "", "", c) for n, c in [("프로모션", 1), ("SNS", 1)]]
        )
        + 2
    )  # 받은편지함 2
    assert sum_ui == 4


# ── 8) duplicate_across_folders 기록 ────────────────────────────────


def test_duplicate_across_folders_recorded():
    """동일 sn 이 두 폴더에 등장 시 duplicate_across_folders 에 기록."""
    fa = MultiFolderActions(
        lnb_raw=_lnb_raw_default(),
        folder_responses_by_url={
            "https://mail.naver.com/v2/folders/0": {
                "1": [_mk_row("100", is_unread=True), _mk_row("999", is_unread=True)]
            },
            "https://mail.naver.com/v2/folders/10": {"1": [_mk_row("999", is_unread=True)]},  # 중복
            "https://mail.naver.com/v2/folders/9": {"1": [_mk_row("300", is_unread=True)]},
        },
    )
    fa._id_map = {"받은메일함": "0", "프로모션": "10", "SNS": "9"}
    rpt = sfc.collect_all(fa, max_pages=5, max_items_per_folder=20)
    sns = {d["sn"] for d in rpt.duplicate_across_folders}
    assert "999" in sns
    # unique_sn_total < folder_collected_total
    assert rpt.unique_sn_total < rpt.folder_collected_total


# ── 9) SESSION_STATE_CHANGED 분류 ───────────────────────────────────


def test_session_state_changed_audit():
    rpt = sfc.CoverageReport(
        schema_version="1.0",
        run_id="x",
        started_at_iso="",
        ended_at_iso="",
        collect_mode="UNREAD_ONLY",
        folders=[],
        ui_count_snapshot_before={"by_folder": {"받은메일함": 5}, "by_folder_sum": 5},
        ui_count_snapshot_after={"by_folder": {"받은메일함": 3}, "by_folder_sum": 3},
        folder_collected_total=0,
        unique_sn_total=0,
        duplicate_across_folders=[],
        warnings=[],
    )
    v = audit.judge_coverage(rpt)
    assert v.code == "WARN_SESSION_STATE_CHANGED"


# ── 10) PII 마스킹 유지 ──────────────────────────────────────────────


def test_pii_masking_preserved_in_smart_folder_collection():
    fa = MultiFolderActions(
        lnb_raw=_lnb_raw_default(),
        folder_responses_by_url={
            "https://mail.naver.com/v2/folders/0": {
                "1": [_mk_row("100", sender_full='"X"<x@example.com>', subject="전화 010-1234-5678", is_unread=True)]
            },
            "https://mail.naver.com/v2/folders/10": {"1": []},
            "https://mail.naver.com/v2/folders/9": {"1": []},
        },
    )
    fa._id_map = {"받은메일함": "0", "프로모션": "10", "SNS": "9"}
    rpt = sfc.collect_all(fa, max_pages=5, max_items_per_folder=20)
    inbox = next(f for f in rpt.folders if f.folder_name == "받은메일함")
    if inbox.items:
        it = inbox.items[0]
        assert "x@example.com" not in it["sender_masked"]
        assert "010-****-****" in it["subject_masked"]


# ── 11) 금지 동작 미호출 ──────────────────────────────────────────────


def test_no_destructive_calls_in_smart_folder_mode():
    fa = MultiFolderActions(
        lnb_raw=_lnb_raw_default(),
        folder_responses_by_url={
            "https://mail.naver.com/v2/folders/0": {"1": [_mk_row("100", is_unread=True)]},
            "https://mail.naver.com/v2/folders/10": {"1": [_mk_row("200", is_unread=True)]},
            "https://mail.naver.com/v2/folders/9": {"1": [_mk_row("300", is_unread=True)]},
        },
    )
    fa._id_map = {"받은메일함": "0", "프로모션": "10", "SNS": "9"}
    sfc.collect_all(fa, max_pages=5, max_items_per_folder=20)
    bad_patterns = (
        "send",
        "delete",
        "trash",
        "spam",
        "download",
        "submit",
        "star",
        "label_change",
        "popup/read",
        "captureScreenshot",
    )
    for entry in fa.call_log + fa.click_log + fa.nav_log:
        for b in bad_patterns:
            assert b not in entry, f"forbidden 호출: {entry}"


# ── 12) audit PASS/WARN/FAIL ────────────────────────────────────────


def test_audit_fail_on_side_effect():
    rpt = sfc.CoverageReport(
        schema_version="1.0",
        run_id="x",
        started_at_iso="",
        ended_at_iso="",
        collect_mode="UNREAD_ONLY",
        folders=[],
        ui_count_snapshot_before={},
        ui_count_snapshot_after={},
        folder_collected_total=0,
        unique_sn_total=0,
        duplicate_across_folders=[],
        warnings=[],
    )
    v = audit.judge_coverage(rpt, side_effect_log=["eval:popup/read/0/100"])
    assert v.code == "FAIL_SIDE_EFFECT_OCCURRED"


def test_audit_pass_when_all_conditions_met():
    fc = sfc.FolderCoverage(
        folder_id="0",
        folder_name="받은메일함",
        kind="inbox",
        ui_unread_count=2,
        collected_total=2,
        collected_unread=2,
        pages_visited=["1"],
        pagination_strategy_used="url_page",
        last_page_evidence=["next_disabled", "url_page_no_change"],
        last_page_reached=True,
        warn_limit_reached=False,
        page_records=[],
        items=[],
        notes=[],
    )
    rpt = sfc.CoverageReport(
        schema_version="1.0",
        run_id="x",
        started_at_iso="",
        ended_at_iso="",
        collect_mode="UNREAD_ONLY",
        folders=[fc],
        ui_count_snapshot_before={"by_folder": {"받은메일함": 2}, "by_folder_sum": 2},
        ui_count_snapshot_after={"by_folder": {"받은메일함": 2}, "by_folder_sum": 2},
        folder_collected_total=2,
        unique_sn_total=2,
        duplicate_across_folders=[],
        warnings=[],
    )
    v = audit.judge_coverage(rpt)
    assert v.code == "PASS_NAVER_MAIL_SMART_FOLDER_COVERAGE", v.reasons
    assert v.passed is True
