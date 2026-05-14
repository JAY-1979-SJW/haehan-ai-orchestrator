"""Hiworks one-recipient-at-a-time sales mail batch planning."""
from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
DEFAULT_QUEUE = DATA_DIR / "eum_sales_mail_queue_latest.jsonl"


@dataclass(frozen=True)
class BatchItem:
    index: int
    to: str
    subject: str
    delay_seconds: int
    status: str
    metadata: dict[str, Any]


def load_pending_queue(path: str | Path = DEFAULT_QUEUE, limit: int = 10) -> list[dict[str, Any]]:
    queue_path = Path(path)
    if not queue_path.exists():
        raise FileNotFoundError(f"queue not found: {queue_path}")
    rows: list[dict[str, Any]] = []
    for line in queue_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("status", "pending") == "pending":
            rows.append(row)
        if len(rows) >= limit:
            break
    return rows


def build_send_plan(
    *,
    queue_path: str | Path = DEFAULT_QUEUE,
    limit: int = 5,
    delay_min: int = 15,
    delay_max: int = 45,
    seed: int | None = 20260513,
) -> dict[str, Any]:
    """Build a safe one-recipient-per-message send plan."""
    if delay_min < 1:
        raise ValueError("delay_min must be >= 1")
    if delay_max < delay_min:
        raise ValueError("delay_max must be >= delay_min")
    rng = random.Random(seed)
    rows = load_pending_queue(queue_path, limit=limit)
    items = [
        BatchItem(
            index=idx,
            to=row["to"],
            subject=row["subject"],
            delay_seconds=rng.randint(delay_min, delay_max),
            status="planned",
            metadata=row.get("metadata") or {},
        )
        for idx, row in enumerate(rows, start=1)
    ]
    return {
        "timestamp": datetime.now().isoformat(),
        "mode": "dry_run_plan",
        "provider": "hiworks",
        "send_unit": "one_recipient_per_message",
        "queue_path": str(queue_path),
        "limit": limit,
        "delay_min": delay_min,
        "delay_max": delay_max,
        "selected": len(items),
        "items": [asdict(item) for item in items],
        "send_status": "not_sent",
    }


def save_send_plan(plan: dict[str, Any], output_dir: str | Path = DATA_DIR) -> Path:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"hiworks_sales_mail_send_plan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    latest = out_dir / "hiworks_sales_mail_send_plan_latest.json"
    latest.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def print_send_plan(plan: dict[str, Any], path: Path | None = None) -> None:
    print("=" * 60)
    print("Hiworks sales-mail send plan")
    print("=" * 60)
    print(f"mode: {plan.get('mode')}")
    print(f"send unit: {plan.get('send_unit')}")
    print(f"selected: {plan.get('selected')}")
    print(f"delay: {plan.get('delay_min')}~{plan.get('delay_max')} sec")
    print(f"send status: {plan.get('send_status')}")
    for item in plan.get("items", []):
        print(f"- #{item['index']} {item['to']} delay={item['delay_seconds']}s | {item['subject']}")
    if path:
        print(f"saved: {path}")
