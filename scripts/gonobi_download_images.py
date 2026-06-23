"""gonobi 이미지 전체 다운로드 — 분류별 폴더로 저장.

저장 경로: data/gonobi_images/{분류}/{log_no}_{n}.jpg
"""

import logging
import re
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.naver.blog.gonobi.db import open_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

OUT_BASE = Path("data/gonobi_images")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://blog.naver.com/gonobi",
}


def safe_name(s: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', "_", s)[:50]


def download_images():
    session = requests.Session()
    session.headers.update(HEADERS)

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

            folder = OUT_BASE / safe_name(category)
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

                try:
                    # ?type=w966 → 네이버 postfiles 최대 해상도
                    fetch_url = url.split("?")[0] + "?type=w966"
                    resp = session.get(fetch_url, timeout=10)
                    if resp.status_code == 200:
                        filename.write_bytes(resp.content)
                        total_downloaded += 1
                    else:
                        total_errors += 1
                except Exception as e:
                    logger.warning("다운로드 실패 %s: %s", url[:60], e)
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
    for folder in sorted(OUT_BASE.iterdir()):
        if folder.is_dir():
            cnt = len(list(folder.glob("*")))
            print(f"  {folder.name:15} {cnt}개")

    return total_downloaded


if __name__ == "__main__":
    download_images()
