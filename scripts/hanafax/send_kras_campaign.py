"""
scripts/hanafax/send_kras_campaign.py

"안전서류(KRAS) 전용 사이트 구축" 영업팩스 — 대상 목록 기반 개인화 발송.

대상 데이터: g2b 프로젝트가 만든 safety_doc_targets_*.json
    (C:\\work\\05. g2b\\scripts\\sales\\scan_safety_doc_targets.py 산출물,
     서버 /nas/g2b/sales/scans/ 에 있음 — 로컬로 내려받아 --data 로 지정)

각 업체마다 kras_campaign_template.build_docx() 로 개인화 docx를 만들고
scripts.hanafax.sender.send_fax() 로 단건 발송한다(개인화라 bulk 불가 —
send_fax_bulk 은 동일 파일만 여러 곳에 보낼 수 있다).

사용:
    # 미리보기만 (발송 없음) — 처음 3건 docx 생성해서 확인
    python scripts/hanafax/send_kras_campaign.py --data <json경로> --preview 3

    # 실제 발송 (소량 테스트 권장: --limit 5)
    python scripts/hanafax/send_kras_campaign.py --data <json경로> --limit 5 --send

전송 로그는 data/kras_fax_sent_log.json 에 누적 기록한다(중복발송 방지 —
이미 성공한 bizno는 재발송 전 건너뛴다. --force 로 무시 가능).
"""

from __future__ import annotations

import argparse
import json
import logging
import tempfile
import time
from pathlib import Path

from scripts.common.app_paths import repo_root
from scripts.hanafax.kras_campaign_template import build_docx
from scripts.hanafax.sender import send_fax

log = logging.getLogger("hanafax.kras_campaign")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

ROOT = repo_root()
SENT_LOG = ROOT / "data" / "kras_fax_sent_log.json"
SUBJECT = "귀사만을 위한 AI 안전관리시스템 안내"


def _load_sent_log() -> dict:
    if SENT_LOG.exists():
        return json.loads(SENT_LOG.read_text(encoding="utf-8"))
    return {}


def _save_sent_log(log_data: dict) -> None:
    SENT_LOG.write_text(json.dumps(log_data, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, help="safety_doc_targets_*.json 로컬 경로")
    ap.add_argument("--preview", type=int, default=0, help="이 수만큼 docx만 생성(발송 없음), 경로 출력")
    ap.add_argument("--limit", type=int, default=0, help="실제 발송 건수 상한 (0=전체)")
    ap.add_argument("--send", action="store_true", help="실제 발송 실행 (없으면 무조건 dry-run)")
    ap.add_argument("--force", action="store_true", help="이미 성공 기록된 bizno도 재발송")
    args = ap.parse_args()

    data = json.loads(Path(args.data).read_text(encoding="utf-8"))
    rows = [r for r in data["data"] if r.get("fax_no")]
    log.info("대상 %d개 업체 중 팩스번호 보유 %d개", len(data["data"]), len(rows))

    if args.preview:
        out_dir = Path(tempfile.mkdtemp(prefix="kras_fax_preview_"))
        for r in rows[: args.preview]:
            path = build_docx(r["corp_nm"], r.get("contract_name") or "", str(out_dir / f"{r['bizno']}.docx"))
            print(f"[미리보기] {r['corp_nm']} ({r['bizno']}) → {path}")
        return

    if not args.send:
        log.info("dry-run 모드(--send 없음) — 실제 발송하지 않습니다. 대상 %d건만 나열합니다.", args.limit or len(rows))
        for r in rows[: args.limit or len(rows)]:
            print(f"  {r['corp_nm']} ({r['bizno']}) fax={r['fax_no']} 공사={r.get('contract_name')}")
        return

    sent_log = _load_sent_log()
    targets = rows[: args.limit] if args.limit else rows
    n_ok, n_fail, n_skip = 0, 0, 0

    for r in targets:
        bizno = r["bizno"]
        if not args.force and sent_log.get(bizno, {}).get("success"):
            n_skip += 1
            continue

        with tempfile.TemporaryDirectory() as tmpd:
            docx_path = build_docx(r["corp_nm"], r.get("contract_name") or "", str(Path(tmpd) / f"{bizno}.docx"))
            result = send_fax(
                receiver_fax=r["fax_no"],
                subject=SUBJECT,
                body="",
                receiver_name=r["corp_nm"],
                bid_name=r.get("contract_name") or "",
                attach_file=docx_path,
            )

        sent_log[bizno] = {
            "corp_nm": r["corp_nm"],
            "fax_no": r["fax_no"],
            "success": result.get("success", False),
            "message": result.get("message"),
            "job_id": result.get("job_id"),
            "sent_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        _save_sent_log(sent_log)  # 매건 저장 — 중간에 끊겨도 유실 없음

        if result.get("success"):
            n_ok += 1
            log.info("[성공] %s (%s) job_id=%s", r["corp_nm"], r["fax_no"], result.get("job_id"))
        else:
            n_fail += 1
            log.warning("[실패] %s (%s): %s", r["corp_nm"], r["fax_no"], result.get("message"))

        time.sleep(2)  # 하나팩스 서버 부하 방지 — 연속 전송 간 최소 간격

    log.info("완료: 성공 %d건 / 실패 %d건 / 스킵(기발송) %d건", n_ok, n_fail, n_skip)


if __name__ == "__main__":
    main()
