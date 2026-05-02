"""파일 정리 계획 마크다운 리포트 생성기."""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from .cleanup_planner import CleanupPlanner, format_size, CleanupPlan
from .models import FileMapReport


class CleanupReportGenerator:
    """정리 계획 리포트 생성."""

    def __init__(self, reveal_sensitive_names: bool = False, auth_verified: bool = False):
        """초기화.

        Args:
            reveal_sensitive_names: 민감정보 표시 활성화
            auth_verified: 사용자 인증 완료 여부
        """
        self.planner = CleanupPlanner(reveal_sensitive_names, auth_verified)

    def generate_markdown(self, report: FileMapReport) -> str:
        """마크다운 리포트 생성.

        Args:
            report: 파일 지도 리포트

        Returns:
            마크다운 문자열
        """
        plans = self.planner.plan_cleanup(report)
        summary = self.planner.summarize_plans(plans)

        lines = []

        # 제목
        lines.append("# PROJECT_FILE 정리 계획표")
        lines.append("")
        lines.append(f"**생성일**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")
        lines.append("**주의**: 이것은 계획표일 뿐 실제 파일 이동/삭제를 수행하지 않습니다.")
        lines.append("")

        # 요약
        lines.append("## 요약")
        lines.append("")
        lines.append(f"- **총 분석 파일**: {len(plans)} 개")
        lines.append(f"- **스캔 시간**: {report.scan_timestamp}")
        lines.append(f"- **스캔 디렉토리**: {report.scanned_directory}")
        lines.append("")

        # 카테고리별 통계
        lines.append("## 카테고리별 통계")
        lines.append("")
        lines.append("| 카테고리 | 파일 수 | 용량 |")
        lines.append("|---------|--------|------|")

        for category in sorted(summary.keys()):
            data = summary[category]
            lines.append(
                f"| {category} | {data['count']} | {format_size(data['total_size'])} |"
            )

        lines.append("")

        # 제안 폴더 구조
        lines.append("## 제안 폴더 구조")
        lines.append("")
        lines.append(self._generate_folder_structure())
        lines.append("")

        # 카테고리별 상세
        lines.extend(self._generate_category_sections(summary))

        # 정책 안내
        lines.append("## 정책 안내")
        lines.append("")
        lines.append("### 파일명 표시 정책")
        lines.append("- **기본**: 민감한 파일명은 마스킹됨")
        lines.append("- **인증 후**: 사용자가 신뢰 PC 설정 선택 시 원본 표시 가능")
        lines.append("")
        lines.append("### 실행 안내")
        lines.append("- 이 계획표는 제안만 제공합니다")
        lines.append("- 실제 파일 이동은 사용자 검토 후 수동으로 진행해야 합니다")
        lines.append("- 중복 검토 항목은 반드시 확인 후 삭제 여부를 결정하세요")
        lines.append("- 민감문서는 별도 보안 저장소로 이동을 권장합니다")
        lines.append("")

        return "\n".join(lines)

    def _generate_folder_structure(self) -> str:
        """제안 폴더 구조."""
        structure = """```
01_PROJECT_FILE_정리안/
├─ 01_업무문서/
│  ├─ 업무문서/           (보고서, 계획안, 공문 등)
│  ├─ 엑셀_내역_정산/     (재무, 정산, 내역 등)
│  ├─ CAD_도면/           (도면, 설계도 등)
│  ├─ 사진_스캔/          (스캔, 촬영 이미지)
│  ├─ 계약_증빙_민감/     (계약서, 통장, 신분증 등)
│  ├─ 설치파일_보관/      (1년 이상 미사용 설치파일)
│  ├─ 압축_백업/          (백업, 압축 아카이브)
│  └─ 중복검토/           (복사본, 사본, 검토 필요)
└─ 99_분류보류/
   └─                      (미분류, 최근파일, 확장자 없음 등)
```"""
        return structure

    def _generate_category_sections(self, summary: dict) -> list[str]:
        """카테고리별 상세 섹션."""
        lines = []

        category_display = {
            "보관": ("## 보관 후보 (오래된 설치파일)", "안전하게 보관할 수 있는 오래된 설치파일"),
            "업무문서": ("## 업무문서 후보", "분류 가능한 업무 문서"),
            "엑셀정산": ("## 엑셀/정산 후보", "스프레드시트 및 내역서"),
            "CAD도면": ("## CAD/도면 후보", "도면 및 설계 파일"),
            "이미지스캔": ("## 이미지/스캔 후보", "사진, 스캔, 이미지"),
            "민감문서": ("## 민감문서 분리 후보", "보안이 필요한 민감문서"),
            "중복검토": ("## 중복 검토 후보", "검토 후 삭제 가능한 중복 파일"),
            "분류보류": ("## 분류보류 후보", "현재 분류 불가 또는 최근 파일"),
        }

        for category in sorted(summary.keys()):
            if category not in category_display:
                continue

            title, description = category_display[category]
            data = summary[category]

            lines.append(title)
            lines.append("")
            lines.append(f"{description}")
            lines.append("")
            lines.append(f"**파일 수**: {data['count']} 개 | **총 용량**: {format_size(data['total_size'])}")
            lines.append("")

            # TOP 30 샘플
            lines.append("### TOP 샘플 파일")
            lines.append("")
            lines.append("| 파일명 | 경로 | 용량 | 수정시간 |")
            lines.append("|--------|------|------|---------|")

            for plan in data["samples"][:30]:
                size_str = format_size(plan.file_size_bytes)
                mod_time = plan.modified_time[:10]  # YYYY-MM-DD
                lines.append(
                    f"| {plan.masked_name[:50]} | ... | {size_str} | {mod_time} |"
                )

            lines.append("")

        return lines


def generate_cleanup_report(
    report: FileMapReport,
    output_path: str,
    reveal_sensitive_names: bool = False,
    auth_verified: bool = False
) -> None:
    """정리 계획 리포트 파일 생성.

    Args:
        report: 파일 지도 리포트
        output_path: 출력 경로
        reveal_sensitive_names: 민감정보 표시 활성화
        auth_verified: 사용자 인증 완료 여부
    """
    generator = CleanupReportGenerator(reveal_sensitive_names, auth_verified)
    markdown = generator.generate_markdown(report)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(markdown)
