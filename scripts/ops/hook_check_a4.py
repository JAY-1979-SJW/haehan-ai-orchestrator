"""PostToolUse 훅 — Write/Edit 후 xlsx 파일이면 A4 서식 자동 검사 + AI 검증.

흐름:
  1. check_a4.py  — 인쇄 설정·행높이·여백 등 기계 검사
  2. ai_check_a4.py — GPT-4.1 품질 평가 (grade A 미달 시 비정상 종료)

훅 stdin: {"tool_name": ..., "tool_input": {"file_path": ...}, ...}
비정상 종료 시 Claude Code 가 이슈를 인지하고 자동 수정 진행.
"""

import json
import logging
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.WARNING, format="[hook_check_a4] %(message)s")
log = logging.getLogger(__name__)

HERE = Path(__file__).parent
ROOT = HERE.parent.parent


def _run(script: str, file_path: str) -> int:
    result = subprocess.run(
        [sys.executable, str(HERE / script), file_path],
        cwd=str(ROOT),
    )
    return result.returncode


def main():
    try:
        data = json.loads(sys.stdin.read())
    except Exception as e:  # noqa: BLE001 - PreToolUse 훅 진입점 — stdin JSON 파싱 실패 시 exit(0)으로 통과시키는 의도된 fail-open, 이후 실제 파일 경로 검사 로직은 파싱 성공을 전제로 별도 수행.
        log.warning("stdin 파싱 실패: %s", e)
        sys.exit(0)

    tool_input = data.get("tool_input") or data.get("input") or {}
    file_path = tool_input.get("file_path", "")

    if not file_path.lower().endswith(".xlsx"):
        sys.exit(0)

    # ── 1단계: 기계 검사 ──────────────────────────────────────────────────────
    rc1 = _run("check_a4.py", file_path)
    if rc1 != 0:
        log.warning("check_a4 실패 (returncode=%d): %s", rc1, file_path)
        sys.exit(rc1)

    # ── 2단계: AI 품질 검사 ───────────────────────────────────────────────────
    rc2 = _run("ai_check_a4.py", file_path)
    if rc2 != 0:
        print(
            "\n[hook] ⚠️  AI 검증 이슈 발견 — "
            "scripts/eum/shared/layout_schema.py 또는 style_presets.py 수정 후 재렌더 필요",
            file=sys.stderr,
        )
        sys.exit(rc2)

    sys.exit(0)


if __name__ == "__main__":
    main()
