"""gonobi 이미지 전체 다운로드 — 분류별 폴더로 저장.

저장 경로: data/gonobi_images/{분류}/{log_no}_{n}.jpg
"""

import logging
import re
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from ai_orchestrator.core.config import get_local_data_dir
from scripts.naver.blog.gonobi.db import open_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)


def get_out_base():
    return get_local_data_dir() / "gonobi_images"


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://blog.naver.com/gonobi",
}


def safe_name(s: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', "_", s)[:50]


def _fetch_image(session, url: str, filename) -> bool:
    """이미지 1장 다운로드. 저장 성공이면 True, 비200/예외면 False(예외는 경고 로그)."""
    try:
        # ?type=w966 → 네이버 postfiles 최대 해상도
        fetch_url = url.split("?")[0] + "?type=w966"
        resp = session.get(fetch_url, timeout=10)
        if resp.status_code == 200:
            filename.write_bytes(resp.content)
            return True
        return False
    except Exception as e:  # noqa: BLE001 - 이미지 다운로드 실패를 카운트하고 경고 로그 남긴 뒤 계속 진행 - 읽기전용 다운로드 스크립트, 실패 건수만 집계될 뿐 위험 조작 없음
        logger.warning("다운로드 실패 %s: %s", url[:60], e)
        return False


def download_images():
    session = requests.Session()
    session.headers.update(HEADERS)
    out_base = get_out_base()

    with open_db() as conn:
        posts = conn.execute("SELECT log_no, title, our_category FROM gonobi_posts").fetchall()

        total_posts = len(posts)
        total_downloaded = 0
        total_skipped = 0
        total_errors = 0

        for idx, post in enumerate(posts, 1):
            log_no = post["log_no"]
            title = safe_name(post["title"])
            category = post["our_category"] or "기타"

            images = conn.execute("SELECT image_url FROM gonobi_images WHERE log_no=?", (log_no,)).fetchall()

            if not images:
                continue

            folder = out_base / safe_name(category)
            folder.mkdir(parents=True, exist_ok=True)

            for n, img_row in enumerate(images, 1):
                url = img_row["image_url"]
                ext = url.split(".")[-1].split("?")[0].lower()
                if ext not in ("jpg", "jpeg", "png", "gif", "webp"):
                    ext = "jpg"
                filename = folder / f"{log_no}_{n:02d}_{title}.{ext}"

                if filename.exists():
                    total_skipped += 1
                    continue

                if _fetch_image(session, url, filename):
                    total_downloaded += 1
                else:
                    total_errors += 1

                time.sleep(0.1)

            if idx % 50 == 0:
                logger.info(
                    "[%d/%d] 다운로드:%d 스킵:%d 오류:%d",
                    idx,
                    total_posts,
                    total_downloaded,
                    total_skipped,
                    total_errors,
                )

    logger.info("완료 — 다운로드:%d 스킵:%d 오류:%d", total_downloaded, total_skipped, total_errors)

    # 폴더별 결과 출력
    print("\n=== 폴더별 이미지 수 ===")
    for folder in sorted(out_base.iterdir()):
        if folder.is_dir():
            cnt = len(list(folder.glob("*")))
            print(f"  {folder.name:15} {cnt}개")

    return total_downloaded


if __name__ == "__main__":
    download_images()
