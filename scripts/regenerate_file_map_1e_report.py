#!/usr/bin/env python3
"""파일 지도 1E 리포트 재생성 스크립트.

LOCAL-FILE-MAP-1E: 01. PROJECT_FILE 정밀 스캔 리포트를 보정된 형식으로 재생성.
"""
import sys
from pathlib import Path

# 프로젝트 루트 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from agent.local_inventory.file_map.scanner import FileMapScanner
from agent.local_inventory.file_map.report_builder import FileMapReportBuilder
from agent.local_inventory.file_map.markdown_renderer import MarkdownRenderer
from agent.local_inventory.file_map.models import ScanOptions
from datetime import datetime


def main():
    """리포트 재생성."""
    print("🔍 LOCAL-FILE-MAP-1E 리포트 재생성 시작...\n")

    # 스캔 대상
    target_dir = r"C:\Users\skyjw\OneDrive\01. PROJECT_FILE"
    print(f"📁 스캔 대상: {target_dir}")

    if not Path(target_dir).exists():
        print(f"❌ 디렉토리를 찾을 수 없음: {target_dir}")
        return 1

    # 스캔 옵션
    options = ScanOptions(
        target_directory=target_dir,
        scan_depth=6,
        max_files=5000,
        exclude_hidden=True,
        exclude_system_dirs=True,
    )

    # 파일 스캔
    print("📂 파일 스캔 중...")
    scanner = FileMapScanner()
    files, scan_result = scanner.scan(options)

    if not scan_result.get("ok"):
        print(f"❌ 스캔 실패: {scan_result.get('error')}")
        return 1

    scan_duration = scan_result.get("scan_duration_seconds", 0)
    print(f"✓ 스캔 완료: {len(files):,}개 파일 발견 ({scan_duration:.1f}초)\n")

    # 보고서 생성
    print("📊 보고서 생성 중...")
    builder = FileMapReportBuilder()
    report = builder.build_report(files, options, scan_duration)
    print("✓ 보고서 객체 생성 완료\n")

    # 마크다운 렌더링
    print("📝 마크다운 렌더링 중...")
    # 기본 리포트: 민감 파일명 마스킹, 인증 미완료
    renderer = MarkdownRenderer(
        reveal_sensitive_names=False,
        auth_verified=False
    )
    markdown = renderer.render(report, "01. PROJECT_FILE")
    print("✓ 마크다운 렌더링 완료\n")

    # 파일 저장
    report_path = project_root / "docs" / "reports" / "local_file_map_1e_project_file_scan_report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(markdown)

    print(f"💾 리포트 저장: {report_path}")
    print(f"   파일 크기: {report_path.stat().st_size / 1024:.1f} KB\n")

    # 결과 요약
    print("=" * 60)
    print("📈 스캔 결과 요약")
    print("=" * 60)
    print(f"총 파일 수: {report.total_files:,}")
    print(f"총 용량: {report.total_size_bytes / (1024 ** 3):.1f} GB")
    print(f"대용량 파일: {len(report.large_files)}개")
    print(f"오래된 파일: {len(report.old_files)}개")
    print(f"중복 의심: {len(report.suspicious_duplicates)}개")
    print(f"임시 파일: {len(report.suspicious_temp)}개")
    print("=" * 60)
    print("\n✅ 리포트 재생성 완료!")

    return 0


if __name__ == "__main__":
    sys.exit(main())
