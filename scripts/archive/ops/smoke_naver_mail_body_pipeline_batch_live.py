"""NAVER-MAIL-BODY-PIPELINE-BATCH-01 라이브 smoke.

CLI:
  python -m scripts.ops.smoke_naver_mail_body_pipeline_batch_live --limit 10
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from scripts.naver.mail import batch_runner as br
from scripts.naver.mail import smart_folder_collector as sfc
from scripts.naver.mail.read import cdp
from scripts.naver.mail.processing import audit_naver_mail_body_pipeline_batch as audit


class LiveActions:
    def __init__(self, target_id):
        self.target_id = target_id

    def evaluate(self, expr):
        return cdp.evaluate(self.target_id, expr, timeout=10.0)

    def navigate(self, url):
        cdp.navigate(self.target_id, url)

    def wait_dom(self, expr, timeout_s=8.0):
        return cdp.wait_dom(self.target_id, expr, timeout=timeout_s)


def collect_targets(actions: LiveActions) -> list[br.BatchTarget]:
    """smart_folder_collector 로 4개 폴더 unread sn 전부 수집."""
    rpt = sfc.collect_all(actions, max_pages=200, max_items_per_folder=5000)
    targets = []
    for fc in rpt.folders:
        for it in fc.items:
            sn = it.get("sn") if isinstance(it, dict) else it.sn
            if sn:
                targets.append(
                    br.BatchTarget(
                        sn=sn,
                        folder_id=fc.folder_id,
                        folder_name=fc.folder_name,
                    )
                )
    return targets


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--delay", type=float, default=br.DEFAULT_DELAY_S)
    ap.add_argument("--jitter", type=float, default=br.DEFAULT_JITTER_S)
    ap.add_argument("--continue-on-warn", action="store_true")
    ap.add_argument("--out", default="data/inspection/naver_mail_body_pipeline_batch")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    target_id = cdp.ensure_about_blank_target()
    print(f"[boot] target_id={target_id[:12]} limit={args.limit} delay={args.delay}±{args.jitter}")
    actions = LiveActions(target_id)

    # 1) 대상 sn 수집 (smart_folder_coverage 244 재실행)
    print("[1] collecting targets via smart_folder_collector ...")
    t0 = time.time()
    targets = collect_targets(actions)
    print(f"    collected {len(targets)} sns in {round(time.time() - t0, 1)}s")

    # 2) batch 실행
    print("[2] running batch ...")
    ck_path = out_dir / "checkpoint.json"
    rep = br.run_batch(
        actions,
        targets,
        limit=args.limit,
        checkpoint_path=ck_path,
        delay_s=args.delay,
        jitter_s=args.jitter,
        continue_on_warn=args.continue_on_warn,
    )

    # 3) audit
    ck = br.load_checkpoint(ck_path)
    v = audit.judge_batch(rep, checkpoint_dict=ck)
    rep.verdict = v.code

    # 4) 저장
    paths = br.write_outputs(rep, out_dir)
    (out_dir / "audit_result.json").write_text(
        json.dumps(
            {"verdict": v.code, "passed": v.passed, "reasons": v.reasons, "metrics": v.metrics},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("\n=== BATCH REPORT ===")
    print(f"target_total={rep.target_total} duplicate_sn={rep.duplicate_sn_count} limit={rep.limit}")
    print(f"attempted={rep.attempted} success={rep.success} failed={rep.failed} skipped={rep.skipped_already_done}")
    print(
        f"unread state_changed={rep.unread_state_changed} "
        f"restore_attempted={rep.unread_restore_attempted} "
        f"restore_succeeded={rep.unread_restore_succeeded} "
        f"restore_failed={rep.unread_restore_failed}"
    )
    print(f"pii_total={rep.pii_detected_total} types={rep.pii_types_summary}")
    print(f"attachment_download={rep.attachment_download_count} external_ai={rep.external_ai_call_count}")
    print(f"elapsed={rep.elapsed_seconds}s avg={rep.avg_seconds_per_message}s/mail")
    print(f"halted_early={rep.halted_early}  halt_reason={rep.halt_reason}")
    print("\n=== AUDIT ===")
    print(json.dumps({"verdict": v.code, "passed": v.passed, "reasons": v.reasons}, ensure_ascii=False, indent=2))
    print(f"\nsaved → {paths['report']}")


if __name__ == "__main__":
    main()
