"""Local AI agent service.

Execution flow:
  1. Run Anthropic SDK without direct cross-app MCP by default.
  2. Fall back to Claude Code CLI when no SDK provider is available.
  3. Forward cross-app CAD work only through approved CAD bridge API requests.

Security:
  - Strip *_API_KEY and *_SECRET from subprocess env where possible.
  - Mask raw sk-* keys in logs.
  - Keep shell=True disabled.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
from pathlib import Path
from typing import Any

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
    """CAD MCP direct discovery is disabled.

    Cross-app CAD access must go through the approved CAD bridge HTTP API.
    Do not auto-discover sibling repositories or legacy CAD path env here.
    """
    return None


def _cad_bridge_status_summary() -> dict[str, Any]:
    """Return CAD bridge API status without exposing local repository paths."""
    try:
        from .cad_bridge_registry import check_status, load_default_config

        status = check_status(load_default_config())
        return {
            "available": status.status == "RUNNING",
            "mode": "approved_api_bridge",
            "status": status.status,
            "host": status.host,
            "port": status.port,
        }
    except Exception as exc:  # noqa: BLE001
        logger.debug("cad bridge status unavailable: %s", type(exc).__name__)
        return {
            "available": False,
            "mode": "approved_api_bridge",
            "status": "UNKNOWN",
        }


def _api_bridge_requested(req: dict) -> bool:
    action = str(req.get("api_action") or req.get("action") or "").strip()
    return bool(req.get("api_path") or action == "cad_bridge_api")


def _cad_api_command_id(method: str, path: str) -> str:
    return f"{method.upper()}:{path.strip()}"


def _get_cad_api_approval_store() -> Any:
    from local_agent.cad.command_approval import DEFAULT_APPROVAL_STORE

    return DEFAULT_APPROVAL_STORE


def _consume_cad_api_approval(req: dict, method: str, path: str) -> tuple[bool, str]:
    approval_id = str(req.get("approval_id") or req.get("_approval_id") or "").strip()
    approval_token = str(req.get("approval_token") or req.get("_approval_token") or "").strip()
    if not approval_id:
        return False, "CAD_API_APPROVAL_ID_MISSING"
    if not approval_token:
        return False, "CAD_API_APPROVAL_TOKEN_MISSING"

    try:
        store = _get_cad_api_approval_store()
        record = store.get_record(approval_id)
        expected_command = _cad_api_command_id(method, path)
        if record.commandId != expected_command or record.toolId != "cad_bridge_api":
            return False, "CAD_API_APPROVAL_SCOPE_MISMATCH"
        if not store.consume(approval_id, approval_token):
            return False, "CAD_API_APPROVAL_INVALID"
        return True, ""
    except Exception as exc:  # noqa: BLE001
        logger.warning("cad api approval verification failed: %s", type(exc).__name__)
        return False, "CAD_API_APPROVAL_INVALID"


async def _run_approved_api_bridge(req: dict, model: str) -> dict:
    """Forward an approved cross-app request through the CAD bridge API proxy."""
    path = str(req.get("api_path") or "").strip()
    method = str(req.get("api_method") or "POST").strip().upper()
    payload = req.get("api_payload", {})
    if not path:
        return _provider_error_response(
            error_code="CAD_API_PATH_EMPTY",
            user_message="Approved API path is empty.",
            next_actions=["Use an allowlisted CAD bridge API path."],
            provider="approved_api_bridge",
            model=model,
            can_retry=True,
        )

    if method not in {"GET", "POST"}:
        return _provider_error_response(
            error_code="CAD_API_METHOD_BLOCKED",
            user_message="CAD bridge API method is not allowed.",
            next_actions=["Use only GET or POST allowlisted paths."],
            provider="approved_api_bridge",
            model=model,
            can_retry=False,
        )

    approved, approval_error = _consume_cad_api_approval(req, method, path)
    if not approved:
        return _provider_error_response(
            error_code=approval_error or _CROSS_APP_APPROVAL_ERROR,
            user_message="Cross-app calls require a valid one-time approval token.",
            next_actions=["Create and approve a scoped CAD API request before retrying."],
            provider="approved_api_bridge",
            model=model,
            can_retry=True,
        )

    from . import cad_bridge_proxy

    body = None
    headers = {"content-type": "application/json", "accept": "application/json"}
    if method == "POST":
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    resp = await cad_bridge_proxy.proxy_cad_bridge_request(
        method,
        path,
        body=body,
        headers=headers,
    )
    result = resp.body.decode("utf-8", errors="replace")
    return {
        "ok": 200 <= resp.status_code < 300,
        "result": result,
        "provider": "approved_api_bridge",
        "model": model,
        "tool_calls": 0,
        "api_status": resp.status_code,
        "approval_id": str(req.get("approval_id") or req.get("_approval_id") or ""),
    }


# ── Anthropic SDK 가용 여부 ───────────────────────────────────────────────────

def _anthropic_available() -> bool:
    try:
        import anthropic  # noqa: F401
        return bool(os.environ.get("ANTHROPIC_API_KEY"))
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

    model: str = req.get("model", "claude-sonnet-4-5")
    if _api_bridge_requested(req):
        return await _run_approved_api_bridge(req, model)

    use_mcp: bool = req.get("use_mcp", False)
    if use_mcp:
        return _provider_error_response(
            error_code=_CROSS_APP_APPROVAL_ERROR,
            user_message="Direct CAD MCP execution is disabled. Use an approved API bridge request.",
            next_actions=["Route CAD work through the approval gate and CAD bridge API proxy."],
            provider="approved_api_bridge",
            model=model,
            can_retry=True,
        )

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

    provider = "anthropic_sdk"

    try:
        if _anthropic_available():
            result = await asyncio.wait_for(
                _run_with_anthropic_no_mcp(prompt, model),
                timeout=_AGENT_TIMEOUT_SEC,
            )
            provider = "anthropic_sdk"
        else:
            logger.info("ANTHROPIC_API_KEY missing; falling back to Claude Code CLI")
            result = await asyncio.wait_for(
                _run_with_claude_code_cli(prompt),
                timeout=_AGENT_TIMEOUT_SEC,
            )
            provider = "claude_code_cli"

        return {"ok": True, "result": result, "provider": provider, "model": model, "tool_calls": 0}

    except asyncio.TimeoutError:
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
    cad_status = _cad_bridge_status_summary()
    cad_ok = bool(cad_status.get("available"))
    cdp_ok = _check_cdp_available()

    if not cad_ok:
        warnings_list.append("CAD_API_BRIDGE_NOT_READY")
    if not cdp_ok:
        warnings_list.append("CDP_BROWSER_NOT_RUNNING")

    optional_status = {
        "cad": {
            "available": cad_ok,
            "mode": cad_status.get("mode"),
            "status": cad_status.get("status"),
            "host": cad_status.get("host"),
            "port": cad_status.get("port"),
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
            "cad_bridge": h.get("cad_bridge", {}),
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
    cad_status = _cad_bridge_status_summary()

    available = (has_sdk and has_api_key) or has_claude_cli

    return {
        "available": available,
        "anthropic_sdk": has_sdk,
        "api_key_set": has_api_key,
        "claude_cli": has_claude_cli,
        "mcp_server_found": False,
        "mcp_server_path": None,
        "cad_bridge": cad_status,
    }
