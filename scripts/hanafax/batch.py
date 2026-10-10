"""하나팩스 대량 발송 배치 모듈.

큐 파일(JSONL) 기반으로 순차 발송. 건당 딜레이로 하나팩스 과부하 방지.

큐 파일 형식 (data/hanafax_queue.jsonl):
    {"receiver_fax": "02-1234-5678", "receiver_name": "ABC건설", "subject": "공고명 외주 문의", "body": "...", "bid_name": "공고명"}
    ...

사용:
    python scripts/entry/cdp_cli.py hanafax batch-send [--limit=N] [--delay=30] [--dry-run]
    python scripts/entry/cdp_cli.py hanafax batch-send --approved --confirm=HANAFAX_APPROVED_BATCH
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from ai_orchestrator.paths.runtime import data_dir
from scripts.common.app_paths import repo_root

ROOT = repo_root()
DATA_DIR = data_dir()
DEFAULT_QUEUE = DATA_DIR / "hanafax_queue.jsonl"
BATCH_RESULT_DIR = DATA_DIR / "hanafax_batch_results"
LATEST_RESULT_PATH = DATA_DIR / "hanafax_batch_result_latest.json"

APPROVAL_CONFIRM_TEXT = "HANAFAX_APPROVED_BATCH"


def load_queue(path: Path = DEFAULT_QUEUE, limit: int = 10) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"팩스 큐 파일 없음: {path}")
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        if row.get("status", "pending") == "pending":
            rows.append(row)
        if len(rows) >= limit:
            break
    return rows


def build_batch_plan(
    queue_path: Path = DEFAULT_QUEUE,
    limit: int = 10,
    delay_seconds: int = 30,
) -> dict[str, Any]:
    """발송 플랜 생성 (dry-run용)."""
    # 큐 파일이 아직 없으면 빈 계획(0건)으로 처리 — dry-run 은 크래시 대신 빈 결과 반환.
    try:
        rows = load_queue(queue_path, limit=limit)
    except FileNotFoundError:
        rows = []
    items = [
        {
            "index": i + 1,
            "receiver_fax": row["receiver_fax"],
            "receiver_name": row.get("receiver_name", ""),
            "subject": row["subject"],
            "body": row.get("body", row["subject"]),
            "bid_name": row.get("bid_name", ""),
            "attach_file": row.get("attach_file"),
            "delay_seconds": delay_seconds,
            "status": "planned",
        }
        for i, row in enumerate(rows)
    ]
    return {
        "timestamp": datetime.now().isoformat(),
        "mode": "dry_run_plan",
        "provider": "hanafax",
        "queue_path": str(queue_path),
        "selected": len(items),
        "delay_seconds": delay_seconds,
        "send_status": "not_sent",
        "items": items,
    }


def execute_batch(plan: dict[str, Any]) -> dict[str, Any]:
    """승인된 배치 발송 실행. 1건씩 순차 전송."""
    from scripts.hanafax.sender import send_fax

    items = plan.get("items", [])
    results = []
    sent = failed = 0

    for item in items:
        result_item: dict[str, Any] = {
            "index": item["index"],
            "receiver_fax": item["receiver_fax"],
            "receiver_name": item.get("receiver_name", ""),
            "subject": item["subject"],
            "sent": False,
            "job_id": None,
            "error": None,
            "timestamp": datetime.now().isoformat(),
        }
        try:
            r = send_fax(
                receiver_fax=item["receiver_fax"],
                subject=item["subject"],
                body=item.get("body", item["subject"]),
                receiver_name=item.get("receiver_name", ""),
                bid_name=item.get("bid_name", ""),
                attach_file=item.get("attach_file"),
            )
            result_item["sent"] = r.get("success", False)
            result_item["job_id"] = r.get("job_id")
            if result_item["sent"]:
                sent += 1
            else:
                failed += 1
                result_item["error"] = r.get("message", "send_failed")
        except Exception as e:  # noqa: BLE001 - 팩스 일괄발송 결과 집계 루프 - 개별 발송 실패는 failed 카운트 증가와 error 메시지 기록만, 성공으로 잘못 표시하지 않음
            failed += 1
            result_item["error"] = str(e)

        results.append(result_item)

        # 마지막 항목이 아닐 때 딜레이
        if item["index"] < len(items):
            time.sleep(item.get("delay_seconds", 30))

    result = {
        "timestamp": datetime.now().isoformat(),
        "mode": "executed",
        "provider": "hanafax",
        "selected": len(items),
        "sent": sent,
        "failed": failed,
        "items": results,
        "send_status": "done",
    }
    _save_result(result)
    return result


def _save_result(result: dict[str, Any]) -> None:
    BATCH_RESULT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = BATCH_RESULT_DIR / f"hanafax_batch_{stamp}.json"
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    path.write_text(payload, encoding="utf-8")
    LATEST_RESULT_PATH.write_text(payload, encoding="utf-8")


def print_plan(plan: dict[str, Any], path: Path | None = None) -> None:
    print("=" * 60)
    print("하나팩스 배치 발송 플랜 (dry-run)")
    print("=" * 60)
    print(f"대상: {plan['selected']}건  딜레이: {plan['delay_seconds']}초/건")
    print(f"상태: {plan['send_status']}")
    for item in plan["items"]:
        print(f"  #{item['index']:>2} {item['receiver_name']:<16} {item['receiver_fax']}  | {item['subject'][:40]}")
    if path:
        print(f"저장: {path}")


def print_result(result: dict[str, Any]) -> None:
    print("=" * 60)
    print("하나팩스 배치 발송 결과")
    print("=" * 60)
    print(f"전송: {result['sent']}건  실패: {result['failed']}건  전체: {result['selected']}건")
    for item in result["items"]:
        mark = "✓" if item["sent"] else "✗"
        err = f" [{item['error']}]" if item.get("error") else ""
        jid = f" (접수: {item['job_id']})" if item.get("job_id") else ""
        print(f"  {mark} #{item['index']:>2} {item['receiver_name']:<16} {item['receiver_fax']}{jid}{err}")
