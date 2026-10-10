"""NAVER-MAIL-DYNAMIC-FOLDER-DISCOVERY-01 라이브 smoke.

수행:
  1. 받은편지함 진입
  2. 전체 폴더 자동 발견 + folder_id 학습
  3. 기본 정책 적용 → collectable / policy_excluded 분류
  4. folder_profile_snapshot 저장
  5. 기존 244건 수집 회귀 검증 (smart_folder_collector.collect_all)
  6. LNB 전체 unread 합계 검산
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from scripts.naver.mail import folder_discovery as fd
from scripts.naver.mail import folder_profile as fpr
from scripts.naver.mail import smart_folder_collector as sfc
from scripts.naver.mail.read import cdp
from scripts.naver.mail.collection import (
    audit_naver_mail_dynamic_folder_discovery as audit_dd,
)
from scripts.naver.mail.collection import (
    audit_naver_mail_smart_folder_coverage as audit_sf,
)


class LiveActions:
    def __init__(self, target_id):
        self.target_id = target_id

    def evaluate(self, expr):
        return cdp.evaluate(self.target_id, expr, timeout=10.0)

    def navigate(self, url):
        cdp.navigate(self.target_id, url)

    def wait_dom(self, expr, timeout_s=8.0):
        return cdp.wait_dom(self.target_id, expr, timeout=timeout_s)


def main():
    out_dir = Path("data/inspection/naver_mail_folder_discovery")
    out_dir.mkdir(parents=True, exist_ok=True)
    target_id = cdp.ensure_about_blank_target()
    print(f"[boot] target_id={target_id[:12]}")

    actions = LiveActions(target_id)
    actions.navigate("https://mail.naver.com/v2/folders/0/all")
    time.sleep(3)
    actions.wait_dom("document.querySelector('.lnb')", timeout_s=12.0)

    # 1) 발견
    t0 = time.time()
    folders = fd.discover_folders(actions, learn_ids=True)
    fd.filter_collectable(folders)
    discover_elapsed = round(time.time() - t0, 1)
    print(f"[1] discovered {len(folders)} folders in {discover_elapsed}s")

    # LNB 전체 unread 집계 (lnb 의 '전체 안읽은 메일' title)
    lnb_total = -1
    for f in folders:
        if f.title == "전체 안읽은 메일" and f.unread_count > 0:
            lnb_total = f.unread_count
            break

    # 2) snapshot
    snap = fpr.build_snapshot(folders, account_raw="", lnb_total_unread=lnb_total)
    snap_path = fpr.write_snapshot(snap, out_dir)
    print(f"[2] snapshot → {snap_path}")

    # 3) audit
    dv = audit_dd.judge(snap)
    snap.verdict = dv.code
    (out_dir / "folder_discovery_audit.json").write_text(
        json.dumps(
            {"verdict": dv.code, "passed": dv.passed, "reasons": dv.reasons, "metrics": dv.metrics},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("\n=== FOLDERS ===")
    for f in folders:
        flag = "✓" if f.is_collectable else " "
        print(
            f"  [{flag}] {f.name:>14} kind={f.kind:>10} unread={f.unread_count:>4}"
            f" fid={f.folder_id or '-':>4} adapter={f.adapter_selected:>20}"
            f" policy={f.default_policy_state}"
        )

    print(f"\n=== AUDIT (discovery) ===\n{dv.code} passed={dv.passed}  reasons={dv.reasons}")

    # 4) 기존 244건 회귀 — smart_folder_collector.collect_all
    print("\n[4] regression: smart_folder_collector.collect_all 실행 중 ...")
    t1 = time.time()
    rpt = sfc.collect_all(actions, max_pages=200, max_items_per_folder=5000)
    coverage_elapsed = round(time.time() - t1, 1)
    rd = sfc.report_to_dict(rpt)
    v_sf = audit_sf.judge_coverage(rpt)
    print(f"  collect_all 완료 in {coverage_elapsed}s")
    print(f"  folder_collected_total = {rd['folder_collected_total']}")
    print(f"  unique_sn_total = {rd['unique_sn_total']}")
    print(f"  audit: {v_sf.code}  passed={v_sf.passed}")

    # 저장
    (out_dir / "regression_smart_folder_coverage.json").write_text(
        json.dumps(
            {
                "folder_collected_total": rd["folder_collected_total"],
                "unique_sn_total": rd["unique_sn_total"],
                "warnings": rd["warnings"],
                "audit": {"verdict": v_sf.code, "passed": v_sf.passed, "reasons": v_sf.reasons},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
