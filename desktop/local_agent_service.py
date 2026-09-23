"""Local AI agent service.

LLM 경계: 앱 표준 실행 = OpenAI(GPT). _run_with_openai_no_mcp 가 기본 경로이며
claude 모델명이 와도 gpt 로 매핑한다. Claude Code CLI 는 OpenAI 미가용 시 폴백
(=터미널 Claude Code 경계)에만 쓰인다. 앱 본 기능은 GPT 전용.

Execution flow:
  1. Run OpenAI(GPT) without direct cross-app MCP by default.
  2. Fall back to Claude Code CLI when no OpenAI provider is available.

Security:
  - Strip *_API_KEY and *_SECRET from subprocess env where possible.
  - Mask raw sk-* keys in logs.
  - Keep shell=True disabled.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

# ── 상수 ─────────────────────────────────────────────────────────────────────
_AGENT_TIMEOUT_SEC = 120
_CROSS_APP_APPROVAL_ERROR = "CROSS_APP_API_APPROVAL_REQUIRED"


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
    """Direct MCP server discovery is disabled.

    Do not auto-discover sibling repositories here.
    """
    return None


# ── OpenAI SDK 가용 여부 ─────────────────────────────────────────────────────


def _anthropic_available() -> bool:
    """하위 호환 — OpenAI 키 설정 여부로 대체."""
    try:
        import openai  # noqa: F401

        return bool(os.environ.get("OPENAI_API_KEY"))
    except ImportError:
        return False


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
        claude_bin,
        "-p",
        prompt,
        "--output-format",
        "text",
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
            "model": str (optional, 기본 gpt-4o-mini),
            "use_mcp": bool (optional, default False; direct MCP is blocked),
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

    model: str = req.get("model", "gpt-4o-mini")  # 앱 표준=GPT
    use_mcp: bool = req.get("use_mcp", False)
    if use_mcp:
        return _provider_error_response(
            error_code=_CROSS_APP_APPROVAL_ERROR,
            user_message="Direct MCP execution is disabled.",
            next_actions=["Run without use_mcp."],
            provider="approved_api_bridge",
            model=model,
            can_retry=True,
        )

    # provider preflight — 실행 전 가용 여부 확인
    has_sdk_provider = _anthropic_available()  # OpenAI 키 여부
    has_cli_provider = bool(shutil.which("claude"))

    if not has_sdk_provider and not has_cli_provider:
        has_api_key = bool(os.environ.get("OPENAI_API_KEY"))
        if not has_api_key and not has_cli_provider:
            return _provider_error_response(
                error_code="NO_PROVIDER_AVAILABLE",
                user_message="AI 에이전트를 실행할 수 없습니다. OPENAI_API_KEY 또는 Claude CLI가 필요합니다.",
                next_actions=[
                    "설정에서 OpenAI API 키를 등록하세요.",
                    "Claude Code CLI 설치 상태를 확인하세요.",
                ],
                model=model,
                can_retry=True,
            )
        if has_api_key and not has_sdk_provider:
            return _provider_error_response(
                error_code="PROVIDER_NOT_READY",
                user_message="OpenAI SDK가 설치되어 있지 않습니다.",
                next_actions=["pip install openai 으로 SDK를 설치하세요."],
                model=model,
                can_retry=True,
            )

    provider = "openai_sdk"

    try:
        if _anthropic_available():
            result = await asyncio.wait_for(
                _run_with_openai_no_mcp(prompt, model),
                timeout=_AGENT_TIMEOUT_SEC,
            )
            provider = "openai_sdk"
        else:
            logger.info("OPENAI_API_KEY missing; falling back to Claude Code CLI")
            result = await asyncio.wait_for(
                _run_with_claude_code_cli(prompt),
                timeout=_AGENT_TIMEOUT_SEC,
            )
            provider = "claude_code_cli"

        return {"ok": True, "result": result, "provider": provider, "model": model, "tool_calls": 0}

    except TimeoutError:
        return _provider_error_response(
            error_code="EXECUTION_TIMEOUT",
            user_message=f"AI agent execution exceeded {_AGENT_TIMEOUT_SEC} seconds.",
            next_actions=["Retry with a smaller task."],
            provider=provider,
            model=model,
            can_retry=True,
        )
    except Exception as exc:
        logger.error("run_local_agent error: %s", _mask_api_key(type(exc).__name__))
        return _provider_error_response(
            error_code="EXECUTION_FAILED",
            user_message="AI agent execution failed.",
            next_actions=["Retry later.", "Check the local logs."],
            provider="error",
            model=model,
            can_retry=True,
        )


async def _run_with_openai_no_mcp(prompt: str, model: str) -> str:
    """MCP 없이 OpenAI SDK 단순 호출."""
    from openai import OpenAI

    api_key = os.environ.get("OPENAI_API_KEY", "")
    client = OpenAI(api_key=api_key)
    gpt_model = "gpt-4o-mini" if "claude" in model.lower() else model
    response = await asyncio.to_thread(
        client.chat.completions.create,
        model=gpt_model,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content or ""


def local_agent_preflight() -> dict:
    """로컬 AI 실행 사전 점검 (preflight) — schema_version: local_agent_preflight_v1.

    can_run 계산 기준:
      - provider_status (anthropic_sdk / claude_cli) 가용 여부만 반영
      - consent.agreed=False → CONSENT_REQUIRED blocking_reason 추가
      - optional_status (cdp) down은 can_run 에 영향 없음 → warnings 에만 기록

    보안:
      - api_key 원문 절대 미노출. api_key_set=boolean 만 허용.
      - whoami / consent 조회 실패 시 crash 금지, 안전값 반환.
    """
    warnings_list: list[str] = []
    blocking_reasons: list[str] = []

    # ── provider_status ──────────────────────────────────────────────────────
    has_sdk = False
    try:
        import openai  # noqa: F401

        has_sdk = True
    except ImportError:
        pass

    has_api_key = bool(os.environ.get("OPENAI_API_KEY"))
    has_claude_cli = bool(shutil.which("claude"))

    provider_openai_ok = has_sdk and has_api_key
    provider_cli_ok = has_claude_cli

    if not has_api_key:
        blocking_reasons.append("API_KEY_MISSING")
    if not has_sdk and has_api_key:
        blocking_reasons.append("OPENAI_SDK_NOT_INSTALLED")
    if not has_claude_cli:
        blocking_reasons.append("CLAUDE_CLI_NOT_FOUND")

    provider_available = provider_openai_ok or provider_cli_ok
    if not provider_available:
        blocking_reasons.append("NO_PROVIDER_AVAILABLE")

    provider_status = {
        "openai_sdk": {
            "available": provider_openai_ok,
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

    # ── optional_status (CDP) — down 이어도 can_run 불변 ─────────────────────
    cdp_ok = _check_cdp_available()

    if not cdp_ok:
        warnings_list.append("CDP_BROWSER_NOT_RUNNING")

    optional_status = {
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
        logger.debug("whoami primary lookup failed, trying env fallback")
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
        import openai  # noqa: F401

        has_sdk = True
    except ImportError:
        pass

    has_api_key = bool(os.environ.get("OPENAI_API_KEY"))
    has_claude_cli = bool(shutil.which("claude"))

    available = (has_sdk and has_api_key) or has_claude_cli

    return {
        "available": available,
        "openai_sdk": has_sdk,
        "api_key_set": has_api_key,
        "claude_cli": has_claude_cli,
        "mcp_server_found": False,
        "mcp_server_path": None,
    }
