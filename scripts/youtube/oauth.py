"""User-approved YouTube OAuth token helper.

This module only implements the official OAuth installed-app flow. It never
prints client secrets, access tokens, or refresh tokens.
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ai_orchestrator.paths.runtime import data_dir
from scripts.auth import local_user_secret_store
from scripts.common.app_paths import repo_root
from scripts.common.gates.secret_action_gate import build_secret_action_policy, normalize_secret_action_mode
from scripts.common.gates.work_mode_gate import build_google_work_mode_policy
from ai_orchestrator.core.security_utils import safe_preview

ROOT = repo_root()
REPORT_DIR = data_dir() / "youtube_oauth_reports"
TOKEN_DIR = data_dir() / "secrets"
LATEST_AUTH_PLAN = data_dir() / "youtube_oauth_auth_plan_latest.json"
LATEST_TOKEN_RESULT = data_dir() / "youtube_oauth_token_result_latest.json"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
DEFAULT_REDIRECT_URI = "http://127.0.0.1:8765/oauth2callback"
DEFAULT_TOKEN_FILE = TOKEN_DIR / "youtube_oauth_authorized_user.json"
SERVER_REDIRECT_URI = "https://haehan-ai.kr/orchestrator/api/v1/oauth/youtube/callback"
SERVER_CLIENT_FILE = "/run/secrets/api/youtube_oauth_client.json"
SERVER_TOKEN_FILE = "/app/ai_orchestrator/storage/secrets/youtube_oauth_authorized_user.json"
LOCAL_CLIENT_SECRET_REF = "local-secret://youtube/oauth_client_json"
YOUTUBE_SCOPES = {
    "readonly": "https://www.googleapis.com/auth/youtube.readonly",
    "upload": "https://www.googleapis.com/auth/youtube.upload",
    "force-ssl": "https://www.googleapis.com/auth/youtube.force-ssl",
}


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _resolve(path: str | Path) -> Path:
    resolved = Path(path)
    if not resolved.is_absolute():
        resolved = ROOT / resolved
    return resolved


def _write_report(payload: dict[str, Any], latest: Path, prefix: str) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORT_DIR / f"{prefix}_{_stamp()}.json"
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    path.write_text(text, encoding="utf-8")
    latest.write_text(text, encoding="utf-8")
    return path


def parse_kv_args(args: list[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    positional: list[str] = []
    for item in args:
        if "=" in item:
            key, value = item.split("=", 1)
            values[key.strip().lstrip("-")] = value.strip()
        elif item.startswith("--"):
            values[item[2:]] = "1"
        else:
            positional.append(item)
    if positional and "code" not in values:
        values["code"] = " ".join(positional)
    return values


def _load_client(values: dict[str, str]) -> tuple[dict[str, Any], str]:
    client_file = (
        values.get("client_file")
        or values.get("client_secrets_file")
        or os.environ.get("YOUTUBE_CLIENT_SECRETS_FILE", "")
        or os.environ.get("YOUTUBE_CLIENT_SECRETS_REF", "")
    )
    client_id = (
        values.get("client_id")
        or os.environ.get("YOUTUBE_OAUTH_CLIENT_ID")
        or os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "")
    )
    client_secret = (
        values.get("client_secret")
        or os.environ.get("YOUTUBE_OAUTH_CLIENT_SECRET")
        or os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", "")
    )
    source = "env_or_args"
    if client_file:
        if client_file.startswith(local_user_secret_store.REF_PREFIX):
            raw = local_user_secret_store.load_secret(client_file)
            if not raw:
                return {}, "local_secret_ref_missing_or_unavailable"
            data = json.loads(raw)
            source = client_file
        else:
            path = _resolve(client_file)
            if not path.exists():
                return {}, f"client_file_not_found:{path}"
            data = json.loads(path.read_text(encoding="utf-8"))
            source = str(path)
        node = data.get("installed") or data.get("web") or data
        client_id = node.get("client_id", client_id)
        client_secret = node.get("client_secret", client_secret)
        redirect_uris = [str(uri) for uri in node.get("redirect_uris", []) if uri]
    else:
        redirect_uris = []
    if not client_id or not client_secret:
        return {}, "oauth_client_id_or_secret_required"
    return {"client_id": client_id, "client_secret": client_secret, "redirect_uris": redirect_uris}, source


def _redirect_uri(values: dict[str, str], client: dict[str, Any]) -> str:
    explicit = (values.get("redirect_uri") or os.environ.get("YOUTUBE_OAUTH_REDIRECT_URI", "")).strip()
    if explicit:
        return explicit
    for uri in client.get("redirect_uris", []):
        if str(uri).startswith(("http://127.0.0.1", "http://localhost")):
            return str(uri)
    return DEFAULT_REDIRECT_URI


def _scope_text(values: dict[str, str]) -> str:
    raw = values.get("scope") or values.get("scopes") or "readonly"
    parts: list[str] = []
    for item in raw.replace(",", " ").split():
        parts.append(YOUTUBE_SCOPES.get(item, item))
    return " ".join(dict.fromkeys(parts))


def build_auth_plan(values: dict[str, str]) -> tuple[dict[str, Any], Path]:
    client, source = _load_client(values)
    redirect_uri = _redirect_uri(values, client) if client else values.get("redirect_uri") or DEFAULT_REDIRECT_URI
    scope = _scope_text(values)
    if not client:
        payload = {
            "schema_version": 1,
            "created_at": _now(),
            "workflow": "youtube_oauth_authorization_url",
            "status": "blocked",
            "reason": source,
            "state_change": False,
            "secret_values_read": False,
            "client_secret_output": "redacted",
            "next_step": "Provide client_file=<client_secret.json> or YOUTUBE_OAUTH_CLIENT_ID/YOUTUBE_OAUTH_CLIENT_SECRET.",
        }
        return payload, _write_report(payload, LATEST_AUTH_PLAN, "youtube_oauth_auth_plan")
    params = {
        "client_id": client["client_id"],
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": scope,
        "access_type": "offline",
        "prompt": values.get("prompt", "consent"),
        "include_granted_scopes": "true",
    }
    auth_url = f"{AUTH_URL}?{urllib.parse.urlencode(params)}"
    payload = {
        "schema_version": 1,
        "created_at": _now(),
        "workflow": "youtube_oauth_authorization_url",
        "status": "ready_for_user_approval",
        "state_change": False,
        "secret_values_read": False,
        "client_source": safe_preview(source, limit=160),
        "client_id_preview": safe_preview(client["client_id"], limit=18),
        "client_secret_output": "redacted",
        "redirect_uri": redirect_uri,
        "client_redirect_uri_source": "explicit_or_client_file_or_default",
        "scope": scope,
        "auth_url": auth_url,
        "approval_boundary": "User must approve in Google OAuth screen and provide only the returned code.",
    }
    return payload, _write_report(payload, LATEST_AUTH_PLAN, "youtube_oauth_auth_plan")


def _post_form(url: str, data: dict[str, str]) -> dict[str, Any]:
    encoded = urllib.parse.urlencode(data).encode("utf-8")
    request = urllib.request.Request(url, data=encoded, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _token_payload_for_file(token: dict[str, Any], client: dict[str, str]) -> dict[str, Any]:
    return {
        "token": token.get("access_token", ""),
        "refresh_token": token.get("refresh_token", ""),
        "token_uri": TOKEN_URL,
        "client_id": client["client_id"],
        "client_secret": client["client_secret"],
        "scopes": token.get("scope", "").split(),
    }


def exchange_code(values: dict[str, str]) -> tuple[dict[str, Any], Path]:
    code = values.get("code", "").strip()
    client, source = _load_client(values)
    redirect_uri = _redirect_uri(values, client) if client else values.get("redirect_uri") or DEFAULT_REDIRECT_URI
    output = _resolve(
        values.get("output")
        or values.get("token_file")
        or os.environ.get("YOUTUBE_OAUTH_TOKEN_FILE", "")
        or DEFAULT_TOKEN_FILE
    )
    if not code:
        payload = {
            "schema_version": 1,
            "created_at": _now(),
            "workflow": "youtube_oauth_token_exchange",
            "status": "blocked",
            "reason": "authorization_code_required",
            "state_change": False,
            "secret_values_read": False,
        }
        return payload, _write_report(payload, LATEST_TOKEN_RESULT, "youtube_oauth_token_result")
    if not client:
        payload = {
            "schema_version": 1,
            "created_at": _now(),
            "workflow": "youtube_oauth_token_exchange",
            "status": "blocked",
            "reason": source,
            "state_change": False,
            "secret_values_read": False,
            "client_secret_output": "redacted",
        }
        return payload, _write_report(payload, LATEST_TOKEN_RESULT, "youtube_oauth_token_result")
    token = _post_form(
        TOKEN_URL,
        {
            "code": code,
            "client_id": client["client_id"],
            "client_secret": client["client_secret"],
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(_token_payload_for_file(token, client), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    payload = {
        "schema_version": 1,
        "created_at": _now(),
        "workflow": "youtube_oauth_token_exchange",
        "status": "ok",
        "state_change": False,
        "secret_values_read": False,
        "client_source": safe_preview(source, limit=160),
        "client_secret_output": "redacted",
        "token_output": "redacted",
        "refresh_token_present": bool(token.get("refresh_token")),
        "expires_in": token.get("expires_in", 0),
        "scope": safe_preview(token.get("scope", ""), limit=500),
        "redirect_uri": safe_preview(redirect_uri, limit=200),
        "token_file": str(output),
    }
    return payload, _write_report(payload, LATEST_TOKEN_RESULT, "youtube_oauth_token_result")


def _truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def handle_server_callback(values: dict[str, str]) -> tuple[dict[str, Any], Path]:
    """Handle the server OAuth callback without returning raw code or tokens."""
    code = values.get("code", "").strip()
    error = values.get("error", "").strip()
    state = values.get("state", "").strip()
    exchange_enabled = _truthy_env("YOUTUBE_OAUTH_CALLBACK_EXCHANGE_ENABLED")
    redirect_uri = values.get("redirect_uri") or os.environ.get("YOUTUBE_OAUTH_REDIRECT_URI") or SERVER_REDIRECT_URI
    client_file = values.get("client_file") or os.environ.get("YOUTUBE_CLIENT_SECRETS_FILE") or SERVER_CLIENT_FILE
    token_file = values.get("token_file") or os.environ.get("YOUTUBE_OAUTH_TOKEN_FILE") or SERVER_TOKEN_FILE
    base = {
        "schema_version": 1,
        "created_at": _now(),
        "workflow": "youtube_oauth_server_callback",
        "state_change": False,
        "code_received": bool(code),
        "code_output": "redacted",
        "token_output": "redacted",
        "client_secret_output": "redacted",
        "state_preview": safe_preview(state, limit=80),
        "redirect_uri": safe_preview(redirect_uri, limit=200),
        "callback_exchange_enabled": exchange_enabled,
        "approval_boundary": "User completed Google OAuth consent before this callback.",
    }
    if error:
        payload = {
            **base,
            "status": "blocked",
            "reason": "google_oauth_error",
            "error": safe_preview(error, limit=120),
            "next_step": "Resolve the Google OAuth error and retry from the server OAuth start command.",
        }
        return payload, _write_report(payload, LATEST_TOKEN_RESULT, "youtube_oauth_server_callback")
    if not code:
        payload = {
            **base,
            "status": "blocked",
            "reason": "authorization_code_missing",
            "next_step": "Retry Google OAuth consent; callback must include code.",
        }
        return payload, _write_report(payload, LATEST_TOKEN_RESULT, "youtube_oauth_server_callback")
    if not exchange_enabled:
        payload = {
            **base,
            "status": "waiting_server_exchange_enabled",
            "reason": "callback_exchange_disabled",
            "next_step": "Set YOUTUBE_OAUTH_CALLBACK_EXCHANGE_ENABLED=true on the server to exchange automatically after final user consent.",
            "token_file": safe_preview(token_file, limit=200),
        }
        return payload, _write_report(payload, LATEST_TOKEN_RESULT, "youtube_oauth_server_callback")
    try:
        exchanged, path = exchange_code(
            {
                "code": code,
                "client_file": client_file,
                "redirect_uri": redirect_uri,
                "output": token_file,
            }
        )
    except Exception as exc:  # pragma: no cover - network/Google dependent  # noqa: BLE001 - OAuth 인가 코드 교환(exchange_code) 실패 시 status=failed, reason=token_exchange_failed 인 실패 payload를 반환하는 fail-closed 경로.
        payload = {
            **base,
            "status": "failed",
            "reason": "token_exchange_failed",
            "error": safe_preview(type(exc).__name__, limit=80),
            "error_summary": safe_preview(str(exc), limit=240),
            "token_file": safe_preview(token_file, limit=200),
        }
        return payload, _write_report(payload, LATEST_TOKEN_RESULT, "youtube_oauth_server_callback")
    payload = {
        **base,
        "status": exchanged.get("status", "unknown"),
        "reason": exchanged.get("reason", ""),
        "state_change": exchanged.get("status") == "ok",
        "token_file": exchanged.get("token_file", safe_preview(token_file, limit=200)),
        "refresh_token_present": bool(exchanged.get("refresh_token_present")),
        "scope": exchanged.get("scope", ""),
        "exchange_report": str(path),
    }
    return payload, _write_report(payload, LATEST_TOKEN_RESULT, "youtube_oauth_server_callback")


def build_server_preapproval(values: dict[str, str] | None = None) -> tuple[dict[str, Any], Path]:
    """Build the server-first Google Console input pack for YouTube captions OAuth."""
    values = values or {}
    work_mode_policy = build_google_work_mode_policy(
        values.get("google_work_mode") or values.get("work_mode"),
        background_approved=str(values.get("background_approved", "")).strip().lower() in {"1", "true", "yes", "on"},
    )
    secret_action_mode = normalize_secret_action_mode(values.get("secret_action_mode"))
    secret_issue_approved = str(values.get("secret_issue_approved", "")).strip().lower() in {"1", "true", "yes", "on"}
    secret_policy = build_secret_action_policy(
        secret_action_mode,
        secret_issue_approved=secret_issue_approved,
    )
    redirect_uri = (
        values.get("redirect_uri") or os.environ.get("YOUTUBE_OAUTH_SERVER_REDIRECT_URI") or SERVER_REDIRECT_URI
    )
    client_file = values.get("client_file") or os.environ.get("YOUTUBE_SERVER_CLIENT_FILE") or SERVER_CLIENT_FILE
    token_file = values.get("token_file") or os.environ.get("YOUTUBE_SERVER_TOKEN_FILE") or SERVER_TOKEN_FILE
    scope = _scope_text({"scope": values.get("scope") or "force-ssl"})
    status = "ready_for_user_console_approval"
    if work_mode_policy["status"] == "blocked" or secret_policy["status"] == "blocked":
        status = "blocked"
    payload = {
        "schema_version": 1,
        "created_at": _now(),
        "workflow": "youtube_caption_server_oauth_preapproval",
        "status": status,
        "state_change": False,
        "google_work_mode_policy": work_mode_policy,
        "google_work_mode": work_mode_policy["mode"],
        "background_approved": work_mode_policy["background_approved"],
        "user_approval_mode": secret_policy["mode"],
        "secret_action_policy": secret_policy,
        "intermediate_user_prompts": False,
        "final_approval_required": "User clicks the final Google Console approval button after the agent completes all non-secret inputs.",
        "server_baseline": True,
        "agent_allowed_steps": [
            "prepare exact non-secret console inputs",
            "open Google Console through the managed CDP browser profile",
            "prepare YouTube Data API v3 enablement screen",
            "fill OAuth consent and OAuth client fields with non-secret values",
            "stop before the final Google Console Create/Save button",
            "after the user clicks the final button, capture the OAuth client JSON into approved secret storage without printing it",
            "prepare server environment variable names and paths",
            "store user-approved local secrets in OS keyring via local-secret references",
            "start the OAuth consent URL and exchange the callback code on the server when enabled",
            "validate generated command structure",
            "write redacted audit/report artifacts",
        ],
        "user_only_steps": [
            "Google account login and MFA/2FA when required",
            "final click on the Google Console Create/Save button",
            "Google OAuth consent approval",
            "final approval for storing client JSON or generated tokens in the approved secret store",
        ],
        "automation_goal": (
            "The agent fills every non-secret YouTube OAuth issuance field and prepares the server token flow; "
            "the user only handles Google login/MFA and the final visible approval button."
        ),
        "google_cloud_inputs": {
            "project": values.get("project") or "haehan-ai",
            "api": "YouTube Data API v3",
            "credential_type": "OAuth client ID",
            "application_type": "Web application",
            "client_name": values.get("client_name") or "haehan-youtube-server-captions",
            "authorized_redirect_uri": redirect_uri,
            "scope": scope,
        },
        "server_secret_placement": {
            "client_json_path": client_file,
            "local_secret_ref": LOCAL_CLIENT_SECRET_REF,
            "token_file_path": token_file,
            "commit_policy": "never commit client JSON, access token, refresh token, or auth code",
        },
        "server_env": {
            "YOUTUBE_CLIENT_SECRETS_FILE": client_file,
            "YOUTUBE_CLIENT_SECRETS_REF": LOCAL_CLIENT_SECRET_REF,
            "YOUTUBE_OAUTH_REDIRECT_URI": redirect_uri,
            "YOUTUBE_OAUTH_TOKEN_FILE": token_file,
            "YOUTUBE_OAUTH_CALLBACK_EXCHANGE_ENABLED": "true",
        },
        "local_secret_commands": [
            "python scripts/auth/local_user_secret_store.py put-file youtube oauth_client_json <downloaded_oauth_client_json>",
            "python scripts/auth/local_user_secret_store.py status youtube oauth_client_json",
        ],
        "post_approval_commands": [
            (
                "python scripts/entry/cdp_cli.py youtube oauth start "
                f"scope=force-ssl client_file={client_file} redirect_uri={redirect_uri}"
            ),
            (
                "python scripts/entry/cdp_cli.py youtube oauth exchange "
                f"code=<returned_code> client_file={client_file} redirect_uri={redirect_uri} output={token_file}"
            ),
            (
                "python scripts/entry/cdp_cli.py youtube research caption-list "
                f"video_id=<owned_or_authorized_video_id> token_file={token_file}"
            ),
        ],
        "approval_boundary": (
            "Final-approval-only mode: the agent prepares values, opens the managed console, fills "
            "non-secret fields, and stops before the final Google Console Create/Save button. "
            "The user handles only Google login/MFA and the final visible approval button."
        ),
    }
    return payload, _write_report(payload, LATEST_AUTH_PLAN, "youtube_caption_server_oauth_preapproval")
