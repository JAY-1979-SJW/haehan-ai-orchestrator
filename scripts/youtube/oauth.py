"""User-approved YouTube OAuth token helper.

This module only implements the official OAuth installed-app flow. It never
prints client secrets, access tokens, or refresh tokens.
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from security_utils import safe_preview


ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = ROOT / "data" / "youtube_oauth_reports"
TOKEN_DIR = ROOT / "data" / "secrets"
LATEST_AUTH_PLAN = ROOT / "data" / "youtube_oauth_auth_plan_latest.json"
LATEST_TOKEN_RESULT = ROOT / "data" / "youtube_oauth_token_result_latest.json"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
DEFAULT_REDIRECT_URI = "http://127.0.0.1:8765/oauth2callback"
DEFAULT_TOKEN_FILE = TOKEN_DIR / "youtube_oauth_authorized_user.json"
YOUTUBE_SCOPES = {
    "readonly": "https://www.googleapis.com/auth/youtube.readonly",
    "upload": "https://www.googleapis.com/auth/youtube.upload",
    "force-ssl": "https://www.googleapis.com/auth/youtube.force-ssl",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


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
    client_file = values.get("client_file") or values.get("client_secrets_file") or os.environ.get("YOUTUBE_CLIENT_SECRETS_FILE", "")
    client_id = values.get("client_id") or os.environ.get("YOUTUBE_OAUTH_CLIENT_ID") or os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "")
    client_secret = (
        values.get("client_secret")
        or os.environ.get("YOUTUBE_OAUTH_CLIENT_SECRET")
        or os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", "")
    )
    source = "env_or_args"
    if client_file:
        path = _resolve(client_file)
        if not path.exists():
            return {}, f"client_file_not_found:{path}"
        data = json.loads(path.read_text(encoding="utf-8"))
        node = data.get("installed") or data.get("web") or data
        client_id = node.get("client_id", client_id)
        client_secret = node.get("client_secret", client_secret)
        redirect_uris = [str(uri) for uri in node.get("redirect_uris", []) if uri]
        source = str(path)
    else:
        redirect_uris = []
    if not client_id or not client_secret:
        return {}, "oauth_client_id_or_secret_required"
    return {"client_id": client_id, "client_secret": client_secret, "redirect_uris": redirect_uris}, source


def _redirect_uri(values: dict[str, str], client: dict[str, Any]) -> str:
    explicit = values.get("redirect_uri", "").strip()
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
    output = _resolve(values.get("output") or values.get("token_file") or DEFAULT_TOKEN_FILE)
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
    output.write_text(json.dumps(_token_payload_for_file(token, client), ensure_ascii=False, indent=2), encoding="utf-8")
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
