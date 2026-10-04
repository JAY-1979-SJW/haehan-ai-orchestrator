"""`claude -p` 텍스트 생성 어댑터 — 도구·MCP 없이 글 텍스트만 만든다.

기준서: docs/specs/2026-09-30_blog_auto_writing_automation.md (v2 §4 단계 3)

Claude 에게는 쓰기 도구를 주지 않는다(`--tools ""`, `--strict-mcp-config`). 저장·발행은 앱이 직접 한다.
반환 형식은 기존 `AIResponder._call` 과 같다: `{"ok": bool, "text": str, ...}` — 그래서
`content.generate_post(llm=...)` 에 그대로 꽂힌다.

- 실행 폴더는 저장소 밖 중립 폴더(프로젝트 CLAUDE.md·훅이 딸려 오지 않게).
- `max_tokens` 는 CLI 에 대응 옵션이 없어 무시한다(비용은 `--max-budget-usd` 로 제한).
- 실행 파일이 없거나 시간 초과여도 예외 대신 `ok=False` 결과를 돌려준다.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

DEFAULT_MAX_BUDGET_USD = 1.0
DEFAULT_TIMEOUT_SECONDS = 420.0

Runner = Callable[[list[str], float, Path], "subprocess.CompletedProcess[str]"]

# 켤 수 있는 도구는 이 읽기 전용 웹 도구뿐이다. 파일 쓰기·명령 실행·MCP 는 어떤 경우에도 주지 않는다.
READ_ONLY_WEB_TOOLS = frozenset({"WebSearch", "WebFetch"})


def build_command(
    system: str,
    user: str,
    *,
    max_budget_usd: float = DEFAULT_MAX_BUDGET_USD,
    model: str | None = None,
    tools: tuple[str, ...] = (),
) -> list[str]:
    """헤드리스 텍스트 생성 명령. 기본은 도구 없음, tools 로 읽기 전용 웹 도구만 켤 수 있다.

    `--` 뒤가 사용자 프롬프트(옵션 파싱을 끊는다).
    """
    extra = set(tools) - READ_ONLY_WEB_TOOLS
    if extra:
        raise ValueError(f"허용되지 않는 도구: {sorted(extra)} (읽기 전용 웹 도구만 가능)")
    tool_list = ",".join(sorted(set(tools)))
    cmd = [
        "claude",
        "-p",
        "--output-format",
        "json",
        "--max-budget-usd",
        str(max_budget_usd),
        "--tools",
        tool_list,
    ]
    if tool_list:
        cmd += ["--allowedTools", tool_list]
    cmd += ["--strict-mcp-config", "--no-session-persistence", "--system-prompt", system]
    if model:
        cmd += ["--model", model]
    return [*cmd, "--", user]


def parse_output(stdout: str) -> dict[str, Any]:
    """`--output-format json` 출력을 {ok, text, cost_usd?, error?} 로 바꾼다."""
    try:
        data = json.loads(stdout)
    except (json.JSONDecodeError, TypeError):
        return {"ok": False, "error": "invalid_json"}
    if not isinstance(data, dict):
        return {"ok": False, "error": "invalid_json"}
    text = data.get("result")
    if data.get("is_error"):
        return {"ok": False, "error": "claude_reported_error"}
    if not isinstance(text, str) or not text.strip():
        return {"ok": False, "error": "empty_result"}
    result: dict[str, Any] = {"ok": True, "text": text.strip()}
    if isinstance(data.get("total_cost_usd"), int | float):
        result["cost_usd"] = float(data["total_cost_usd"])
    return result


def _default_run(cmd: list[str], timeout: float, cwd: Path) -> subprocess.CompletedProcess[str]:
    # 고정된 claude 명령이고 사용자 입력은 `--` 뒤 인자로만 전달한다(셸 미사용).
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
        timeout=timeout,
        check=False,
    )


def claude_available(*, which: Callable[[str], str | None] = shutil.which) -> bool:
    return which("claude") is not None


def neutral_cwd() -> Path:
    path = Path(tempfile.gettempdir()) / "haehan_blog_automation"
    path.mkdir(parents=True, exist_ok=True)
    return path


def make_claude_llm(
    *,
    run: Runner = _default_run,
    max_budget_usd: float = DEFAULT_MAX_BUDGET_USD,
    model: str | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    cwd: Path | None = None,
    tools: tuple[str, ...] = (),
) -> Callable[..., dict[str, Any]]:
    """`(system, user, max_tokens) -> {"ok", "text", ...}` 형태의 텍스트 생성 함수를 만든다."""
    build_command("", "", tools=tools)  # 허용되지 않는 도구는 만드는 시점에 바로 거부

    def llm(system: str, user: str, max_tokens: int = 0) -> dict[str, Any]:
        del max_tokens  # CLI 에 대응 옵션이 없어 무시(비용은 --max-budget-usd 로 제한)
        cmd = build_command(system, user, max_budget_usd=max_budget_usd, model=model, tools=tools)
        try:
            proc = run(cmd, timeout, cwd or neutral_cwd())
        except FileNotFoundError:
            return {"ok": False, "error": "claude_cli_not_found"}
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "timeout"}
        if not (proc.stdout or "").strip():
            return {"ok": False, "error": f"claude_exit_{proc.returncode}"}
        return parse_output(proc.stdout)

    return llm
