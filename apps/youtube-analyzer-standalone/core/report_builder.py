"""검색 통계 + 전사 + 장면 설명을 묶어 마크다운 리포트를 조립."""

from __future__ import annotations

from typing import Any


def build_report(
    video_id: str,
    title: str,
    stats: dict[str, Any] | None,
    transcript: dict[str, Any],
    frames_with_desc: list[dict[str, Any]],
) -> str:
    """frames_with_desc: [{index, timestamp, path, description}, ...] (description 은 Claude 가 채움)"""
    lines = [f"# 영상 분석 리포트: {title}", "", f"- 영상: https://youtube.com/watch?v={video_id}"]

    if stats:
        lines += [
            f"- 조회수: {stats.get('view_count', 0):,}",
            f"- VPH: {stats.get('vph', '?')} ({'신뢰가능' if stats.get('vph_reliable') else '참고용(게시 30일 초과)'})",
            f"- 참여율(좋아요+댓글/조회수): {stats.get('engagement_rate', '?')}%",
        ]

    lines += ["", "## 장면 구성 (시간순)", ""]
    for f in frames_with_desc:
        ts = f["timestamp"]
        ts_display = f"{ts:.1f}초" if ts is not None else "?"
        lines.append(f"### #{f['index']} — {ts_display}")
        lines.append(f"- **화면**: {f.get('description', '(미판독)')}")
        if f.get("transcript_context"):
            lines.append(f"- **대사**: {f['transcript_context']}")
        lines.append("")

    source = transcript.get("source", "")
    source_label = "YouTube 자동자막" if source == "subtitle" else f"로컬 음성인식({source})"
    lines += [
        "## 전체 전사",
        "",
        f"※ 출처: {source_label}. 자동 음성/자막 인식 결과이므로 발언을 정확한 인용으로 사용하지 말 것 — "
        "이름·수치·전문용어 등 오인식 가능성이 있어 참고용으로만 활용 권장.",
        "",
        transcript.get("full_text", ""),
        "",
    ]

    lines += ["## 이 영상이 왜 잘 됐는가 (분석)", "", "<!-- WHY_ANALYSIS -->", ""]

    return "\n".join(lines)
