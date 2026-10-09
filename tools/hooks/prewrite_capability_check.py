"""PreToolUse hook: Write 시점에 등록된 안전 게이트를 순서대로 실행한다.

Claude Code PreToolUse 훅으로 실행됨.
stdin: JSON {tool_name, tool_input: {file_path, content}}

이 파일은 오케스트레이터일 뿐이고, 실제 검사 로직은 각 게이트 모듈에 있다
(scripts/ops/write_gates/) — 게이트가 늘어나도 이 파일은 등록만 하면 된다.

  - naver_blog_safety_gate : 네이버 블로그 자동화 위험 패턴(경로 무관, 내용 검사)
  - duplicate_impl_gate    : 자동화 경로 신규 파일 생성 시 기존 구현 확인 강제
"""

from __future__ import annotations

import contextlib
import json
import sys
from pathlib import Path

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
sys.path.insert(0, str(ROOT))

from tools.write_gates import duplicate_impl_gate, naver_blog_safety_gate, sitemap_gate  # noqa: E402

# 등록된 게이트 — 순서대로 실행, 첫 차단 사유가 나오면 즉시 중단
_GATES = [
    ("naver-blog-safety", naver_blog_safety_gate.check),
    ("duplicate-impl", duplicate_impl_gate.check),
]

# 경고 전용 게이트 — 작성은 막지 않고 안내만 붙인다(차단 게이트를 모두 통과한 뒤 실행)
_WARN_GATES = [
    ("sitemap", sitemap_gate.warn),
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
    # 훅 출력은 하네스가 UTF-8 로 읽는다. 파이프로 연결되면 파이썬 기본 인코딩이 cp949 라 한글이 깨져
    # 사용자에게 안내 문구(예: /clear 안내)가 읽히지 않았다(2026-10-01).
    for _stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(Exception):
            _stream.reconfigure(encoding="utf-8", errors="replace")
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
    except Exception:  # noqa: BLE001 - PreToolUse(Write) 훅 진입점 — stdin JSON 파싱 실패 시 exit(0)으로 통과시키는 의도된 fail-open, 실제 capability 검사 로직은 파싱 성공 이후 수행.
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

    warnings = [msg for _name, warn in _WARN_GATES if (msg := warn(file_path, content))]
    if warnings:
        print(
            json.dumps(
                {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": " / ".join(warnings)}},
                ensure_ascii=False,
            )
        )

    sys.exit(0)


if __name__ == "__main__":
    main()
