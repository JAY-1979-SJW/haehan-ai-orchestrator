from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from scripts.youtube import oauth


def _test_dir() -> Path:
    path = Path("tmp") / "youtube_oauth_tests" / uuid4().hex
    path.mkdir(parents=True, exist_ok=True)
    return path


def test_auth_plan_blocks_without_client(monkeypatch):
    monkeypatch.delenv("YOUTUBE_OAUTH_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_ID", raising=False)
    monkeypatch.delenv("YOUTUBE_OAUTH_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("YOUTUBE_CLIENT_SECRETS_FILE", raising=False)

    result, path = oauth.build_auth_plan({})

    assert path.exists()
    assert result["status"] == "blocked"
    assert result["reason"] == "oauth_client_id_or_secret_required"
    assert result["client_secret_output"] == "redacted"


def test_auth_plan_uses_client_file_without_secret_output():
    tmp_path = _test_dir()
    client_file = tmp_path / "client_secret.json"
    client_file.write_text(
        json.dumps({"installed": {"client_id": "client-id.apps.googleusercontent.com", "client_secret": "super-secret"}}),
        encoding="utf-8",
    )

    result, _path = oauth.build_auth_plan({"client_file": str(client_file), "scope": "readonly upload"})

    assert result["status"] == "ready_for_user_approval"
    assert "https://accounts.google.com/o/oauth2/v2/auth?" in result["auth_url"]
    assert "127.0.0.1%3A8765%2Foauth2callback" in result["auth_url"]
    assert "youtube.readonly" in result["auth_url"]
    assert "youtube.upload" in result["auth_url"]
    assert "super-secret" not in str(result)


def test_auth_plan_prefers_desktop_client_redirect_uri():
    tmp_path = _test_dir()
    client_file = tmp_path / "client_secret.json"
    client_file.write_text(
        json.dumps(
            {
                "installed": {
                    "client_id": "client-id.apps.googleusercontent.com",
                    "client_secret": "super-secret",
                    "redirect_uris": ["http://localhost"],
                }
            }
        ),
        encoding="utf-8",
    )

    result, _path = oauth.build_auth_plan({"client_file": str(client_file), "scope": "readonly"})

    assert result["status"] == "ready_for_user_approval"
    assert result["redirect_uri"] == "http://localhost"
    assert "redirect_uri=http%3A%2F%2Flocalhost" in result["auth_url"]


def test_exchange_code_writes_authorized_user_token(monkeypatch):
    tmp_path = _test_dir()
    client_file = tmp_path / "client_secret.json"
    token_file = tmp_path / "token.json"
    client_file.write_text(
        json.dumps(
            {
                "installed": {
                    "client_id": "client-id.apps.googleusercontent.com",
                    "client_secret": "super-secret",
                    "redirect_uris": ["http://localhost"],
                }
            }
        ),
        encoding="utf-8",
    )

    def fake_post_form(url, data):
        assert url == oauth.TOKEN_URL
        assert data["grant_type"] == "authorization_code"
        assert data["redirect_uri"] == "http://localhost"
        return {
            "access_token": "access-secret",
            "refresh_token": "refresh-secret",
            "expires_in": 3600,
            "scope": oauth.YOUTUBE_SCOPES["readonly"],
        }

    monkeypatch.setattr(oauth, "_post_form", fake_post_form)

    result, _path = oauth.exchange_code(
        {"code": "user-code", "client_file": str(client_file), "output": str(token_file)}
    )

    assert result["status"] == "ok"
    assert result["refresh_token_present"] is True
    assert result["token_output"] == "redacted"
    assert "access-secret" not in str(result)
    saved = json.loads(token_file.read_text(encoding="utf-8"))
    assert saved["token"] == "access-secret"
    assert saved["refresh_token"] == "refresh-secret"
    assert saved["client_secret"] == "super-secret"


def test_exchange_blocks_without_code():
    tmp_path = _test_dir()
    client_file = tmp_path / "client_secret.json"
    client_file.write_text(
        json.dumps({"installed": {"client_id": "client-id.apps.googleusercontent.com", "client_secret": "super-secret"}}),
        encoding="utf-8",
    )

    result, _path = oauth.exchange_code({"client_file": str(client_file)})

    assert result["status"] == "blocked"
    assert result["reason"] == "authorization_code_required"


def test_auth_plan_uses_server_redirect_env(monkeypatch):
    tmp_path = _test_dir()
    client_file = tmp_path / "client_secret.json"
    client_file.write_text(
        json.dumps({"web": {"client_id": "client-id.apps.googleusercontent.com", "client_secret": "super-secret"}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("YOUTUBE_OAUTH_REDIRECT_URI", "https://haehan-ai.kr/orchestrator/api/v1/oauth/youtube/callback")

    result, _path = oauth.build_auth_plan({"client_file": str(client_file), "scope": "force-ssl"})

    assert result["status"] == "ready_for_user_approval"
    assert result["redirect_uri"] == "https://haehan-ai.kr/orchestrator/api/v1/oauth/youtube/callback"
    assert "youtube.force-ssl" in result["scope"]
    assert "super-secret" not in str(result)


def test_exchange_uses_server_token_file_env(monkeypatch):
    tmp_path = _test_dir()
    client_file = tmp_path / "client_secret.json"
    token_file = tmp_path / "server-token.json"
    client_file.write_text(
        json.dumps(
            {
                "web": {
                    "client_id": "client-id.apps.googleusercontent.com",
                    "client_secret": "super-secret",
                    "redirect_uris": ["https://haehan-ai.kr/orchestrator/api/v1/oauth/youtube/callback"],
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("YOUTUBE_OAUTH_TOKEN_FILE", str(token_file))

    def fake_post_form(url, data):
        return {
            "access_token": "access-secret",
            "refresh_token": "refresh-secret",
            "expires_in": 3600,
            "scope": oauth.YOUTUBE_SCOPES["force-ssl"],
        }

    monkeypatch.setattr(oauth, "_post_form", fake_post_form)

    result, _path = oauth.exchange_code({"code": "user-code", "client_file": str(client_file)})

    assert result["status"] == "ok"
    assert result["token_file"] == str(token_file.resolve())
    assert token_file.exists()


def test_server_preapproval_defines_final_console_values():
    result, path = oauth.build_server_preapproval({})

    assert path.exists()
    assert result["status"] == "ready_for_user_console_approval"
    assert result["server_baseline"] is True
    assert result["user_approval_mode"] == "final_approval_only"
    assert result["intermediate_user_prompts"] is False
    assert "Google Console Create/Save for OAuth client" in result["user_only_steps"]
    assert "prepare exact non-secret console inputs" in result["agent_allowed_steps"]
    assert result["google_cloud_inputs"]["application_type"] == "Web application"
    assert result["google_cloud_inputs"]["authorized_redirect_uri"].startswith("https://haehan-ai.kr/")
    assert "youtube.force-ssl" in result["google_cloud_inputs"]["scope"]
    assert result["server_secret_placement"]["commit_policy"].startswith("never commit")
    assert result["server_env"]["YOUTUBE_OAUTH_CALLBACK_EXCHANGE_ENABLED"] == "true"


def test_server_callback_waits_when_exchange_disabled(monkeypatch):
    monkeypatch.delenv("YOUTUBE_OAUTH_CALLBACK_EXCHANGE_ENABLED", raising=False)

    result, path = oauth.handle_server_callback({"code": "secret-code", "state": "state-1"})

    assert path.exists()
    assert result["status"] == "waiting_server_exchange_enabled"
    assert result["code_received"] is True
    assert result["code_output"] == "redacted"
    assert "secret-code" not in str(result)


def test_server_callback_reports_google_error_without_secret():
    result, _path = oauth.handle_server_callback({"error": "access_denied", "state": "state-1"})

    assert result["status"] == "blocked"
    assert result["reason"] == "google_oauth_error"
    assert result["code_output"] == "redacted"


def test_server_callback_exchanges_when_enabled(monkeypatch):
    work_dir = _test_dir()
    client_file = work_dir / "client_secret.json"
    token_file = work_dir / "server-token.json"
    client_file.write_text(
        json.dumps(
            {
                "web": {
                    "client_id": "client-id.apps.googleusercontent.com",
                    "client_secret": "super-secret",
                    "redirect_uris": ["https://haehan-ai.kr/orchestrator/api/v1/oauth/youtube/callback"],
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("YOUTUBE_OAUTH_CALLBACK_EXCHANGE_ENABLED", "true")

    def fake_post_form(url, data):
        assert data["code"] == "secret-code"
        return {
            "access_token": "access-secret",
            "refresh_token": "refresh-secret",
            "expires_in": 3600,
            "scope": oauth.YOUTUBE_SCOPES["force-ssl"],
        }

    monkeypatch.setattr(oauth, "_post_form", fake_post_form)

    result, _path = oauth.handle_server_callback(
        {
            "code": "secret-code",
            "client_file": str(client_file),
            "token_file": str(token_file),
            "redirect_uri": "https://haehan-ai.kr/orchestrator/api/v1/oauth/youtube/callback",
        }
    )

    assert result["status"] == "ok"
    assert result["state_change"] is True
    assert result["refresh_token_present"] is True
    assert token_file.exists()
    assert "secret-code" not in str(result)
    assert "access-secret" not in str(result)
