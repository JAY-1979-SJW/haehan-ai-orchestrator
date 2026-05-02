"""파일 지도 보고서 마크다운 렌더러.

FileMapReport를 마크다운 형식으로 변환.
민감 파일명 마스킹 옵션 포함.
"""
from __future__ import annotations

from datetime import datetime
from .models import FileMapReport
from .privacy import PrivacyMasker


class MarkdownRenderer:
    """마크다운 렌더러."""

    def __init__(self, reveal_sensitive: bool = False) -> None:
        """초기화.

        Args:
            reveal_sensitive: True면 민감 파일명 원본 유지, False면 마스킹
        """
        self.reveal_sensitive = reveal_sensitive
        self.masker = PrivacyMasker()

    def render(self, report: FileMapReport, report_name: str = "01. PROJECT_FILE") -> str:
        """보고서를 마크다운으로 렌더링한다.

        Args:
            report: FileMapReport 객체
            report_name: 리포트 이름 (제목에 사용)

        Returns:
            마크다운 문자열
        """
        lines = []

        # 제목
        lines.append(f"# LOCAL-FILE-MAP-1E: {report_name} 정밀 스캔 리포트\n")
        lines.append("**스캔 날짜**: " + datetime.now().strftime("%Y-%m-%d"))
        lines.append("**스캔 상태**: ✅ 완료 (읽기 전용, 파일 변경 없음)\n")

        # max_files 제한 도달 여부에 따른 경고
        if self._is_max_files_reached(report.total_files):
            lines.append("⚠️ **주의**: 이번 스캔은 **max_files 제한에 도달**했습니다.")
            lines.append("따라서 결과는 전체 폴더의 완전한 통계가 아니라 제한 범위 내 분석입니다.\n")

        lines.append("---\n")

        # 1. 스캔 대상
        lines.extend(self._render_scan_target(report))

        # 2. 스캔 결과 요약
        lines.extend(self._render_summary(report))

        # 3. 카테고리별 분포
        lines.extend(self._render_categories(report))

        # 4. 대용량 파일
        lines.extend(self._render_large_files(report))

        # 5. 오래된 파일
        lines.extend(self._render_old_files(report))

        # 6. 중복 의심 파일
        lines.extend(self._render_duplicates(report))

        # 7. 임시/다운로드 의심 파일
        lines.extend(self._render_suspicious_temp(report))

        # 8. 추천사항
        lines.extend(self._render_recommendations(report))

        return "\n".join(lines)

    @staticmethod
    def _is_max_files_reached(total_files: int) -> bool:
        """max_files 제한 도달 여부.

        Args:
            total_files: 스캔된 파일 수

        Returns:
            도달 여부
        """
        # 5000개 제한 기준
        return total_files >= 4999

    def _render_scan_target(self, report: FileMapReport) -> list[str]:
        """스캔 대상 섹션."""
        lines = []
        lines.append("## 1. 스캔 대상\n")
        lines.append(f"**경로**: `{report.scanned_directory}`\n")
        lines.append("**스캔 옵션**:")
        lines.append("- 최대 깊이: 6")
        lines.append("- 최대 파일: 5000")
        lines.append("- 숨겨진 파일 제외: Yes")
        lines.append("- Symlink 팔로우: No\n")
        lines.append("---\n")
        return lines

    def _render_summary(self, report: FileMapReport) -> list[str]:
        """요약 섹션."""
        lines = []
        lines.append("## 2. 스캔 결과 요약\n")
        lines.append("| 항목 | 값 |")
        lines.append("|------|-----|")

        # 파일 수 포맷
        total_files_str = f"{report.total_files:,} 개"
        lines.append(f"| 총 파일 수 | {total_files_str} |")

        # 용량 포맷
        total_gb = report.total_size_bytes / (1024 ** 3)
        total_size_str = f"{report.total_size_bytes:,} bytes ({total_gb:.1f} GB)"
        lines.append(f"| 총 용량 | {total_size_str} |")

        # 스캔 시간
        duration_str = f"{report.scan_duration_seconds:.1f}초"
        lines.append(f"| 스캔 소요 시간 | {duration_str} |")
        lines.append("")
        lines.append("---\n")
        return lines

    def _render_categories(self, report: FileMapReport) -> list[str]:
        """카테고리 섹션."""
        lines = []
        lines.append("## 3. 카테고리별 분포\n")
        lines.append("| 카테고리 | 파일 수 | 비율 |")
        lines.append("|---------|--------|------|")

        total = sum(report.files_by_category.values())
        for category, count in sorted(
            report.files_by_category.items(),
            key=lambda x: x[1],
            reverse=True
        ):
            pct = (count / total * 100) if total > 0 else 0
            lines.append(f"| {category} | {count} | {pct:.1f}% |")

        lines.append("\n**주요 카테고리**:")
        for category, count in sorted(
            report.files_by_category.items(),
            key=lambda x: x[1],
            reverse=True
        )[:5]:
            cat_map = {
                "document": "문서 파일",
                "spreadsheet": "스프레드시트",
                "image": "이미지 파일",
                "video": "동영상 파일",
                "audio": "오디오 파일",
                "archive": "압축 파일",
                "cad": "CAD 파일",
                "code": "코드 파일",
                "unknown": "미분류",
            }
            cat_name = cat_map.get(category, category)
            lines.append(f"- **{cat_name}**: {count}개")

        lines.append("")
        lines.append("---\n")
        return lines

    def _render_large_files(self, report: FileMapReport) -> list[str]:
        """대용량 파일 섹션."""
        lines = []
        lines.append("## 4. 대용량 파일 (상위 20개)\n")

        if not report.large_files:
            lines.append("대용량 파일 없음\n")
            lines.append("---\n")
            return lines

        lines.append("| 순위 | 파일명 | 크기 (MB) |")
        lines.append("|------|--------|----------|")

        for idx, file_info in enumerate(report.large_files[:20], 1):
            filename = self.masker.mask_filename(
                file_info.get("name", ""),
                self.reveal_sensitive
            )
            # size_mb가 없으면 size_bytes에서 계산
            size_mb = file_info.get("size_mb")
            if size_mb is None:
                size_bytes = file_info.get("size_bytes", 0)
                size_mb = round(size_bytes / (1024 * 1024), 2)

            lines.append(f"| {idx} | {filename} | {size_mb:.1f} |")

        lines.append("")
        lines.append("---\n")
        return lines

    def _render_old_files(self, report: FileMapReport) -> list[str]:
        """오래된 파일 섹션."""
        lines = []
        lines.append("## 5. 오래된 파일 (상위 20개)\n")

        if not report.old_files:
            lines.append("오래된 파일 없음\n")
            lines.append("---\n")
            return lines

        lines.append("| 순위 | 파일명 | 수정 일시 | 경과 일수 |")
        lines.append("|------|--------|----------|----------|")

        for idx, file_info in enumerate(report.old_files[:20], 1):
            filename = self.masker.mask_filename(
                file_info.get("name", ""),
                self.reveal_sensitive
            )
            modified = file_info.get("modified_time", "")
            age_days = file_info.get("age_days", 0)
            lines.append(f"| {idx} | {filename} | {modified} | {age_days}일 |")

        lines.append("")
        lines.append("---\n")
        return lines

    def _render_duplicates(self, report: FileMapReport) -> list[str]:
        """중복 의심 파일 섹션."""
        lines = []
        lines.append("## 6. 중복 의심 파일\n")

        if not report.suspicious_duplicates:
            lines.append("중복 의심 파일 없음\n")
            lines.append("---\n")
            return lines

        lines.append("### 중복 의심 그룹 (상위 20개)\n")
        lines.append("| 원본 | 유사 파일 수 | 사유 | 심각도 |")
        lines.append("|------|-------------|------|--------|")

        for dup_info in report.suspicious_duplicates[:20]:
            primary_name = self.masker.mask_filename(
                dup_info.get("primary", "").split("\\")[-1].split("/")[-1],
                self.reveal_sensitive
            )
            similar_count = len(dup_info.get("similar", []))
            reason = dup_info.get("reason", "unknown")
            severity = dup_info.get("severity", "unknown")

            reason_map = {
                "same_name": "동일 파일명",
                "same_size": "동일 크기",
                "copy_pattern": "복사본 패턴",
            }
            severity_map = {
                "high": "높음",
                "medium": "중간",
                "low": "낮음",
            }

            reason_text = reason_map.get(reason, reason)
            severity_text = severity_map.get(severity, severity)

            lines.append(
                f"| {primary_name} | {similar_count} | {reason_text} | {severity_text} |"
            )

        lines.append("")
        lines.append("**검토 필요**: 수동 확인 후 실제 중복은 정리를 검토하세요.\n")
        lines.append("---\n")
        return lines

    def _render_suspicious_temp(self, report: FileMapReport) -> list[str]:
        """임시/다운로드 의심 파일 섹션."""
        lines = []
        lines.append("## 7. 임시/다운로드 의심 파일 (상위 20개)\n")

        if not report.suspicious_temp:
            lines.append("임시 파일 의심 없음\n")
            lines.append("---\n")
            return lines

        lines.append("| 순위 | 파일명 | 크기 (KB) |")
        lines.append("|------|--------|----------|")

        for idx, file_info in enumerate(report.suspicious_temp[:20], 1):
            filename = self.masker.mask_filename(
                file_info.get("name", ""),
                self.reveal_sensitive
            )
            size_kb = file_info.get("size_kb", 0)
            lines.append(f"| {idx} | {filename} | {size_kb:.1f} |")

        lines.append("")
        lines.append("---\n")
        return lines

    def _render_recommendations(self, report: FileMapReport) -> list[str]:
        """추천사항 섹션."""
        lines = []
        lines.append("## 8. 정리 추천사항\n")

        if not report.recommendations:
            lines.append("추천사항 없음\n")
        else:
            for rec in report.recommendations:
                lines.append(f"- {rec}")

        lines.append("")
        lines.append("---\n")
        lines.append("**생성 일시**: " + datetime.now().isoformat())
        return lines
