"""mutmut export-cicd-stats 결과를 GITHUB_STEP_SUMMARY 용 Markdown 으로 요약한다. 점수로 실패시키지 않는다(항상 exit 0)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

STATS = Path("mutants/mutmut-cicd-stats.json")


def render(stats: dict[str, int], total_targets: int = 0, limit: int = 0) -> str:
    killed, survived = stats.get("killed", 0), stats.get("survived", 0)
    decided = killed + survived  # total 은 누적값이라 분모로 쓰지 않는다
    score = f"{killed / decided:.1%}" if decided else "n/a"
    lines = ["## 변이 검증(mutmut)", "", f"- 점수(killed/(killed+survived)): **{score}** ({killed}/{decided})"]
    for key in ("survived", "no_tests", "timeout", "suspicious", "skipped"):
        lines.append(f"- {key}: {stats.get(key, 0)}")
    if limit and total_targets > limit:
        lines.append(f"- ⚠ 대상 함수 {total_targets}개 중 {limit}개만 검사함(상한 절삭)")
    return "\n".join(lines) + "\n"


def main() -> int:
    total_targets = int(os.environ.get("TOTAL_TARGETS", "0") or 0)
    limit = int(os.environ.get("TARGET_LIMIT", "0") or 0)
    try:
        stats = json.loads(STATS.read_text(encoding="utf-8"))
    except (OSError, ValueError) as _read_error:
        text = "## 변이 검증(mutmut)\n\n통계 파일이 없습니다(대상 함수 없음 또는 실행 실패).\n"
    else:
        text = render(stats, total_targets, limit)
    target = os.environ.get("GITHUB_STEP_SUMMARY")
    if target:
        with open(target, "a", encoding="utf-8") as fh:
            fh.write(text)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
