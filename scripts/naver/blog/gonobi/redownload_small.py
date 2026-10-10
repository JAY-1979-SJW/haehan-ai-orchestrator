"""10KB 미만 이미지만 골라서 재다운로드."""

import logging
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from ai_orchestrator.core.config import get_local_data_dir

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://blog.naver.com/gonobi",
}
MIN_SIZE = 10_000  # 10KB


def _collect_small_files(base) -> list:
    """MIN_SIZE 미만 파일 목록 수집."""
    small_files = []
    for folder in base.iterdir():
        if folder.is_dir():
            for f in folder.glob("*"):
                if f.stat().st_size < MIN_SIZE:
                    small_files.append(f)
    return small_files


def _resolve_image_url(fpath) -> str | None:
    """파일명({log_no}_{n}_...)으로 DB 에서 원본 URL 을 찾아 w966 URL 반환. 못 찾으면 None."""
    # 파일명에서 log_no 추출
    log_no = fpath.stem.split("_")[0]

    # DB에서 해당 포스트의 이미지 URL 순번 파악
    n_str = fpath.stem.split("_")[1]
    try:
        n = int(n_str) - 1  # 0-indexed
    except ValueError:
        return None

    # DB에서 URL 가져오기
    from scripts.naver.blog.gonobi.db import open_db

    with open_db() as conn:
        rows = conn.execute("SELECT image_url FROM gonobi_images WHERE log_no=? ORDER BY id", (log_no,)).fetchall()

    if n >= len(rows):
        return None

    return rows[n]["image_url"].split("?")[0] + "?type=w966"


def _redownload(session, url: str, fpath) -> bool:
    """URL 을 받아 fpath 에 덮어쓴다. 200 이면 True, 비200/예외면 False(예외는 경고 로그)."""
    try:
        resp = session.get(url, timeout=15)
        if resp.status_code == 200:
            # w966도 작으면 원본 그대로 (크기 무관하게 저장)
            fpath.write_bytes(resp.content)
            return True
        return False
    except Exception as e:  # noqa: BLE001 - 작은 이미지 재다운로드 실패를 카운트하고 경고 로그 남긴 뒤 계속 진행 - 읽기전용 다운로드 스크립트, 실패 건수만 집계될 뿐 위험 조작 없음
        logger.warning("실패 %s: %s", url[:60], e)
        return False


def main():
    base = get_local_data_dir() / "gonobi_images"
    # 작은 파일 목록 수집
    small_files = _collect_small_files(base)

    logger.info("재다운로드 대상: %d개", len(small_files))

    session = requests.Session()
    session.headers.update(HEADERS)

    done = 0
    errors = 0
    for i, fpath in enumerate(small_files, 1):
        url = _resolve_image_url(fpath)
        if url is None:
            continue

        if _redownload(session, url, fpath):
            done += 1
        else:
            errors += 1

        time.sleep(0.1)

        if i % 100 == 0:
            logger.info("[%d/%d] 완료:%d 오류:%d", i, len(small_files), done, errors)

    logger.info("완료 — 재다운로드:%d 오류:%d", done, errors)

    # 결과 확인
    print("\n=== 최종 폴더별 현황 ===")
    total = 0
    still_small = 0
    for folder in sorted(base.iterdir()):
        if folder.is_dir():
            files = list(folder.glob("*"))
            s = sum(1 for f in files if f.stat().st_size < MIN_SIZE)
            total += len(files)
            still_small += s
            print(f"  {folder.name:15} {len(files):4}개 | 10KB미만:{s}개")
    print(f"\n합계: {total}개 | 여전히 작음: {still_small}개")


if __name__ == "__main__":
    main()
