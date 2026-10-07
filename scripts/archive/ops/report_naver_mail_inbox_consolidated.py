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
from collections import Counter
from pathlib import Path

from scripts.naver.mail import business_report as br
from scripts.naver.mail import pii_mask

# scripts/naver/mail/batch_runner.py 는 `from ...processing.batch_runner import *` 인
# 얇은 이동 shim이라 __all__ 이 없으면 밑줄 시작 이름(_classify_priority 등)은
# 재노출되지 않는다(Python의 import * 기본 규칙). 여기서 필요한 두 이름은 밑줄
# 시작이라 shim을 거치지 않고 실제 모듈에서 바로 가져온다(2026-09-29, defect #32).
from scripts.naver.mail.processing.batch_runner import (
    BODY_READ_OK,
    UNREAD_CHANGED_RESTORED,
    BatchReport,
    MailResult,
    _classify_priority,
    _render_business_report,
)
from scripts.naver.mail.analysis import audit_naver_mail_business_report as audit_br


def _load_json(p: Path) -> dict:
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - 네이버 메일함 통합 리포트 — 체크포인트 JSON 로드 실패 시 빈 dict를 반환하는 안전한 기본값(선택적 상태 파일), 읽기전용 리포트 생성.
        return {}


def _meta_from_list(list_old):
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
    return sn_meta


def _merge_smart_meta(smart_dir, sn_meta):
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


def _build_report(sn_status, sn_meta):
    rep = BatchReport()
    rep.run_id = "consolidated"
    rep.target_total = len(sn_status)
    pii_total = 0
    pii_types_total: Counter[str] = Counter()  # noqa: F841
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
    return rep


def _write_legacy_json(out, rep):
    json_path = out / "consolidated_data.json"
    json_path.write_text(
        json.dumps(
            {
                "run_id": rep.run_id,
                "total_results": len(rep.results),
                "by_status": dict(Counter(r.status for r in rep.results)),
                "by_folder": dict(Counter(r.folder_name for r in rep.results)),
                "by_priority": dict(
                    Counter(_classify_priority(r.subject_masked, r.sender_masked) for r in rep.results)
                ),
                "pii_total": rep.pii_detected_total,
                "results_sample": [r.to_dict() for r in rep.results[:30]],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return json_path


def _build_mail_items(rep, sn_meta):
    mail_items = []
    seen_sns: set[str] = set()
    for mr in rep.results:
        mail_items.append(
            br.MailItem(
                sn=mr.sn,
                folder_name=mr.folder_name,
                subject_masked=mr.subject_masked,
                sender_masked=mr.sender_masked,
                date_text=mr.date_text,
                body_redacted_short=mr.body_redacted_short,
                has_attach=mr.has_attach,
                pii_detected_count=mr.pii_detected_count,
                link_domains={},
            )
        )
        seen_sns.add(mr.sn)
    # 추가: 5/20 list 에 있지만 batch checkpoint 에 없는 메일 (이미 사용자가 읽은 메일)
    # — 이 메일들도 보고서 분류 대상에 포함해야 ATTENTION/REVIEW 가 누락되지 않음
    for sn, meta in sn_meta.items():
        if sn in seen_sns:
            continue
        subj = meta.get("subject", "")
        sender = meta.get("sender_full") or meta.get("sender_name", "")
        mail_items.append(
            br.MailItem(
                sn=sn,
                folder_name=meta.get("folder_name", "받은메일함") + "(읽음)",
                subject_masked=pii_mask.mask(subj).masked_text[:300],
                sender_masked=pii_mask.mask(sender).masked_text[:200],
                date_text=meta.get("time_txt", ""),
                body_redacted_short="",
                has_attach=False,
                pii_detected_count=0,
                link_domains={},
            )
        )
    return mail_items


def _build_business_report(rep, mail_items):
    biz_rep = br.build_report(
        mail_items,
        run_id="closeout_consolidated",
        unread_restore_summary={
            "state_changed": rep.unread_state_changed,
            "restore_attempted": rep.unread_restore_attempted,
            "restore_succeeded": rep.unread_restore_succeeded,
            "restore_failed": rep.unread_restore_failed,
        },
        attachment_download_count=0,
        external_ai_call_count=0,
        pii_detected_total=rep.pii_detected_total,
    )
    md = br.render_markdown(biz_rep)
    js = json.dumps(br.render_json(biz_rep), ensure_ascii=False, indent=2)
    biz_rep = br.attach_leak_check(biz_rep, md_text=md, json_text=js)
    # leak self-check 반영된 최종 json 재직렬화
    js = json.dumps(br.render_json(biz_rep), ensure_ascii=False, indent=2)
    return biz_rep, md, js


def _write_v2_files(out, md, js, biz_rep):
    md2 = out / "consolidated_business_report_v2.md"
    js2 = out / "consolidated_business_report_v2.json"
    md2.write_text(md, encoding="utf-8")
    js2.write_text(js, encoding="utf-8")

    # action_items 따로 + category_summary 따로
    ai = out / "action_items.json"
    ai.write_text(
        json.dumps([a.to_dict() for a in biz_rep.action_items], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    cs = out / "category_summary.json"
    cs.write_text(
        json.dumps({cg.category: cg.count for cg in biz_rep.categories}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return md2, js2, ai, cs


def _write_audit(out, biz_rep, md, js):
    v = audit_br.judge_report(biz_rep, md_text=md, json_text=js)
    audit_path = out / "audit_business_report.json"
    audit_path.write_text(
        json.dumps(
            {
                "verdict": v.code,
                "passed": v.passed,
                "reasons": v.reasons,
                "metrics": v.metrics,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return v, audit_path


def main():
    base = Path("data/inspection")
    ck = _load_json(base / "naver_mail_body_pipeline_batch/checkpoint.json")
    list_old = _load_json(base / "mail_20260520/mail_unread_report.json")
    smart_dir = base / "naver_mail_smart_folder_coverage/folder_results"

    # 1) checkpoint sn → status, hash, pii_count
    sn_status = ck.get("sn_to_status", {})

    # 2) 5/20 list — 제목/발신자/날짜 (이미 마스킹된 상태)
    sn_meta = _meta_from_list(list_old)

    # 3) smart_folder_coverage — 스마트폴더의 sn → meta
    _merge_smart_meta(smart_dir, sn_meta)

    # 4) MailResult 합성 — 체크포인트 + meta JOIN
    rep = _build_report(sn_status, sn_meta)

    # 5) 산출 (구버전 — 호환)
    out = Path("data/inspection/naver_mail_inbox_consolidated_report")
    out.mkdir(parents=True, exist_ok=True)
    md_path = out / "consolidated_business_report.md"
    md_path.write_text(_render_business_report(rep), encoding="utf-8")
    json_path = _write_legacy_json(out, rep)
    # 6) 신규 정식 모듈로 보고서 재생성 (business_report)
    mail_items = _build_mail_items(rep, sn_meta)
    biz_rep, md, js = _build_business_report(rep, mail_items)

    md2, js2, ai, cs = _write_v2_files(out, md, js, biz_rep)

    # audit
    v, audit_path = _write_audit(out, biz_rep, md, js)

    print(f"[done] (v1) {md_path}")
    print(f"       (v1) {json_path}")
    print(f"       (v2) {md2}")
    print(f"       (v2) {js2}")
    print(f"       action_items: {ai}")
    print(f"       category_summary: {cs}")
    print(f"       audit: {audit_path}  → {v.code}  passed={v.passed}")
    # 콘솔 sneak peek
    print("\n=== 카테고리 분포 ===")
    cnts = Counter(_classify_priority(r.subject_masked, r.sender_masked) for r in rep.results)
    for p, n in cnts.most_common():
        print(f"  {p:>18}: {n}건")


if __name__ == "__main__":
    main()
