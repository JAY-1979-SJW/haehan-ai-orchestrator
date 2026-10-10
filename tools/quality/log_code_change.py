"""Claude Code 훅 수신 스크립트 — 파일 작성/수정 이벤트 로깅.

Claude Code PostToolUse 훅으로 호출됨.
stdin으로 JSON 이벤트를 수신해 op_log 에 기록한다.

훅 이벤트 형식 (stdin JSON):
  {
    "session_id": "...",
    "tool_name": "Write" | "Edit" | "NotebookEdit",
    "tool_input": {
      "file_path": "/path/to/file.py",
      "content": "...",        (Write)
      "old_string": "...",     (Edit)
      "new_string": "...",     (Edit)
    },
    "tool_response": { ... }
  }
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_BOOT = Path(__file__).resolve().parents[2]  # 정본을 import 하기 전 sys.path 부트스트랩(G5 예외: scripts/ 독립 실행)
if str(_BOOT) not in sys.path:
    sys.path.insert(0, str(_BOOT))

from scripts.common.app_paths import repo_root  # noqa: E402

ROOT = repo_root()
sys.path.insert(0, str(ROOT))


def main() -> None:
    try:
        raw = sys.stdin.read()
        event = json.loads(raw) if raw.strip() else {}
    except Exception:  # noqa: BLE001 - 코드 변경 로그 기록 훅(PostToolUse) — 이벤트 파싱 실패/경로 변환 실패/로그 기록 실패 모두 훅이 Claude Code 동작을 막지 않도록 무시하거나 원본값 사용(주석에 명시된 의도적 fail-open)
        event = {}

    tool_name = event.get("tool_name", "unknown")
    tool_input = event.get("tool_input", {})

    # 파일 경로 추출 (Write / Edit / NotebookEdit 공통)
    file_path = tool_input.get("file_path") or tool_input.get("path") or tool_input.get("notebook_path") or "unknown"

    # 변경 크기 추출
    if tool_name == "Write":
        content = tool_input.get("content", "")
        change_size = len(content)
        op = "file_write"
    elif tool_name in ("Edit", "MultiEdit"):
        old = tool_input.get("old_string", "")
        new = tool_input.get("new_string", "")
        change_size = abs(len(new) - len(old))
        op = "file_edit"
    elif tool_name == "NotebookEdit":
        op = "notebook_edit"
        change_size = 0
    else:
        op = f"file_{tool_name.lower()}"
        change_size = 0

    # 상대 경로로 단축
    try:
        rel = Path(file_path).relative_to(ROOT)
        display_path = str(rel)
    except Exception:  # noqa: BLE001 - 코드 변경 로그 기록 훅(PostToolUse) — 이벤트 파싱 실패/경로 변환 실패/로그 기록 실패 모두 훅이 Claude Code 동작을 막지 않도록 무시하거나 원본값 사용(주석에 명시된 의도적 fail-open)
        display_path = file_path

    # 확장자 추출
    suffix = Path(file_path).suffix.lower()

    try:
        from scripts.common.op_log import log_op

        log_op(
            op,
            ok=True,
            file=display_path,
            ext=suffix,
            size=change_size,
            tool=tool_name,
        )
    except Exception as e:  # noqa: BLE001 - 코드 변경 로그 기록 훅(PostToolUse) — 이벤트 파싱 실패/경로 변환 실패/로그 기록 실패 모두 훅이 Claude Code 동작을 막지 않도록 무시하거나 원본값 사용(주석에 명시된 의도적 fail-open)
        # 훅이 실패해도 Claude Code 동작에 영향 없도록 조용히 처리
        sys.stderr.write(f"[log_code_change] op_log 실패: {e}\n")


if __name__ == "__main__":
    main()
