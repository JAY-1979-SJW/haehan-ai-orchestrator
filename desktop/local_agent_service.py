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

def _provider_error_response(
    error_code: str,
    user_message: str,
    next_actions: list[str],
    provider: str = "error",
    model: str = "",
    can_retry: bool = False,
) -> dict:
    """provider 오류 표준 응답 빌더.

    기존 키(ok/result/provider/model/tool_calls) 보존.
    추가 키(error_code/user_message/next_actions/can_retry/safe_to_show) 포함.
    raw exception 원문 / secret / token 미노출.
    """
    return {
        "ok": False,
        "result": user_message,
        "provider": provider,
        "model": model,
        "tool_calls": 0,
        "error_code": error_code,
        "user_message": user_message,
        "next_actions": next_actions,
        "provider_status": {
            "anthropic_sdk": {
                "available": _anthropic_available(),
                "api_key_set": bool(os.environ.get("ANTHROPIC_API_KEY")),
            },
            "claude_cli": {
                "available": bool(shutil.which("claude")),
            },
        },
        "can_retry": can_retry,
        "safe_to_show": True,
    }


async def run_local_agent(req: dict) -> dict:
    """로컬 AI + 로컬 MCP 실행.

    Args:
        req: {
            "prompt": str,
            "model": str (optional, 기본 claude-sonnet-4-5),
            "use_mcp": bool (optional, 기본 True),
        }

    Returns (기존 키 보존 + P3 확장 키):
        {
            "ok": bool,
            "result": str,
            "provider": str,  # "anthropic_sdk" | "claude_code_cli" | "error"
            "model": str,
            "tool_calls": int,
            # P3 추가 (오류 시만 포함):
            "error_code": str,
            "user_message": str,
            "next_actions": list[str],
            "provider_status": dict,
            "can_retry": bool,
            "safe_to_show": bool,
        }
    """
    prompt: str = req.get("prompt", "").strip()
    if not prompt:
        return _provider_error_response(
            error_code="PROMPT_EMPTY",
            user_message="실행할 명령(prompt)이 비어 있습니다.",
            next_actions=["실행할 작업 내용을 입력하세요."],
        )

    model: str = req.get("model", "claude-sonnet-4-5")
    use_mcp: bool = req.get("use_mcp", True)

    # provider preflight — 실행 전 가용 여부 확인
    has_sdk_provider = _anthropic_available()
    has_cli_provider = bool(shutil.which("claude"))

    if not has_sdk_provider and not has_cli_provider:
        has_api_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
        if not has_api_key and not has_cli_provider:
            return _provider_error_response(
                error_code="NO_PROVIDER_AVAILABLE",
                user_message="AI 에이전트를 실행할 수 없습니다. API 키 또는 Claude CLI가 필요합니다.",
                next_actions=[
                    "설정에서 Anthropic API 키를 등록하세요.",
                    "Claude Code CLI 설치 상태를 확인하세요.",
                ],
                model=model,
                can_retry=True,
            )
        if has_api_key and not has_sdk_provider:
            return _provider_error_response(
                error_code="PROVIDER_NOT_READY",
                user_message="Anthropic SDK가 설치되어 있지 않습니다.",
                next_actions=["pip install anthropic 으로 SDK를 설치하세요."],
                model=model,
                can_retry=True,
            )

    mcp: _McpStdioClient | None = None
    provider = "anthropic_sdk"

    try:
        if use_mcp:
            mcp_path = _find_mcp_server()
            if mcp_path:
                mcp = _McpStdioClient(mcp_path)
                try:
                    await mcp.start()
                except Exception as exc:
                    logger.warning("MCP 시작 실패 (무시하고 진행): %s", exc)
                    mcp = None

        if _anthropic_available():
            result = await asyncio.wait_for(
                _run_with_anthropic(prompt, mcp, model) if mcp else _run_with_anthropic_no_mcp(prompt, model),
                timeout=_AGENT_TIMEOUT_SEC,
            )
            provider = "anthropic_sdk"
        else:
            logger.info("ANTHROPIC_API_KEY 없음 — Claude Code CLI 폴백")
            result = await asyncio.wait_for(
                _run_with_claude_code_cli(prompt),
                timeout=_AGENT_TIMEOUT_SEC,
            )
            provider = "claude_code_cli"

        return {"ok": True, "result": result, "provider": provider, "model": model, "tool_calls": 0}

    except asyncio.TimeoutError:
        return _provider_error_response(
            error_code="EXECUTION_TIMEOUT",
            user_message=f"AI 에이전트 실행이 {_AGENT_TIMEOUT_SEC}초를 초과했습니다.",
            next_actions=["더 간단한 작업으로 재시도하세요."],
            provider=provider,
            model=model,
            can_retry=True,
        )
    except Exception as exc:
        logger.error("run_local_agent 오류: %s", _mask_api_key(type(exc).__name__))
        return _provider_error_response(
            error_code="EXECUTION_FAILED",
            user_message="AI 에이전트 실행 중 오류가 발생했습니다.",
            next_actions=["잠시 후 다시 시도하세요.", "로그를 확인하세요."],
            provider="error",
            model=model,
            can_retry=True,
        )
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


def local_agent_preflight() -> dict:
    """로컬 AI 실행 사전 점검 (preflight) — schema_version: local_agent_preflight_v1.

    can_run 계산 기준:
      - provider_status (anthropic_sdk / claude_cli) 가용 여부만 반영
      - consent.agreed=False → CONSENT_REQUIRED blocking_reason 추가
      - optional_status (cad / cdp) down은 can_run 에 영향 없음 → warnings 에만 기록

    보안:
      - api_key 원문 절대 미노출. api_key_set=boolean 만 허용.
      - whoami / consent 조회 실패 시 crash 금지, 안전값 반환.
    """
    warnings_list: list[str] = []
    blocking_reasons: list[str] = []

    # ── provider_status ──────────────────────────────────────────────────────
    has_sdk = False
    try:
        import anthropic  # noqa: F401
        has_sdk = True
    except ImportError:
        pass

    has_api_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    has_claude_cli = bool(shutil.which("claude"))

    provider_anthropic_ok = has_sdk and has_api_key
    provider_cli_ok = has_claude_cli

    if not has_api_key:
        blocking_reasons.append("API_KEY_MISSING")
    if not has_sdk and has_api_key:
        blocking_reasons.append("ANTHROPIC_SDK_NOT_INSTALLED")
    if not has_claude_cli:
        blocking_reasons.append("CLAUDE_CLI_NOT_FOUND")

    provider_available = provider_anthropic_ok or provider_cli_ok
    if not provider_available:
        blocking_reasons.append("NO_PROVIDER_AVAILABLE")

    provider_status = {
        "anthropic_sdk": {
            "available": provider_anthropic_ok,
            "sdk_installed": has_sdk,
            "api_key_set": has_api_key,
        },
        "claude_cli": {
            "available": provider_cli_ok,
        },
    }

    # ── health 요약 (local_agent_health 재사용, 안전 필드만) ─────────────────
    health = _safe_health_summary()

    # ── whoami (crash 금지) ───────────────────────────────────────────────────
    try:
        whoami = _safe_whoami_summary()
    except Exception:
        whoami = {"available": False, "role": "unknown"}

    # ── consent (crash 금지) ──────────────────────────────────────────────────
    try:
        consent = _safe_consent_summary()
    except Exception:
        consent = {"agreed": False, "source": "unavailable"}
        warnings_list.append("CONSENT_CHECK_FAILED")
    if not consent.get("agreed", False):
        blocking_reasons.append("CONSENT_REQUIRED")

    # ── can_run 최종 결정 ─────────────────────────────────────────────────────
    # CONSENT_REQUIRED 와 NO_PROVIDER_AVAILABLE 만 차단
    core_blocks = {"CONSENT_REQUIRED", "NO_PROVIDER_AVAILABLE"}
    can_run = not bool(core_blocks & set(blocking_reasons))

    # ── optional_status (CAD / CDP) — down 이어도 can_run 불변 ───────────────
    mcp_path = _find_mcp_server()
    cad_ok = mcp_path is not None
    cdp_ok = _check_cdp_available()

    if not cad_ok:
        warnings_list.append("CAD_MCP_SERVER_NOT_FOUND")
    if not cdp_ok:
        warnings_list.append("CDP_BROWSER_NOT_RUNNING")

    optional_status = {
        "cad": {
            "available": cad_ok,
            "path": str(mcp_path) if mcp_path else None,
        },
        "cdp": {
            "available": cdp_ok,
        },
    }

    # ── user_message / next_actions ───────────────────────────────────────────
    user_message, next_actions = _build_user_guidance(blocking_reasons, can_run)

    # ── blocking_reasons 중복 제거 (삽입 순서 유지) ───────────────────────────
    seen: set[str] = set()
    unique_blocking: list[str] = []
    for r in blocking_reasons:
        if r not in seen:
            seen.add(r)
            unique_blocking.append(r)

    return {
        "schema_version": "local_agent_preflight_v1",
        "ok": True,
        "can_run": can_run,
        "blocking_reasons": unique_blocking,
        "user_message": user_message,
        "next_actions": next_actions,
        "provider_status": provider_status,
        "api_key_set": has_api_key,
        "claude_cli_available": has_claude_cli,
        "health": health,
        "whoami": whoami,
        "consent": consent,
        "optional_status": optional_status,
        "warnings": warnings_list,
    }


def _safe_health_summary() -> dict:
    """local_agent_health() 에서 보안 안전 필드만 추출. 실패 시 안전값."""
    try:
        h = local_agent_health()
        return {
            "available": h.get("available", False),
            "anthropic_sdk": h.get("anthropic_sdk", False),
            "api_key_set": h.get("api_key_set", False),
            "claude_cli": h.get("claude_cli", False),
            "mcp_server_found": h.get("mcp_server_found", False),
        }
    except Exception:
        return {"available": False, "error": "health_check_failed"}


def _safe_whoami_summary() -> dict:
    """role/source/admin 요약. 실패 시 안전값 반환, crash 금지."""
    try:
        from desktop.local_server import _resolve_whoami_role  # type: ignore
        role, source = _resolve_whoami_role()
        return {
            "available": True,
            "role": role,
            "admin": role in ("admin", "owner"),
            "source": source,
        }
    except Exception:
        pass
    try:
        import os as _os
        role = _os.environ.get("HAEHAN_ROLE", "any").strip().lower()
        return {"available": True, "role": role, "admin": role in ("admin", "owner"), "source": "env_fallback"}
    except Exception:
        return {"available": False, "role": "unknown"}


def _safe_consent_summary() -> dict:
    """consent.json 상태 요약. 실패 시 agreed=False 로 안전 처리."""
    try:
        from desktop.main_launcher import check_consent_hook  # type: ignore
        result = check_consent_hook()
        return {
            "agreed": bool(result.get("agreed", False)),
            "source": result.get("source", "unknown"),
        }
    except Exception:
        return {"agreed": False, "source": "unavailable"}


def _build_user_guidance(blocking_reasons: list[str], can_run: bool) -> tuple[str, list[str]]:
    """blocking_reasons 기반으로 사용자 안내 메시지와 next_actions 생성."""
    if can_run:
        return "AI 에이전트를 실행할 준비가 되었습니다.", []

    messages: list[str] = []
    actions: list[str] = []

    if "CONSENT_REQUIRED" in blocking_reasons:
        messages.append("사용 동의가 필요합니다.")
        actions.append("앱을 처음 실행하여 사용 동의를 완료하세요.")

    if "NO_PROVIDER_AVAILABLE" in blocking_reasons or "API_KEY_MISSING" in blocking_reasons:
        messages.append("AI 에이전트를 실행하려면 API 키를 설정하거나 Claude CLI를 사용할 수 있어야 합니다.")
        actions.append("설정에서 Anthropic API 키를 등록하세요.")

    if "CLAUDE_CLI_NOT_FOUND" in blocking_reasons and "API_KEY_MISSING" in blocking_reasons:
        actions.append("Claude Code CLI 설치 상태를 확인하세요.")

    user_message = " ".join(messages) if messages else "AI 에이전트를 실행할 수 없습니다."
    return user_message, actions


def _check_cdp_available() -> bool:
    """CDP 브라우저 소켓 포트(9222) 리슨 여부 확인 — 실패해도 예외 없음."""
    import socket
    try:
        with socket.create_connection(("127.0.0.1", 9222), timeout=0.5):
            return True
    except OSError:
        return False


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
