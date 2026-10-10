"""PostToolUse 훅 — Write/Edit 후 xlsx 파일이면 A4 서식 자동 검사.

흐름:
  1. check_a4.py  — 인쇄 설정·행높이·여백 등 기계 검사 (비용 없음)
  (참고) 예전에는 ai_check_a4.py 가 2단계로 GPT-4o-mini 품질 평가를 했으나, CLAUDE.md "외부 유료 AI API
  호출 승인제"와 2026-09-24 "OpenAI 호출 코드 완전 삭제" 결정에 맞지 않고 이미 실행 불가여서 2026-10-08
  삭제했다(docs/deleted_code_index.md). 되살리려면 이 파일이 아니라 사용자 승인부터 받을 것.

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
OFFICE = HERE.parent / "office"  # check_a4.py 가 있는 폴더(P2 에서 ops 직하 → office/ 로 이동)
ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다


def _run(script: str, file_path: str) -> int:
    result = subprocess.run(
        [sys.executable, str(OFFICE / script), file_path],
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

    # ── 2단계: AI 품질 검사 — 비활성 (위 모듈 docstring 참고) ────────────────────
    sys.exit(0)


if __name__ == "__main__":
    main()
