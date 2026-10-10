"""PreToolUse(Edit|Write) — 편집으로 새로 생기는 함수/클래스명이 저장소 다른 곳에
이미 있는지 빠르게 확인해 additionalContext 로 경고만 준다(차단하지 않음).

기존 tools/hooks/duplicate_code_check.py 는 커밋된 전체 저장소를 본문 해시로 비교하는
사후 스캔용이라, 여기서 필요한 "편집 직전 이름 매칭"과는 신호가 다르다. 그래서 별도
스크립트로 둔다(§2 기준서 참조: docs/specs/2026-09-26_ai_code_quality_gate.md).

입력: stdin JSON (Claude Code PreToolUse 훅 표준 payload).
  tool_input.file_path, tool_input.new_string(Edit) 또는 tool_input.content(Write)
출력: hookSpecificOutput.additionalContext 에 경고 텍스트(있으면). 항상 exit 0(차단 안 함).
내부 예외는 fail-open(exit 0) — 이 훅이 죽어서 모든 편집이 막히면 안 된다.
"""

from __future__ import annotations

import contextlib
import json
import re
import sys
from pathlib import Path

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다

EXCLUDED_DIR_NAMES = {
    ".git",
    "__pycache__",
    "node_modules",
    ".next",
    "dist",
    "dist-electron",
    "build",
    "venv",
    ".venv",
    "data",
    "logs",
    "archive",
    "_internal",
}

DEF_RE = re.compile(r"^\s*(?:async\s+)?def\s+(\w+)\s*\(|^\s*class\s+(\w+)\s*[:(]", re.MULTILINE)

# 흔해서 오탐만 만드는 이름은 조회 대상에서 제외
COMMON_NAMES = {
    "main",
    "run",
    "handler",
    "init",
    "setup",
    "test",
    "get",
    "post",
    "load",
    "save",
    "__init__",
    "__repr__",
    "__str__",
    "wrapper",
    "execute",
    "process",
}


def _extract_new_names(tool_input: dict) -> list[str]:
    text = tool_input.get("new_string") or tool_input.get("content") or ""
    if not text:
        return []
    names = set()
    for m in DEF_RE.finditer(text):
        name = m.group(1) or m.group(2)
        if name and name not in COMMON_NAMES:
            names.add(name)
    return sorted(names)


def _top_level_dir(file_path: str) -> Path:
    p = Path(file_path)
    try:
        rel = p.resolve().relative_to(ROOT)
    except ValueError:
        return ROOT
    parts = rel.parts
    if len(parts) <= 1:
        return ROOT
    return ROOT / parts[0]


def _search_name(name: str, search_root: Path, skip_file: Path) -> list[str]:
    pattern = re.compile(r"\b(?:def|class)\s+" + re.escape(name) + r"\b")
    hits: list[str] = []
    if not search_root.exists():
        return hits
    for py in search_root.rglob("*.py"):
        if any(part in EXCLUDED_DIR_NAMES for part in py.parts):
            continue
        try:
            if py.resolve() == skip_file.resolve():
                continue
        except OSError as exc:
            sys.stderr.write(f"[pre_edit_dup_check] resolve failed for {py} (ignored): {exc}\n")
        try:
            content = py.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if pattern.search(content):
            hits.append(str(py.relative_to(ROOT)))
            if len(hits) >= 3:
                break
    return hits


def main() -> int:
    # 훅 출력은 하네스가 UTF-8 로 읽는다. 파이프로 연결되면 파이썬 기본 인코딩이 cp949 라 한글이 깨져
    # 사용자에게 안내 문구(예: /clear 안내)가 읽히지 않았다(2026-10-01).
    for _stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(Exception):
            _stream.reconfigure(encoding="utf-8", errors="replace")
    try:
        payload = json.load(sys.stdin)
    except Exception:  # noqa: BLE001 - PreToolUse 훅 진입점 — stdin JSON 파싱 실패 및 내부 오류를 모두 return 0(허용)으로 처리하는 코드 내 주석(# fail-open)으로 이미 의도가 명시된 fail-open 훅
        return 0

    try:
        tool_input = payload.get("tool_input") or {}
        file_path = tool_input.get("file_path") or ""
        if not file_path:
            return 0

        names = _extract_new_names(tool_input)
        if not names:
            return 0

        search_root = _top_level_dir(file_path)
        target = Path(file_path)

        warnings = []
        for name in names[:10]:  # 과도한 스캔 방지
            hits = _search_name(name, search_root, target)
            if len(hits) >= 2:
                warnings.append(f"- `{name}`: 이미 {len(hits)}곳에서 정의됨 ({', '.join(hits)})")

        if not warnings:
            return 0

        context = (
            "[중복 구현 가능성 경고 — 차단 아님, 참고용]\n"
            "아래 이름은 이미 다른 파일에도 정의돼 있습니다. 새로 짜는 대신 기존 것을 "
            "재사용/import 하는 것을 우선 검토하세요.\n" + "\n".join(warnings)
        )
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "additionalContext": context,
                    }
                }
            )
        )
        return 0
    except Exception as exc:  # fail-open  # noqa: BLE001 - PreToolUse 훅 진입점 — stdin JSON 파싱 실패 및 내부 오류를 모두 return 0(허용)으로 처리하는 코드 내 주석(# fail-open)으로 이미 의도가 명시된 fail-open 훅
        sys.stderr.write(f"[pre_edit_dup_check] internal error (ignored): {exc}\n")
        return 0


if __name__ == "__main__":
    sys.exit(main())
