#!/usr/bin/env python
"""OneDrive 상위 폴더 탐색 및 업무파일 후보 발견.

READ-ONLY, 파일 내용 read 없음, 파일 이동/삭제 없음.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.local_inventory.file_map.folder_summarizer import FolderSummarizer
from collections import defaultdict
import json


def main():
    """OneDrive 탐색 실행."""
    target_dir = r"C:\Users\skyjw\OneDrive"

    print(f"\n[OneDrive 탐색 시작]")
    print(f"대상: {target_dir}")
    print(f"최대 깊이: 2")
    print(f"제약: 폴더당 최대 300파일, 전체 최대 10000파일")

    summarizer = FolderSummarizer()
    summaries, meta = summarizer.summarize_top_folders(
        target_dir,
        max_depth=2,
        max_files_per_folder=300,
        total_max_files=10000,
        exclude_hidden=True,
    )

    if not meta["ok"]:
        print(f"\n오류: {meta.get('error')}")
        return False

    print(f"\n✓ 탐색 완료: {meta['folders_summarized']}개 폴더, {meta['scan_duration_seconds']:.2f}초")

    # 결과 분석
    if not summaries:
        print("탐색된 폴더가 없습니다.")
        return True

    # 정렬 및 TOP 선택
    top_by_files = sorted(summaries, key=lambda s: s.direct_file_count, reverse=True)[:10]
    top_by_size = sorted(summaries, key=lambda s: s.total_size_bytes, reverse=True)[:10]
    top_by_score = sorted(summaries, key=lambda s: s.business_score, reverse=True)[:10]

    # 카테고리별 TOP
    doc_candidates = [s for s in summaries if "document" in s.business_categories]
    doc_candidates = sorted(doc_candidates, key=lambda s: s.business_score, reverse=True)[:10]

    sheet_candidates = [s for s in summaries if "spreadsheet" in s.business_categories]
    sheet_candidates = sorted(sheet_candidates, key=lambda s: s.business_score, reverse=True)[:10]

    cad_candidates = [s for s in summaries if "cad" in s.business_categories]
    cad_candidates = sorted(cad_candidates, key=lambda s: s.business_score, reverse=True)[:10]

    code_candidates = [s for s in summaries if "code" in s.business_categories]
    code_candidates = sorted(code_candidates, key=lambda s: s.business_score, reverse=True)[:10]

    # 정리 우선 (파일 많거나 용량 큰)
    cleanup_candidates = [
        s for s in summaries
        if s.direct_file_count > 100 or s.total_size_bytes > 500 * 1024 * 1024
    ]
    cleanup_candidates = sorted(
        cleanup_candidates,
        key=lambda s: (s.direct_file_count, s.total_size_bytes),
        reverse=True,
    )[:10]

    # 결과 출력
    print("\n" + "=" * 80)
    print("[파일 수 TOP 10]")
    print("=" * 80)
    for i, s in enumerate(top_by_files, 1):
        print(f"{i:2}. {s.folder_name:30} | 파일: {s.direct_file_count:4} | 폴더: {s.direct_folder_count:3} | 용량: {s.total_size_bytes / (1024*1024):.1f}MB")

    print("\n" + "=" * 80)
    print("[용량 TOP 10]")
    print("=" * 80)
    for i, s in enumerate(top_by_size, 1):
        size_mb = s.total_size_bytes / (1024 * 1024)
        print(f"{i:2}. {s.folder_name:30} | 용량: {size_mb:8.1f}MB | 파일: {s.direct_file_count:4}")

    print("\n" + "=" * 80)
    print("[업무 후보 점수 TOP 10]")
    print("=" * 80)
    for i, s in enumerate(top_by_score, 1):
        cats = ", ".join(s.business_categories) if s.business_categories else "없음"
        print(f"{i:2}. {s.folder_name:30} | 점수: {s.business_score:5.1f} | {cats}")

    if doc_candidates:
        print("\n" + "=" * 80)
        print("[문서 업무 후보]")
        print("=" * 80)
        for i, s in enumerate(doc_candidates, 1):
            print(f"{i:2}. {s.folder_name:30} | 점수: {s.business_score:5.1f} | 파일: {s.direct_file_count:4}")

    if sheet_candidates:
        print("\n" + "=" * 80)
        print("[엑셀/정산 후보]")
        print("=" * 80)
        for i, s in enumerate(sheet_candidates, 1):
            print(f"{i:2}. {s.folder_name:30} | 점수: {s.business_score:5.1f} | 파일: {s.direct_file_count:4}")

    if cad_candidates:
        print("\n" + "=" * 80)
        print("[CAD 후보]")
        print("=" * 80)
        for i, s in enumerate(cad_candidates, 1):
            print(f"{i:2}. {s.folder_name:30} | 점수: {s.business_score:5.1f} | 파일: {s.direct_file_count:4}")

    if code_candidates:
        print("\n" + "=" * 80)
        print("[개발 프로젝트 후보]")
        print("=" * 80)
        for i, s in enumerate(code_candidates, 1):
            print(f"{i:2}. {s.folder_name:30} | 점수: {s.business_score:5.1f} | 파일: {s.direct_file_count:4}")

    if cleanup_candidates:
        print("\n" + "=" * 80)
        print("[정리 우선 후보 (파일 >100 또는 용량 >500MB)]")
        print("=" * 80)
        for i, s in enumerate(cleanup_candidates, 1):
            size_mb = s.total_size_bytes / (1024 * 1024)
            print(f"{i:2}. {s.folder_name:30} | 파일: {s.direct_file_count:4} | 용량: {size_mb:8.1f}MB")

    # JSON 저장
    summary_dicts = [
        {
            "folder_path": s.folder_path,
            "folder_name": s.folder_name,
            "direct_file_count": s.direct_file_count,
            "direct_folder_count": s.direct_folder_count,
            "total_size_mb": round(s.total_size_bytes / (1024 * 1024), 2),
            "extension_distribution": s.extension_distribution,
            "last_modified": s.last_modified,
            "business_score": round(s.business_score, 2),
            "business_categories": s.business_categories,
        }
        for s in summaries
    ]

    output_file = Path(__file__).parent.parent / "docs" / "reports" / "onedrive_discovery_data.json"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(summary_dicts, f, ensure_ascii=False, indent=2)

    print(f"\n✓ 데이터 저장: {output_file}")
    print(f"✓ 총 탐색 폴더: {len(summaries)}")

    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
