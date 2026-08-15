"""건설공무 카페 신규 게시글 일일 누적 스니펫.

목적: "며칠 지켜보며 패턴 확정" 요청에 대응 — 매일 당일(days=0) 신규 게시글을
본문/댓글까지 상세 수집해 누적 JSONL에 append한다. article_id 기준으로
같은 날 중복 실행해도 중복 저장하지 않는다.

CDP 브라우저(9222, 카페 로그인 세션)가 떠 있어야 동작한다. 로그인이 끊겼거나
브라우저가 없으면 예외를 던지고 그날은 건너뛴다(다음날 재시도로 자연 복구).
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from scripts.common.data_paths import get_app_dir

CAFE_URL = "https://cafe.naver.com/0moo"
_OUT_PATH = get_app_dir("cafe") / "건설공무_daily_accumulated.jsonl"


def _load_existing_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    ids: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        aid = row.get("article_id")
        snapshot_date = row.get("snapshot_date")
        if aid and snapshot_date:
            ids.add(f"{snapshot_date}:{aid}")
    return ids


def run_daily_snapshot(page: Any, *, out_path: Path | None = None) -> dict[str, Any]:
    """오늘 신규 게시글을 상세 수집해 누적 파일에 append.

    Args:
        page: Playwright Page (connect_over_cdp 로 얻은, 로그인된 카페 세션).
        out_path: 누적 JSONL 경로. None이면 기본 경로.

    Returns:
        {"snapshot_date", "collected", "new_appended", "skipped_duplicate", "out_path"}
    """
    from scripts.naver.cafe.collection.collector import collect_articles

    path = out_path or _OUT_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()

    articles = collect_articles(page, CAFE_URL, days=0, max_pages=5, max_detail=30)

    existing = _load_existing_ids(path)
    new_rows: list[dict[str, Any]] = []
    for art in articles:
        key = f"{today}:{art.get('article_id')}"
        if key in existing:
            continue
        row = dict(art)
        row["snapshot_date"] = today
        new_rows.append(row)
        existing.add(key)

    if new_rows:
        with path.open("a", encoding="utf-8") as f:
            for row in new_rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    return {
        "snapshot_date": today,
        "collected": len(articles),
        "new_appended": len(new_rows),
        "skipped_duplicate": len(articles) - len(new_rows),
        "out_path": str(path),
    }
