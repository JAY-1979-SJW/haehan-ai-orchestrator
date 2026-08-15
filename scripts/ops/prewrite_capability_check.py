"""PreToolUse hook: Write 시점에 등록된 안전 게이트를 순서대로 실행한다.

Claude Code PreToolUse 훅으로 실행됨.
stdin: JSON {tool_name, tool_input: {file_path, content}}

이 파일은 오케스트레이터일 뿐이고, 실제 검사 로직은 각 게이트 모듈에 있다
(scripts/ops/write_gates/) — 게이트가 늘어나도 이 파일은 등록만 하면 된다.

  - naver_blog_safety_gate : 네이버 블로그 자동화 위험 패턴(경로 무관, 내용 검사)
  - duplicate_impl_gate    : 자동화 경로 신규 파일 생성 시 기존 구현 확인 강제
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.ops.write_gates import duplicate_impl_gate, naver_blog_safety_gate  # noqa: E402

# 등록된 게이트 — 순서대로 실행, 첫 차단 사유가 나오면 즉시 중단
_GATES = [
    ("naver-blog-safety", naver_blog_safety_gate.check),
    ("duplicate-impl", duplicate_impl_gate.check),
]


def _print_block(gate_name: str, file_path: str, message: str) -> None:
    sep = "═" * 60
    print(sep)
    print(f"[capability-gate:{gate_name}] 작성 차단")
    print(f"  대상 파일: {file_path}")
    print(sep)
    print(f"⛔ {message}")
    print(sep)


def main() -> None:
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
    except Exception:
        sys.exit(0)

    tool_name = data.get("tool_name", "")
    if tool_name not in ("Write",):
        sys.exit(0)

    file_path: str = data.get("tool_input", {}).get("file_path", "")
    if not file_path or not file_path.endswith(".py"):
        sys.exit(0)

    content: str = data.get("tool_input", {}).get("content", "") or ""

    for gate_name, gate_check in _GATES:
        message = gate_check(file_path, content)
        if message:
            _print_block(gate_name, file_path, message)
            sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
