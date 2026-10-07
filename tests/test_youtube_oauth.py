from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from scripts.youtube import oauth
from scripts.auth import local_user_secret_store


def _test_dir() -> Path:
    path = Path("tmp") / "youtube_oauth_tests" / uuid4().hex
    path.mkdir(parents=True, exist_ok=True)
    return path


def test_auth_plan_blocks_without_client(monkeypatch):
    monkeypatch.delenv("YOUTUBE_OAUTH_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_ID", raising=False)
    monkeypatch.delenv("YOUTUBE_OAUTH_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_SECRET", raising=False)
    monkeypatch.setenv("YOUTUBE_CLIENT_SECRETS_FILE", "/nonexistent/path/client.json")
    monkeypatch.delenv("YOUTUBE_CLIENT_SECRETS_REF", raising=False)

    result, path = oauth.build_auth_plan({})

    assert path.exists()
    assert result["status"] == "blocked"
    assert (result["reason"] == "oauth_client_id_or_secret_required"
            or result["reason"].startswith("client_file_not_found"))
    assert result["client_secret_output"] == "redacted"


def test_auth_plan_uses_client_file_without_secret_output(monkeypatch):
    monkeypatch.delenv("YOUTUBE_OAUTH_REDIRECT_URI", raising=False)
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


def test_auth_plan_prefers_desktop_client_redirect_uri(monkeypatch):
    monkeypatch.delenv("YOUTUBE_OAUTH_REDIRECT_URI", raising=False)
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
    monkeypatch.delenv("YOUTUBE_OAUTH_REDIRECT_URI", raising=False)
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
    result, path = oauth.build_server_preapproval({"google_work_mode": "main"})

    assert path.exists()
    assert result["status"] == "ready_for_user_console_approval"
    assert result["server_baseline"] is True
    assert result["user_approval_mode"] == "final_approval_only"
    assert result["secret_action_policy"]["mode"] == "final_approval_only"
    assert result["secret_action_policy"]["raw_secret_output_allowed"] is False
    assert result["intermediate_user_prompts"] is False
    assert "stop before the final Google Console Create/Save button" in result["agent_allowed_steps"]
    assert "final click on the Google Console Create/Save button" in result["user_only_steps"]
    assert "Google Console Create/Save for OAuth client" not in result["user_only_steps"]
    assert "prepare exact non-secret console inputs" in result["agent_allowed_steps"]
    assert "the user only handles Google login/MFA and the final visible approval button" in result["automation_goal"]
    assert result["google_cloud_inputs"]["application_type"] == "Web application"
    assert result["google_cloud_inputs"]["authorized_redirect_uri"].startswith("https://haehan-ai.kr/")
    assert "youtube.force-ssl" in result["google_cloud_inputs"]["scope"]
    assert result["server_secret_placement"]["commit_policy"].startswith("never commit")
    assert result["server_secret_placement"]["local_secret_ref"] == "local-secret://youtube/oauth_client_json"
    assert result["server_env"]["YOUTUBE_CLIENT_SECRETS_REF"] == "local-secret://youtube/oauth_client_json"
    assert result["server_env"]["YOUTUBE_OAUTH_CALLBACK_EXCHANGE_ENABLED"] == "true"
    assert any("local_user_secret_store.py status youtube oauth_client_json" in item for item in result["local_secret_commands"])


def test_server_preapproval_supports_secret_issue_user_click_mode():
    result, _path = oauth.build_server_preapproval(
        {"google_work_mode": "main", "secret_action_mode": "secret_issue_user_click"}
    )

    assert result["user_approval_mode"] == "secret_issue_user_click"
    assert result["secret_action_policy"]["final_button_user_only"] is True
    assert result["secret_action_policy"]["agent_final_secret_issue_allowed"] is False
    assert result["secret_action_policy"]["raw_secret_output_allowed"] is False


def test_server_preapproval_blocks_agent_secret_click_without_approval():
    result, _path = oauth.build_server_preapproval(
        {"google_work_mode": "main", "secret_action_mode": "secret_issue_agent_click"}
    )

    assert result["user_approval_mode"] == "secret_issue_agent_click"
    assert result["secret_action_policy"]["status"] == "blocked"
    assert result["secret_action_policy"]["blocked_reason"] == "secret_issue_agent_click_requires_explicit_approval"
    assert result["secret_action_policy"]["raw_secret_output_allowed"] is False


def test_server_preapproval_allows_agent_secret_click_with_explicit_approval():
    result, _path = oauth.build_server_preapproval(
        {"google_work_mode": "main", "secret_action_mode": "secret_issue_agent_click", "secret_issue_approved": "true"}
    )

    assert result["secret_action_policy"]["status"] == "ok"
    assert result["secret_action_policy"]["agent_final_secret_issue_allowed"] is True
    assert result["secret_action_policy"]["raw_secret_output_allowed"] is False


def test_youtube_server_console_preapproval_has_managed_browser_plan():
    from scripts.google import managed_console

    result, _path = oauth.build_server_preapproval({"google_work_mode": "main"})
    plan = managed_console.build_youtube_oauth_console_open_plan(google_work_mode="main")

    assert result["user_approval_mode"] == "final_approval_only"
    assert plan["default_browser_allowed"] is False
    assert plan["non_secret_inputs"]["authorized_redirect_uri"] == result["google_cloud_inputs"]["authorized_redirect_uri"]
    assert plan["non_secret_inputs"]["client_name"] == result["google_cloud_inputs"]["client_name"]


def test_auth_plan_uses_local_secret_ref_without_secret_output(monkeypatch):
    ref = "local-secret://youtube/oauth_client_json"
    monkeypatch.setattr(
        local_user_secret_store,
        "load_secret",
        lambda value: json.dumps(
            {
                "web": {
                    "client_id": "client-id.apps.googleusercontent.com",
                    "client_secret": "super-secret",
                    "redirect_uris": ["https://haehan-ai.kr/orchestrator/api/v1/oauth/youtube/callback"],
                }
            }
        )
        if value == ref
        else "",
    )

    result, _path = oauth.build_auth_plan({"client_file": ref, "scope": "force-ssl"})

    assert result["status"] == "ready_for_user_approval"
    assert result["client_source"] == ref
    assert "youtube.force-ssl" in result["scope"]
    assert "super-secret" not in str(result)


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
