"""gonobi 이미지를 블로그 원본 카테고리 기준으로 재분류."""

import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from ai_orchestrator.core.config import get_local_data_dir
from scripts.naver.blog.gonobi.db import open_db


# 폴더명에 사용 불가 문자 제거
def safe_name(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|★\s]', "_", name).strip("_")


def _collect_image_files(base) -> list:
    """base 하위 폴더의 모든 파일을 수집."""
    all_files = []
    for folder in base.iterdir():
        if folder.is_dir():
            for f in folder.glob("*"):
                if f.is_file():
                    all_files.append(f)
    return all_files


def main():
    base = get_local_data_dir() / "gonobi_images"
    new_base = get_local_data_dir() / "gonobi_images_v2"
    # DB에서 log_no → category_name 매핑
    with open_db() as conn:
        posts = conn.execute("SELECT log_no, category_name, title FROM gonobi_posts").fetchall()

    log_to_cat = {r["log_no"]: r["category_name"] for r in posts}
    _log_to_title = {r["log_no"]: r["title"] for r in posts}

    print(f"포스트 수: {len(log_to_cat)}")

    # 기존 이미지 파일 전체 수집
    all_files = _collect_image_files(base)

    print(f"전체 이미지 파일: {len(all_files)}개")

    # 파일명에서 log_no 추출 (패턴: {log_no}_{n}_{title}.{ext})
    moved = 0
    skipped = 0
    no_match = 0
    by_cat = defaultdict(int)

    new_base.mkdir(parents=True, exist_ok=True)

    for f in all_files:
        # 파일명 첫 부분이 log_no
        stem = f.stem
        parts = stem.split("_")
        log_no = parts[0] if parts else ""

        cat_name = log_to_cat.get(log_no)
        if not cat_name:
            # log_no 못 찾으면 기존 폴더명 유지
            cat_name = f.parent.name
            no_match += 1

        dest_folder = new_base / safe_name(cat_name)
        dest_folder.mkdir(parents=True, exist_ok=True)
        dest = dest_folder / f.name

        if dest.exists():
            skipped += 1
            continue

        shutil.copy2(f, dest)
        moved += 1
        by_cat[cat_name] += 1

    print(f"\n이동 완료: {moved}개 | 이미 존재: {skipped}개 | log_no 미매칭: {no_match}개")
    print("\n=== 카테고리별 결과 ===")
    for cat, cnt in sorted(by_cat.items(), key=lambda x: -x[1]):
        print(f"  {safe_name(cat):25} {cnt:5}개  (원본: {cat})")

    # 최종 검증
    print("\n=== 최종 폴더 현황 ===")
    total = 0
    for folder in sorted(new_base.iterdir()):
        if folder.is_dir():
            files = list(folder.glob("*"))
            sizes = [f.stat().st_size for f in files]
            avg_kb = sum(sizes) // len(sizes) // 1024 if sizes else 0
            small = sum(1 for s in sizes if s < 10000)
            total += len(files)
            print(f"  {folder.name:25} {len(files):5}개 | 평균:{avg_kb:4}KB | 10KB미만:{small}개")
    print(f"\n합계: {total}개")


if __name__ == "__main__":
    main()
