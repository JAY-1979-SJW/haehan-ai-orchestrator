"""건설공무카페 전체 게시판 순회 수집.

configs/cafe_gunmu_boards.json 에 저장된 게시판 목록(cafe_explorer.py boards
명령으로 라이브 조회 후 고정한 스냅샷)을 기준으로 게시판마다
collector.collect_articles(menu_id=...) 를 호출해 게시판별 JSON을
data/cafe/gunmu_all_boards/ 에 저장한다.

"전체글보기" 뷰는 네이버 카페 조회 페이지 상한(약 150p)에 걸려 과거 글을
못 가져오는 문제가 있었다(scripts/_backfill_by_board.py, 삭제됨 — 일회성
스크립트였음). 이 스크립트는 게시판별로 개별 스코프 수집해 그 문제를
우회하고, 재사용 가능한 정식 자산으로 남긴다.

사용:
    python -m scripts.naver.cafe.collection.collect_all_boards --days 400
    python -m scripts.naver.cafe.collection.collect_all_boards --days 400 --board-menu-id 202  # 특정 게시판만
    python -m scripts.naver.cafe.collection.collect_all_boards --refresh-boards  # 게시판 목록부터 다시 조회
"""

from __future__ import annotations

import argparse
import json
import time

from scripts.common.app_paths import repo_root
from scripts.common.logger import get_logger
from scripts.naver.cafe.collection.collector import collect_articles

_log = get_logger(__name__)

ROOT = repo_root()
BOARD_CONFIG = ROOT / "configs" / "cafe_gunmu_boards.json"
OUT_DIR = ROOT / "data" / "cafe" / "gunmu_all_boards"

# 이미지/앨범형 게시판(boardtype=I)은 목록 DOM 구조가 달라 collect_articles로
# 파싱 불가 — 별도 photos 수집기(cafe_explorer.py photos)가 필요. 여기서는 skip.
_SKIP_BOARD_TYPES = {"I"}


def load_board_config() -> dict:
    return json.loads(BOARD_CONFIG.read_text(encoding="utf-8"))


def refresh_board_config(agent, cafe_url: str) -> dict:
    """카페 게시판 목록을 라이브로 재조회해 config 파일을 갱신.

    Args:
        agent: BrowserAgent 인스턴스(cafe_boards 메서드 보유).
    """
    boards = agent.cafe_boards(cafe_url)

    cfg = load_board_config()
    cfg["boards"] = [
        {
            "menu_id": b["menu_id"],
            "name": b["name"],
            "board_type": b["href"].split("boardtype=")[-1] if "boardtype=" in b.get("href", "") else "L",
        }
        for b in boards
        if b.get("menu_id")
    ]
    BOARD_CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    _log.info("[collect_all_boards] 게시판 목록 갱신: %d개", len(cfg["boards"]))
    return cfg


def collect_all(
    page,
    *,
    days: int = 400,
    max_pages: int = 400,
    max_detail: int = 0,
    only_menu_id: str = "",
) -> dict:
    """설정된 전체 게시판(또는 only_menu_id 하나)을 순회 수집.

    Returns: {"boards": [{"menu_id", "name", "count", "path"}], "total": int}
    """
    cfg = load_board_config()
    cafe_url = cfg["cafe_url"]
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    results = []
    total = 0
    for b in cfg["boards"]:
        if only_menu_id and b["menu_id"] != only_menu_id:
            continue
        if b.get("board_type") in _SKIP_BOARD_TYPES:
            _log.info("[collect_all_boards] skip(이미지게시판): %s", b["name"])
            continue

        safe_name = b["name"].replace("/", "_").replace(" ", "_")
        out_path = OUT_DIR / f"{b['menu_id']}_{safe_name}.json"

        _log.info("[collect_all_boards] 수집 시작: %s (menu_id=%s)", b["name"], b["menu_id"])
        try:
            articles = collect_articles(
                page,
                cafe_url=cafe_url,
                days=days,
                max_pages=max_pages,
                max_detail=max_detail,
                menu_id=b["menu_id"],
                save_path=str(out_path),
            )
        except Exception as e:  # noqa: BLE001 - 카페 게시판별 전체 수집 루프(읽기전용) - 개별 게시판 수집 실패는 경고 로그 후 continue로 다음 게시판 계속 진행
            _log.warning("[collect_all_boards] 수집 실패 %s: %s", b["name"], e)
            continue

        results.append({"menu_id": b["menu_id"], "name": b["name"], "count": len(articles), "path": str(out_path)})
        total += len(articles)
        _log.info("[collect_all_boards] 완료: %s — %d건", b["name"], len(articles))
        time.sleep(1.5)  # 게시판 전환 사이 부하 분산

    summary = {"total": total, "boards": results}
    (OUT_DIR / "_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def _main() -> None:
    parser = argparse.ArgumentParser(description="건설공무카페 전체 게시판 순회 수집")
    parser.add_argument("--days", type=int, default=400, help="수집 기간(일), 기본 400일")
    parser.add_argument("--max-pages", type=int, default=400, help="게시판당 최대 페이지 수")
    parser.add_argument("--max-detail", type=int, default=0, help="상세 방문 글 수(0=목록만, 조회수 포함)")
    parser.add_argument("--board-menu-id", default="", help="특정 게시판만 수집(menu_id)")
    parser.add_argument("--refresh-boards", action="store_true", help="게시판 목록을 라이브로 다시 조회 후 저장")
    args = parser.parse_args()

    from scripts.browser.agent.agent import BrowserAgent

    with BrowserAgent() as agent:
        page = agent._page
        if args.refresh_boards:
            cfg = load_board_config()
            refresh_board_config(agent, cfg["cafe_url"])

        summary = collect_all(
            page,
            days=args.days,
            max_pages=args.max_pages,
            max_detail=args.max_detail,
            only_menu_id=args.board_menu_id,
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    _main()
