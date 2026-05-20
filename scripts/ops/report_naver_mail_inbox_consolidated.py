"""기존 라이브 산출물(체크포인트 + 5/20 list metadata)을 합쳐
PII 마스킹된 비즈니스 보고서 생성.

입력:
  data/inspection/naver_mail_body_pipeline_batch/checkpoint.json
  data/inspection/mail_20260520/mail_unread_report.json
  data/inspection/naver_mail_smart_folder_coverage/folder_results/*.json

출력:
  data/inspection/naver_mail_inbox_consolidated_report/
    consolidated_business_report.md
    consolidated_data.json
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from scripts.naver_mail import pii_mask
from scripts.naver_mail.batch_runner import (
    MailResult, BatchReport, _classify_priority, _render_business_report,
    UNREAD_CHANGED_RESTORED, BODY_READ_OK, SKIPPED_ALREADY_DONE,
)


def _load_json(p: Path) -> dict:
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def main():
    base = Path("data/inspection")
    ck = _load_json(base / "naver_mail_body_pipeline_batch/checkpoint.json")
    list_old = _load_json(base / "mail_20260520/mail_unread_report.json")
    smart_dir = base / "naver_mail_smart_folder_coverage/folder_results"

    # 1) checkpoint sn → status, hash, pii_count
    sn_status = ck.get("sn_to_status", {})

    # 2) 5/20 list — 제목/발신자/날짜 (이미 마스킹된 상태)
    sn_meta: dict[str, dict] = {}
    for lbl, lst in (list_old.get("classified", {}) or {}).items():
        for it in lst:
            sn = it.get("sn", "")
            if sn:
                sn_meta[sn] = {
                    "subject": it.get("subject", ""),
                    "sender_name": it.get("sender_name", ""),
                    "sender_full": it.get("sender_full", ""),
                    "time_txt": it.get("time_txt", ""),
                    "size_txt": it.get("size_txt", ""),
                    "preview": it.get("preview", ""),
                    "folder_name": "받은메일함",
                }

    # 3) smart_folder_coverage — 스마트폴더의 sn → meta
    if smart_dir.exists():
        for jf in smart_dir.glob("*.json"):
            d = _load_json(jf)
            fname = d.get("folder_name", "")
            for it in d.get("items", []) or []:
                sn = it.get("sn", "")
                if sn and sn not in sn_meta:
                    sn_meta[sn] = {
                        "subject": it.get("subject_masked", ""),
                        "sender_name": "",
                        "sender_full": it.get("sender_masked", ""),
                        "time_txt": it.get("display_time", ""),
                        "size_txt": it.get("size_txt", ""),
                        "preview": "",
                        "folder_name": fname or "스마트폴더",
                    }

    # 4) MailResult 합성 — 체크포인트 + meta JOIN
    rep = BatchReport()
    rep.run_id = "consolidated"
    rep.target_total = len(sn_status)
    pii_total = 0
    pii_types_total: Counter[str] = Counter()
    for sn, st in sn_status.items():
        meta = sn_meta.get(sn, {})
        subj = meta.get("subject", "")
        sender = meta.get("sender_full") or meta.get("sender_name", "")
        # 한 번 더 PII 마스킹 (이중 안전)
        subj_m = pii_mask.mask(subj).masked_text
        sender_m = pii_mask.mask(sender).masked_text
        pii_n = int(st.get("pii_detected_count", 0))
        pii_total += pii_n
        # types 는 체크포인트에 없으므로 generic 처리
        mr = MailResult(
            sn=sn,
            folder_id="",
            folder_name=meta.get("folder_name", "받은메일함"),
            status=st.get("status", ""),
            body_open_ok=True,
            masked_text_hash=st.get("masked_text_hash", ""),
            pii_detected_count=pii_n,
            subject_masked=subj_m[:300],
            sender_masked=sender_m[:200],
            date_text=meta.get("time_txt", ""),
            body_redacted_short="",  # 체크포인트엔 본문 없음
        )
        rep.results.append(mr)
        # 상태 통계
        if st.get("status") == UNREAD_CHANGED_RESTORED:
            rep.unread_state_changed += 1
            rep.unread_restore_attempted += 1
            rep.unread_restore_succeeded += 1
        if st.get("status") in (UNREAD_CHANGED_RESTORED, BODY_READ_OK):
            rep.success += 1
    rep.pii_detected_total = pii_total
    rep.attempted = rep.success

    # 5) 산출
    out = Path("data/inspection/naver_mail_inbox_consolidated_report")
    out.mkdir(parents=True, exist_ok=True)
    md_path = out / "consolidated_business_report.md"
    md_path.write_text(_render_business_report(rep), encoding="utf-8")
    json_path = out / "consolidated_data.json"
    json_path.write_text(
        json.dumps({
            "run_id": rep.run_id,
            "total_results": len(rep.results),
            "by_status": dict(Counter(r.status for r in rep.results)),
            "by_folder": dict(Counter(r.folder_name for r in rep.results)),
            "by_priority": dict(Counter(_classify_priority(r.subject_masked,
                                                           r.sender_masked)
                                        for r in rep.results)),
            "pii_total": rep.pii_detected_total,
            "results_sample": [r.to_dict() for r in rep.results[:30]],
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[done] {md_path}")
    print(f"       {json_path}")
    # 콘솔 sneak peek
    print("\n=== 카테고리 분포 ===")
    cnts = Counter(_classify_priority(r.subject_masked, r.sender_masked)
                   for r in rep.results)
    for p, n in cnts.most_common():
        print(f"  {p:>18}: {n}건")


if __name__ == "__main__":
    main()
