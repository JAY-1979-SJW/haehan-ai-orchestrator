"""건설공무카페 조회수 TOP N 게시글 본문 상세 수집.

data/cafe/gunmu_all_boards/ 의 게시판별 목록 수집 결과(제목/조회수/링크만
있고 본문 없음)를 합쳐 조회수 순으로 정렬한 뒤, 상위 N건만 상세페이지를
직접 방문해 본문·댓글을 채워 개별 저장한다. 전체 36,783건을 다 상세
방문하면 3~4초/건 기준 30시간 이상 걸려 비현실적이므로 범위를 좁힌다.

사용:
    python -m scripts.naver.cafe.collection.collect_top_post_details --top 300
"""

from __future__ import annotations

import argparse
import json
import time

from scripts.common.app_paths import repo_root
from scripts.common.logger import get_logger
from scripts.naver.cafe.collection.collector import _fetch_article_detail

_log = get_logger(__name__)

ROOT = repo_root()
BOARDS_DIR = ROOT / "data" / "cafe" / "gunmu_all_boards"
OUT_DIR = ROOT / "data" / "cafe" / "gunmu_post_details"
CLUB_ID = "10445200"


def _to_int(v) -> int:
    try:
        return int(str(v).replace(",", "").strip() or 0)
    except Exception:  # noqa: BLE001 - 숫자 파싱 실패시 0 반환, 캐시 JSON 파일 로드 실패시 해당 파일만 건너뛰고 계속 — 읽기전용 수집
        return 0


def load_all_posts() -> list[dict]:
    posts = []
    seen = set()
    for fp in BOARDS_DIR.glob("*.json"):
        if fp.name == "_summary.json":
            continue
        # 파일명 형식: {menu_id}_{board_name}.json — board 필드가 비어있는 레코드를 채운다.
        board_name = fp.stem.split("_", 1)[1].replace("_", " ") if "_" in fp.stem else fp.stem
        try:
            items = json.loads(fp.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001 - 숫자 파싱 실패시 0 반환, 캐시 JSON 파일 로드 실패시 해당 파일만 건너뛰고 계속 — 읽기전용 수집
            _log.warning("[collect_top_post_details] 로드 실패 %s: %s", fp, e)
            continue
        for a in items:
            aid = a.get("article_id")
            if not aid or aid in seen:
                continue
            seen.add(aid)
            if not a.get("board"):
                a["board"] = board_name
            posts.append(a)
    return posts


def collect_top_details(page, *, top: int = 300) -> dict:
    posts = load_all_posts()
    posts.sort(key=lambda a: _to_int(a.get("view_count") or a.get("views")), reverse=True)
    targets = posts[:top]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    saved, skipped, failed = 0, 0, 0

    for i, post in enumerate(targets, 1):
        aid = post["article_id"]
        out_path = OUT_DIR / f"{aid}.json"
        if out_path.exists():
            skipped += 1
            continue

        _log.info("[collect_top_post_details] (%d/%d) %s", i, len(targets), post.get("title", "")[:40])
        detail = _fetch_article_detail(page, CLUB_ID, aid)
        if not detail:
            failed += 1
            time.sleep(1.0)
            continue

        record = {**post, **detail, "detail_collected": True}
        out_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        saved += 1
        time.sleep(1.5)

    summary = {"target": len(targets), "saved": saved, "skipped_existing": skipped, "failed": failed}
    (OUT_DIR / "_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def _main() -> None:
    parser = argparse.ArgumentParser(description="조회수 TOP N 게시글 본문 상세 수집")
    parser.add_argument("--top", type=int, default=300)
    args = parser.parse_args()

    from scripts.browser.agent.agent import BrowserAgent

    with BrowserAgent() as agent:
        summary = collect_top_details(agent._page, top=args.top)
        print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    _main()
