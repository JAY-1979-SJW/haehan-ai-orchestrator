"""PreToolUse hook: Write/Edit 시 기존 구현 조회 후 신규 파일이면 차단.

Claude Code PreToolUse 훅으로 실행됨.
stdin: JSON {tool_name, tool_input: {file_path, content}}

동작:
  - 자동화 경로(scripts/naver/, ai_orchestrator/connectors/ 등)에 신규 파일 생성 시
  - capability_check.py 실행 → 기존 구현 발견 → exit 2 (Claude Code가 Write 차단)
  - 기존 파일 수정 or 비자동화 경로 or 기존 구현 없음 → exit 0 (통과)
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# 신규 파일 생성 시 기존 구현 확인을 강제하는 경로
_AUTO_DIRS = [
    "scripts/naver/",
    "scripts/eum",
    "scripts/browser_agent/",
    "ai_orchestrator/connectors/",
    "desktop/",
]

# capability_check 키워드 추출 시 제외할 공통 조각
_SKIP_PARTS = {
    "scripts",
    "naver",
    "ai",
    "orchestrator",
    "connectors",
    "ops",
    "desktop",
    "browser",
    "agent",
    "collection",
    "analysis",
    "write",
}


def _is_automation_path(path: str) -> bool:
    p = path.replace("\\", "/")
    return any(p.startswith(d) for d in _AUTO_DIRS)


def _extract_keywords(path: str) -> list[str]:
    """경로에서 capability_check 검색 키워드 추출."""
    p = path.replace("\\", "/")
    # 경로 조각(디렉터리명)에서만 추출 — 파일명 제외 (신규 파일이라 의미 없음)
    dir_parts = p.split("/")[:-1]  # 파일명(마지막) 제외
    keywords: list[str] = []
    for part in dir_parts:
        word = part.lower().replace("-", "")
        if word and word not in _SKIP_PARTS and len(word) >= 3:
            if word not in keywords:
                keywords.append(word)
        if len(keywords) >= 2:
            break
    return keywords


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

    if not _is_automation_path(file_path.replace("\\", "/")):
        sys.exit(0)

    # 이미 존재하는 파일 수정 → 통과 (신규 생성만 검사)
    full = Path(file_path) if Path(file_path).is_absolute() else ROOT / file_path
    if full.exists():
        sys.exit(0)

    keywords = _extract_keywords(file_path)
    if not keywords:
        sys.exit(0)

    # capability_check 실행
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "ops" / "capability_check.py"), *keywords],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    output = (proc.stdout or "").strip()

    if not output or "기존 구현 없음" in output:
        sys.exit(0)

    # 기존 구현 발견 → 차단
    sep = "═" * 60
    print(sep)
    print("[capability-gate] 신규 파일 생성 전 기존 구현 확인 필수")
    print(f"  대상 파일  : {file_path}")
    print(f"  검색 키워드: {' '.join(keywords)}")
    print(sep)
    print(output)
    print(sep)
    print("⛔ 기존 구현이 있습니다.")
    print("   위 API / 함수를 먼저 사용하세요.")
    print("   정말 신규 파일이 필요하면 기존 구현과 완전히 다른 기능임을")
    print("   먼저 설명한 뒤 작성하세요.")
    print(sep)
    sys.exit(2)


if __name__ == "__main__":
    main()
