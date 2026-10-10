"""실시간 작업 로그 훅 스크립트.

Claude Code 훅(UserPromptSubmit / PostToolUse / Stop)으로 호출됨.
stdin JSON 이벤트를 받아 docs/worklog.md 맨 위에 실시간 기록한다.

이벤트 종류:
  user_prompt  — 사용자 지시 입력 (UserPromptSubmit)
  tool_done    — 도구 실행 완료   (PostToolUse: Bash)
  stop         — Claude 응답 완료 (Stop)
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
WORKLOG = ROOT / "docs" / "worklog.md"
MAX_CMD_LEN = 120  # Bash 명령 최대 표시 길이
MAX_RESULT_LEN = 200  # 결과 최대 표시 길이


def _now() -> str:
    return datetime.now().strftime("%H:%M")


def _date_header() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _read() -> str:
    if WORKLOG.exists():
        return WORKLOG.read_text(encoding="utf-8")
    return "# 작업 로그 (Work Log)\n\n> 최신 항목이 맨 위.\n\n---\n"


def _write(content: str) -> None:
    WORKLOG.write_text(content, encoding="utf-8")


def _ensure_today_section(text: str) -> tuple[str, int]:
    """오늘 날짜 섹션이 없으면 만들고, 섹션 시작 줄 번호를 반환."""
    header = f"## {_date_header()}"
    lines = text.splitlines(keepends=True)

    # 기존 오늘 섹션 찾기
    for i, line in enumerate(lines):
        if line.startswith(header):
            return text, i

    # 없으면 --- 다음에 삽입
    insert_at = 0
    for i, line in enumerate(lines):
        if line.strip() == "---":
            insert_at = i + 1
            break

    new_section = f"\n{header}\n\n"
    lines.insert(insert_at, new_section)
    return "".join(lines), insert_at + 1


def _append_to_today(text: str, entry: str) -> str:
    """오늘 섹션 바로 아래에 항목 추가."""
    text, section_line = _ensure_today_section(text)
    lines = text.splitlines(keepends=True)

    # 섹션 헤더 다음 빈 줄 건너뛰고 첫 내용 줄 찾기
    insert_at = section_line + 1
    while insert_at < len(lines) and lines[insert_at].strip() == "":
        insert_at += 1

    lines.insert(insert_at, entry + "\n")
    return "".join(lines)


def handle_user_prompt(event: dict) -> None:
    prompt = event.get("prompt", "").strip()
    if not prompt:
        return

    # 너무 긴 지시는 줄임
    display = prompt if len(prompt) <= 200 else prompt[:197] + "..."
    # 개행 제거
    display = display.replace("\n", " ")

    entry = f"- {_now()} **[지시]** {display}"
    text = _read()
    text = _append_to_today(text, entry)
    _write(text)


def handle_tool_done(event: dict) -> None:
    tool = event.get("tool_name", "")
    if tool != "Bash":
        return

    tool_input = event.get("tool_input", {})
    cmd = tool_input.get("command", "").strip().replace("\n", " ")
    if not cmd:
        return

    # 내부 훅 스크립트 호출은 로그 제외 (노이즈)
    skip_patterns = ["worklog_realtime", "log_code_change", "behavior_gate"]
    if any(p in cmd for p in skip_patterns):
        return

    display_cmd = cmd if len(cmd) <= MAX_CMD_LEN else cmd[: MAX_CMD_LEN - 3] + "..."

    entry = f"- {_now()} **[실행]** `{display_cmd}`"
    text = _read()
    text = _append_to_today(text, entry)
    _write(text)


def handle_stop(event: dict) -> None:
    stop_reason = event.get("stop_reason", "")
    # 정상 완료만 기록 (tool_use 중간 stop은 제외)
    if stop_reason and stop_reason != "end_turn":
        return

    entry = f"- {_now()} **[완료]** 응답 종료"
    text = _read()

    # 오늘 섹션에 [완료]가 이미 있으면 덮어쓰기 대신 skip (중복 방지)
    # 단, [지시]나 [실행]이 있을 때만 기록
    header = f"## {_date_header()}"
    if header not in text:
        return

    # 마지막 [완료] 항목 교체 (같은 응답 내 중복 방지)
    pattern = r"(- \d{2}:\d{2} \*\*\[완료\]\*\* 응답 종료\n)"
    last_match = None
    for m in re.finditer(pattern, text):
        last_match = m
    if last_match:
        text = text[: last_match.start()] + entry + "\n" + text[last_match.end() :]
        _write(text)
    else:
        text = _append_to_today(text, entry)
        _write(text)


def handle_session() -> None:
    """SessionStart: 가장 최근 섹션(오늘 포함) 전체를 출력."""
    if not WORKLOG.exists():
        return
    text = WORKLOG.read_text(encoding="utf-8")
    m = re.search(r"(## \d{4}-\d{2}-\d{2}.*?)(?=\n## |\Z)", text, re.DOTALL)
    if m:
        section = m.group(1).strip()
        print(section[:3000])
    else:
        print(text[:1000])


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""

    if mode == "session":
        handle_session()
        return

    try:
        raw = sys.stdin.read()
        event = json.loads(raw) if raw.strip() else {}
    except Exception:  # noqa: BLE001 - Claude Code 훅 진입점 — stdin 읽기/JSON 파싱 실패시 조용히 반환(무동작), 기타 처리 오류는 stderr 로그만 남기는 의도된 fail-open(워크로그 기록 실패가 본작업을 막지 않도록)
        return

    try:
        if mode == "prompt":
            handle_user_prompt(event)
        elif mode == "tool":
            handle_tool_done(event)
        elif mode == "stop":
            handle_stop(event)
    except Exception as e:  # noqa: BLE001 - Claude Code 훅 진입점 — stdin 읽기/JSON 파싱 실패시 조용히 반환(무동작), 기타 처리 오류는 stderr 로그만 남기는 의도된 fail-open(워크로그 기록 실패가 본작업을 막지 않도록)
        sys.stderr.write(f"[worklog_realtime] 오류: {e}\n")


if __name__ == "__main__":
    main()
