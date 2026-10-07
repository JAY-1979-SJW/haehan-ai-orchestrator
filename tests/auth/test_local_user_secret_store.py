from __future__ import annotations

from scripts.auth import local_user_secret_store as store


class FakeKeyring:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}

    def set_password(self, service: str, name: str, value: str) -> None:
        self.values[(service, name)] = value

    def get_password(self, service: str, name: str) -> str:
        return self.values.get((service, name), "")

    def delete_password(self, service: str, name: str) -> None:
        self.values.pop((service, name), None)


def test_secret_ref_parse_and_make() -> None:
    ref = store.make_ref("youtube", "oauth_client_json")

    parsed = store.parse_ref(ref)

    assert ref == "local-secret://youtube/oauth_client_json"
    assert parsed.service == "haehan-ai-orchestrator:youtube"


def test_store_blocks_without_keyring(monkeypatch) -> None:
    monkeypatch.setattr(store, "_try_keyring", lambda: None)

    result = store.store_secret("local-secret://youtube/oauth_client_json", "{}")

    assert result["ok"] is False
    assert result["reason"] == "keyring_unavailable"
    assert "{}" not in str(result)


def test_store_status_load_delete_with_keyring(monkeypatch) -> None:
    fake = FakeKeyring()
    monkeypatch.setattr(store, "_try_keyring", lambda: fake)
    ref = "local-secret://youtube/oauth_client_json"

    saved = store.store_secret(ref, '{"web": {"client_id": "id", "client_secret": "secret"}}')

    assert saved["status"] == "stored"
    assert saved["secret_output"] == "redacted"
    assert "client_secret" not in str(saved)
    assert store.secret_status(ref)["status"] == "present"
    assert store.load_secret(ref).startswith('{"web"')
    assert store.delete_secret(ref)["status"] == "deleted"
    assert store.secret_status(ref)["status"] == "missing"
