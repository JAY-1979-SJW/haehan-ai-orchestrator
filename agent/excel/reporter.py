"""Excel 분석 결과 보고서 생성.

표 분석, 수식 검증, 데이터 품질 검사 결과를 종합하여
사람이 읽을 수 있는 보고서로 생성한다.
Read-only 작업이므로 원본 수정 없음.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def build_analysis_report(
    sheet_name: str,
    table_analysis: Optional[dict] = None,
    data_validation: Optional[dict] = None,
    formula_errors: Optional[dict] = None,
) -> dict:
    """분석 결과를 종합하여 보고서를 생성한다.

    Args:
        sheet_name: 시트 이름
        table_analysis: table_analyzer 결과
        data_validation: data_validator 결과
        formula_errors: formula_validator 결과

    Returns:
        {
            "sheet_name": str,
            "summary": {...},
            "details": {...},
            "issues": [...],
            "recommendations": [...],
        }
    """
    issues = []
    recommendations = []

    # 데이터 품질 분석
    quality_score = 100
    if data_validation:
        quality_score = data_validation.get("quality_score", 100)
        if data_validation.get("error_cells", 0) > 0:
            error_count = data_validation.get("error_cells", 0)
            issues.append({
                "type": "formula_error",
                "severity": "high",
                "message": f"{error_count} 개의 셀에 수식 에러 발견",
            })
        if data_validation.get("empty_cells", 0) > 0:
            pct = data_validation.get("empty_percentage", 0)
            if pct > 10:
                issues.append({
                    "type": "empty_cells",
                    "severity": "medium",
                    "message": f"{pct}%의 셀이 비어있음",
                })
                if pct > 30:
                    recommendations.append("빈 셀이 많습니다. 데이터 정제 검토 필요")

    # 테이블 구조 분석
    if table_analysis:
        col_count = table_analysis.get("summary", {}).get("col_count", 0)
        row_count = table_analysis.get("summary", {}).get("data_row_count", 0)

        if col_count == 0:
            issues.append({
                "type": "no_columns",
                "severity": "high",
                "message": "헤더 행을 찾을 수 없음",
            })
        if row_count == 0:
            issues.append({
                "type": "no_data",
                "severity": "medium",
                "message": "데이터 행이 없음",
            })

        # 열 타입 분석
        for col in table_analysis.get("columns", []):
            if col.get("type") == "unknown":
                recommendations.append(
                    f"'{col['name']}' 열의 데이터 타입 확인 필요"
                )

    # 수식 검증
    if formula_errors:
        if formula_errors.get("error_count", 0) > 0:
            issues.append({
                "type": "formula_errors",
                "severity": "high",
                "message": f"{formula_errors['error_count']} 개의 수식 에러",
                "error_types": formula_errors.get("error_types", {}),
            })

    # 우선순위별 정렬
    issues.sort(key=lambda x: {"high": 0, "medium": 1, "low": 2}.get(x.get("severity"), 3))

    return {
        "sheet_name": sheet_name,
        "summary": {
            "quality_score": quality_score,
            "issue_count": len(issues),
            "recommendation_count": len(recommendations),
            "analysis_complete": True,
        },
        "details": {
            "table_analysis": table_analysis,
            "data_validation": data_validation,
            "formula_validation": formula_errors,
        },
        "issues": issues,
        "recommendations": recommendations,
    }


def format_report_as_text(report: dict) -> str:
    """보고서를 텍스트 형식으로 포매팅한다.

    Args:
        report: build_analysis_report 결과

    Returns:
        포매팅된 텍스트
    """
    lines = []
    lines.append("=" * 60)
    lines.append(f"Excel 분석 보고서: {report.get('sheet_name', 'Unknown')}")
    lines.append("=" * 60)
    lines.append("")

    # 요약
    summary = report.get("summary", {})
    lines.append("[요약]")
    lines.append(f"  품질 점수: {summary.get('quality_score', 'N/A')} / 100")
    lines.append(f"  발견된 문제: {summary.get('issue_count', 0)} 개")
    lines.append(f"  권장사항: {summary.get('recommendation_count', 0)} 개")
    lines.append("")

    # 문제점
    issues = report.get("issues", [])
    if issues:
        lines.append("[발견된 문제]")
        for i, issue in enumerate(issues, 1):
            severity = issue.get("severity", "unknown").upper()
            lines.append(f"  {i}. [{severity}] {issue.get('message', 'Unknown')}")
        lines.append("")

    # 권장사항
    recommendations = report.get("recommendations", [])
    if recommendations:
        lines.append("[권장사항]")
        for i, rec in enumerate(recommendations, 1):
            lines.append(f"  {i}. {rec}")
        lines.append("")

    # 상세 정보
    details = report.get("details", {})
    if details.get("table_analysis"):
        lines.append("[테이블 구조]")
        ta = details["table_analysis"].get("summary", {})
        lines.append(f"  헤더: {ta.get('header_count', 0)} 개")
        lines.append(f"  데이터 행: {ta.get('data_row_count', 0)} 개")
        lines.append(f"  열: {ta.get('col_count', 0)} 개")
        lines.append("")

    if details.get("data_validation"):
        lines.append("[데이터 현황]")
        dv = details["data_validation"]
        lines.append(f"  전체 셀: {dv.get('total_cells', 0)} 개")
        lines.append(f"  데이터: {dv.get('data_cells', 0)} 개")
        lines.append(f"  수식: {dv.get('formula_cells', 0)} 개")
        lines.append(f"  빈 셀: {dv.get('empty_cells', 0)} 개")
        lines.append(f"  에러: {dv.get('error_cells', 0)} 개")
        lines.append("")

    lines.append("=" * 60)
    return "\n".join(lines)


def summarize_changes(
    before_report: Optional[dict],
    after_report: Optional[dict],
) -> dict:
    """변경 전후를 비교하여 변경 요약을 생성한다.

    Args:
        before_report: 변경 전 보고서
        after_report: 변경 후 보고서

    Returns:
        {
            "quality_delta": float,
            "issue_delta": int,
            "improvements": [...],
            "regressions": [...],
        }
    """
    if not before_report or not after_report:
        return {
            "quality_delta": 0,
            "issue_delta": 0,
            "improvements": [],
            "regressions": [],
        }

    before_summary = before_report.get("summary", {})
    after_summary = after_report.get("summary", {})
    before_issues = set(i.get("message", "") for i in before_report.get("issues", []))
    after_issues = set(i.get("message", "") for i in after_report.get("issues", []))

    quality_delta = after_summary.get("quality_score", 0) - before_summary.get("quality_score", 0)
    issue_delta = after_summary.get("issue_count", 0) - before_summary.get("issue_count", 0)

    improvements = list(before_issues - after_issues)
    regressions = list(after_issues - before_issues)

    return {
        "quality_delta": round(quality_delta, 2),
        "issue_delta": issue_delta,
        "improvements": improvements,
        "regressions": regressions,
    }
