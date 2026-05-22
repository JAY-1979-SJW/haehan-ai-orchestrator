"""로컬 AI Agent 서비스 — MCP stdio + Anthropic SDK 직접 호출.

실행 흐름:
  1. CAD_REPO_PATH 환경변수로 mcp_server/server.py 위치 탐색
  2. MCP stdio 클라이언트로 서버 연결 → 도구 목록 획득
  3. Anthropic SDK로 Claude 호출 (tool_use 루프)
  4. ANTHROPIC_API_KEY 없으면 Claude Code CLI 폴백

보안:
  - subprocess env에서 *_API_KEY 제거 (_safe_subprocess_env)
  - API key 원문 로그 출력 금지 (sk- 패턴 마스킹)
  - shell=True 금지
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── 상수 ─────────────────────────────────────────────────────────────────────
_AGENT_TIMEOUT_SEC = 120
_MAX_TOOL_ROUNDS = 10


# ── 보안 유틸 ─────────────────────────────────────────────────────────────────

def _safe_subprocess_env() -> dict[str, str]:
    """subprocess 실행 시 API 키를 제거한 환경변수 반환."""
    env = dict(os.environ)
    for k in list(env.keys()):
        if k.upper().endswith("_API_KEY") or k.upper().endswith("_SECRET"):
            del env[k]
    return env


def _mask_api_key(text: str) -> str:
    """sk- 패턴 API 키를 마스킹."""
    return re.sub(r"sk-[A-Za-z0-9\-_]{6,}", "sk-***MASKED***", text)


# ── MCP 서버 경로 탐색 ────────────────────────────────────────────────────────

def _find_mcp_server() -> Path | None:
    """CAD_REPO_PATH 환경변수 또는 상대경로로 mcp_server/server.py 탐색."""
    candidates: list[Path] = []

    # 1. 환경변수 명시
    cad_root = os.environ.get("CAD_REPO_PATH", "")
    if cad_root:
        candidates.append(Path(cad_root) / "mcp_server" / "server.py")

    # 2. orchestrator 프로젝트에서 나란히 있는 CAD 프로젝트 (개발 환경)
    this_dir = Path(__file__).resolve().parent.parent  # orchestrator 루트
    candidates.append(
        this_dir.parent / "14. CAD 산출 프로그램_WORK" / "mcp_server" / "server.py"
    )

    for p in candidates:
        if p.exists():
            logger.info("MCP server 경로 확인: %s", p)
            return p

    logger.warning("mcp_server/server.py 를 찾지 못했습니다. 후보: %s", candidates)
    return None


# ── Anthropic SDK 가용 여부 ───────────────────────────────────────────────────

def _anthropic_available() -> bool:
    try:
        import anthropic  # noqa: F401
        return bool(os.environ.get("ANTHROPIC_API_KEY"))
    except ImportError:
        return False


# ── MCP stdio 클라이언트 (경량 구현) ─────────────────────────────────────────

class _McpStdioClient:
    """MCP stdio 전송 클라이언트 (최소 구현).

    FastMCP/MCP SDK 없이도 동작하도록 JSON-RPC over stdin/stdout 을 직접 구현.
    """

    def __init__(self, server_path: Path) -> None:
        self._server_path = server_path
        self._proc: asyncio.subprocess.Process | None = None
        self._req_id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._reader_task: asyncio.Task | None = None

    async def start(self) -> None:
        python = sys.executable
        env = dict(os.environ)  # MCP 서버는 API 키가 필요할 수 있으므로 유지
        self._proc = await asyncio.create_subprocess_exec(
            python, str(self._server_path),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        self._reader_task = asyncio.create_task(self._read_loop())
        # MCP initialize 핸드셰이크
        await self._call("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "local_agent_service", "version": "1.0"},
        })
        logger.info("MCP stdio 클라이언트 초기화 완료")

    async def _read_loop(self) -> None:
        assert self._proc and self._proc.stdout
        try:
            async for line in self._proc.stdout:
                raw = line.decode("utf-8", errors="replace").strip()
                if not raw:
                    continue
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                req_id = msg.get("id")
                if req_id is not None and req_id in self._pending:
                    fut = self._pending.pop(req_id)
                    if not fut.done():
                        if "error" in msg:
                            fut.set_exception(RuntimeError(str(msg["error"])))
                        else:
                            fut.set_result(msg.get("result"))
        except Exception as exc:
            logger.debug("MCP read_loop 종료: %s", exc)

    async def _call(self, method: str, params: dict) -> Any:
        self._req_id += 1
        rid = self._req_id
        payload = json.dumps({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        assert self._proc and self._proc.stdin
        self._proc.stdin.write((payload + "\n").encode("utf-8"))
        await self._proc.stdin.drain()
        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[rid] = fut
        return await asyncio.wait_for(fut, timeout=30)

    async def list_tools(self) -> list[dict]:
        result = await self._call("tools/list", {})
        return result.get("tools", []) if result else []

    async def call_tool(self, name: str, arguments: dict) -> Any:
        result = await self._call("tools/call", {"name": name, "arguments": arguments})
        return result

    async def close(self) -> None:
        if self._reader_task:
            self._reader_task.cancel()
        if self._proc:
            try:
                self._proc.stdin.close()  # type: ignore[union-attr]
                await self._proc.wait()
            except Exception:
                pass


# ── Anthropic SDK 기반 agent ──────────────────────────────────────────────────

async def _run_with_anthropic(prompt: str, mcp: _McpStdioClient, model: str) -> str:
    """Anthropic SDK + MCP tool_use 루프."""
    import anthropic

    tools_raw = await mcp.list_tools()

    # Anthropic 형식으로 변환
    tools_for_claude: list[dict] = []
    for t in tools_raw:
        tools_for_claude.append({
            "name": t["name"],
            "description": t.get("description", ""),
            "input_schema": t.get("inputSchema", {"type": "object", "properties": {}}),
        })

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    messages: list[dict] = [{"role": "user", "content": prompt}]

    for _round in range(_MAX_TOOL_ROUNDS):
        kwargs: dict[str, Any] = dict(
            model=model,
            max_tokens=4096,
            messages=messages,
        )
        if tools_for_claude:
            kwargs["tools"] = tools_for_claude

        response = await asyncio.to_thread(client.messages.create, **kwargs)
        stop_reason = response.stop_reason

        # 응답 메시지를 누적
        messages.append({"role": "assistant", "content": response.content})

        if stop_reason == "end_turn":
            # 텍스트 블록 추출
            texts = [b.text for b in response.content if hasattr(b, "text")]
            return "\n".join(texts)

        if stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                logger.info("도구 호출: %s(%s)", block.name, list(block.input.keys()))
                try:
                    result = await mcp.call_tool(block.name, block.input)
                    content_str = json.dumps(result, ensure_ascii=False)
                except Exception as exc:
                    content_str = f"오류: {exc}"

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": content_str,
                })

            messages.append({"role": "user", "content": tool_results})
        else:
            # 예상치 못한 stop_reason
            break

    return "에이전트 최대 라운드 초과"


# ── Claude Code CLI 폴백 ──────────────────────────────────────────────────────

async def _run_with_claude_code_cli(prompt: str) -> str:
    """Claude Code CLI (`claude`) 폴백 실행."""
    claude_bin = shutil.which("claude")
    if not claude_bin:
        return "오류: claude CLI 를 찾을 수 없습니다. ANTHROPIC_API_KEY 또는 claude CLI 를 설치하세요."

    env = _safe_subprocess_env()
    # API 키는 claude CLI가 자체 관리하므로 제거하지 않음
    env.update({k: v for k, v in os.environ.items() if k.upper().endswith("_API_KEY")})

    proc = await asyncio.create_subprocess_exec(
        claude_bin, "-p", prompt, "--output-format", "text",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=_AGENT_TIMEOUT_SEC)
    out = stdout.decode("utf-8", errors="replace").strip()
    err = stderr.decode("utf-8", errors="replace").strip()
    if proc.returncode != 0:
        logger.warning("claude CLI 오류 (rc=%d): %s", proc.returncode, _mask_api_key(err))
        return f"Claude Code CLI 오류 (rc={proc.returncode}): {err[:500]}"
    return out


# ── 공개 API ──────────────────────────────────────────────────────────────────

async def run_local_agent(req: dict) -> dict:
    """로컬 AI + 로컬 MCP 실행.

    Args:
        req: {
            "prompt": str,
            "model": str (optional, 기본 claude-sonnet-4-5),
            "use_mcp": bool (optional, 기본 True),
        }

    Returns:
        {
            "ok": bool,
            "result": str,
            "provider": str,  # "anthropic_sdk" | "claude_code_cli" | "error"
            "model": str,
            "tool_calls": int,
        }
    """
    prompt: str = req.get("prompt", "").strip()
    if not prompt:
        return {"ok": False, "result": "prompt 가 비어 있습니다.", "provider": "error", "model": "", "tool_calls": 0}

    model: str = req.get("model", "claude-sonnet-4-5")
    use_mcp: bool = req.get("use_mcp", True)

    mcp: _McpStdioClient | None = None
    provider = "anthropic_sdk"

    try:
        # MCP 연결 시도
        if use_mcp:
            mcp_path = _find_mcp_server()
            if mcp_path:
                mcp = _McpStdioClient(mcp_path)
                try:
                    await mcp.start()
                except Exception as exc:
                    logger.warning("MCP 시작 실패 (무시하고 진행): %s", exc)
                    mcp = None

        # Anthropic SDK 우선
        if _anthropic_available():
            result = await asyncio.wait_for(
                _run_with_anthropic(prompt, mcp, model) if mcp else _run_with_anthropic_no_mcp(prompt, model),
                timeout=_AGENT_TIMEOUT_SEC,
            )
            provider = "anthropic_sdk"
        else:
            # Claude Code CLI 폴백
            logger.info("ANTHROPIC_API_KEY 없음 — Claude Code CLI 폴백")
            result = await asyncio.wait_for(
                _run_with_claude_code_cli(prompt),
                timeout=_AGENT_TIMEOUT_SEC,
            )
            provider = "claude_code_cli"

        return {"ok": True, "result": result, "provider": provider, "model": model, "tool_calls": 0}

    except asyncio.TimeoutError:
        return {"ok": False, "result": "타임아웃 (120초 초과)", "provider": provider, "model": model, "tool_calls": 0}
    except Exception as exc:
        logger.error("run_local_agent 오류: %s", _mask_api_key(str(exc)))
        return {"ok": False, "result": f"오류: {exc}", "provider": "error", "model": model, "tool_calls": 0}
    finally:
        if mcp:
            await mcp.close()


async def _run_with_anthropic_no_mcp(prompt: str, model: str) -> str:
    """MCP 없이 Anthropic SDK 단순 호출."""
    import anthropic

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    response = await asyncio.to_thread(
        client.messages.create,
        model=model,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    texts = [b.text for b in response.content if hasattr(b, "text")]
    return "\n".join(texts)


def local_agent_health() -> dict:
    """로컬 AI 가용 여부 상태 반환."""
    has_sdk = False
    try:
        import anthropic  # noqa: F401
        has_sdk = True
    except ImportError:
        pass

    has_api_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    has_claude_cli = bool(shutil.which("claude"))
    mcp_path = _find_mcp_server()

    available = (has_sdk and has_api_key) or has_claude_cli

    return {
        "available": available,
        "anthropic_sdk": has_sdk,
        "api_key_set": has_api_key,
        "claude_cli": has_claude_cli,
        "mcp_server_found": mcp_path is not None,
        "mcp_server_path": str(mcp_path) if mcp_path else None,
    }
