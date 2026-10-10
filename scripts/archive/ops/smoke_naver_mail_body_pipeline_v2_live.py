"""NAVER-MAIL-BODY-PIPELINE-V2-01 라이브 smoke.

안전 우선:
  - FULL_READ 모드 max_bodies=2 (사용자 mailbox 영향 최소)
  - 매 본문 후 즉시 안읽음 복구 + 복구 검증
  - 실패 시 즉시 중단
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from scripts.naver.mail import body_pipeline_v2 as bp
from scripts.naver.mail import inbox_collector as ic
from scripts.naver.mail.read import cdp
from scripts.naver.mail.processing import audit_naver_mail_body_pipeline_v2 as audit


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
    out_dir = Path("data/inspection/naver_mail_body_pipeline_v2")
    out_dir.mkdir(parents=True, exist_ok=True)
    target_id = cdp.ensure_about_blank_target()
    print(f"[boot] target_id={target_id[:12]}")
    actions = LiveActions(target_id)

    # 1) 받은편지함 unread 목록에서 sn 2개 채취
    actions.navigate("https://mail.naver.com/v2/folders/0/unread")
    time.sleep(3.5)
    actions.wait_dom("document.querySelector('li.mail_item')", timeout_s=15.0)
    list_payload = actions.evaluate(ic.LIST_EXPR) or {}
    items = list_payload.get("items", []) if isinstance(list_payload, dict) else []
    if not items:
        print("[FAIL] unread mail list empty — abort")
        return
    targets = [
        bp.TargetMail(sn=it.get("sn", ""), folder_id="0", folder_name="받은메일함") for it in items if it.get("sn")
    ][:2]
    print(f"[1] targets: {[t.sn for t in targets]}")

    # 2) 본문 진입 + 복구 + 감사
    rpt = bp.run(actions, targets, mode=bp.MODE_FULL_READ, max_bodies=2)
    v = audit.judge(rpt)
    rpt.verdict = v.code

    # 3) 저장
    paths = bp.write_outputs(rpt, out_dir)
    (out_dir / "audit_result.json").write_text(
        json.dumps(
            {"verdict": v.code, "passed": v.passed, "reasons": v.reasons, "metrics": v.metrics},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    # 4) 콘솔 보고
    print("\n=== BODY PIPELINE V2 ===")
    print(f"mode={rpt.mode}")
    print(f"attempt={rpt.attempt_count} success={rpt.success_count} failure={rpt.failure_count}")
    print(
        f"unread_audit: state_changed={rpt.unread_audit.get('state_changed')} "
        f"restore_attempted={rpt.unread_audit.get('restore_attempted')} "
        f"restore_succeeded={rpt.unread_audit.get('restore_succeeded')} "
        f"restore_failed={rpt.unread_audit.get('restore_failed')}"
    )
    print(
        f"attachment_download_count={rpt.attachment_download_count} external_ai_call_count={rpt.external_ai_call_count}"
    )
    print("\nbodies:")
    for b in rpt.bodies:
        print(
            f"  sn={b.sn} folder={b.folder_name} open_ok={b.open_ok} "
            f"pii_n={b.pii_detected_count} hash={b.masked_text_hash} "
            f"restore_ok={b.unread_audit.get('restore_ok')}"
        )
    print(f"\nverdict: {v.code}  passed={v.passed}")
    print(f"\nsaved → {paths['report']}")


if __name__ == "__main__":
    main()
