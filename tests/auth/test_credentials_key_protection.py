"""자격증명 마스터 키를 OS 자격 증명 관리자(keyring)로 보관·이전하는 동작 검사.

실제 Windows 자격 증명 관리자는 건드리지 않고 메모리 안의 가짜 keyring 을 쓴다.
"""

from __future__ import annotations

import json

import pytest
from cryptography.fernet import Fernet

from scripts.auth import credentials as c


class FakeKeyring:
    def __init__(self, fail_get=False, fail_set=False):
        self.store: dict[tuple[str, str], str] = {}
        self.fail_get, self.fail_set = fail_get, fail_set

    def get_password(self, service, account):
        if self.fail_get:
            raise RuntimeError("locked")
        return self.store.get((service, account))

    def set_password(self, service, account, value):
        if self.fail_set:
            raise RuntimeError("denied")
        self.store[(service, account)] = value


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.delenv("HAEHAN_CRED_KEY_BACKEND", raising=False)  # 기본 = keyring
    monkeypatch.setattr(c, "CRED_FILE", tmp_path / "credentials.json")
    monkeypatch.setattr(c, "KEY_FILE", tmp_path / ".cred.key")
    # 이 PC 의 실제 평문 레거시 파일(data/.env_naver)을 시험이 읽거나 옮기지 못하게 임시 경로로 돌린다
    monkeypatch.setattr(c, "_LEGACY_ENV_FILES", {"naver": tmp_path / ".env_naver_legacy"})
    fake = FakeKeyring()
    monkeypatch.setattr(c, "_keyring_module", lambda: fake)
    return fake, tmp_path


def test_new_key_is_created_in_keyring_not_in_file(env):
    fake, tmp = env
    c.set_cred("naver", id="user1", pw="Dummy-Pw-1")
    assert (c.KEY_SERVICE, c.KEY_ACCOUNT) in fake.store
    assert not (tmp / ".cred.key").exists()
    assert c.get_cred("naver")["pw"] == "Dummy-Pw-1"


def test_legacy_key_file_is_migrated_and_renamed_not_deleted(env):
    fake, tmp = env
    legacy = Fernet.generate_key()
    (tmp / ".cred.key").write_bytes(legacy)
    token = Fernet(legacy).encrypt(b"Old-Dummy-Pw").decode("ascii")
    (tmp / "credentials.json").write_text(json.dumps({"naver": {"id": "u", "pw_enc": token}}), encoding="utf-8")

    assert c.get_cred("naver")["pw"] == "Old-Dummy-Pw"  # 이전 후에도 기존 항목이 풀림
    assert fake.store[(c.KEY_SERVICE, c.KEY_ACCOUNT)] == legacy.decode("ascii")
    assert not (tmp / ".cred.key").exists()
    assert (tmp / ".cred.key.migrated").read_bytes().strip() == legacy  # 삭제하지 않고 보존


def test_migration_keeps_key_file_when_entries_do_not_decrypt(env):
    _, tmp = env
    (tmp / ".cred.key").write_bytes(Fernet.generate_key())
    other = Fernet.generate_key()  # 다른 키로 암호화된 항목이 섞여 있는 비정상 상태
    token = Fernet(other).encrypt(b"x").decode("ascii")
    (tmp / "credentials.json").write_text(json.dumps({"naver": {"id": "u", "pw_enc": token}}), encoding="utf-8")

    c._get_or_create_key()
    assert (tmp / ".cred.key").exists()  # 검증 실패 시 원본 유지
    assert not (tmp / ".cred.key.migrated").exists()


def test_fail_closed_when_keyring_unavailable(monkeypatch, tmp_path):
    monkeypatch.delenv("HAEHAN_CRED_KEY_BACKEND", raising=False)
    monkeypatch.setattr(c, "KEY_FILE", tmp_path / ".cred.key")
    monkeypatch.setattr(c, "_keyring_module", lambda: FakeKeyring(fail_get=True))
    with pytest.raises(c.CredentialKeyError):
        c._get_or_create_key()
    assert not (tmp_path / ".cred.key").exists()  # 조용히 파일로 폴백하지 않는다


def test_fail_closed_when_keyring_cannot_store(monkeypatch, tmp_path):
    monkeypatch.delenv("HAEHAN_CRED_KEY_BACKEND", raising=False)
    monkeypatch.setattr(c, "KEY_FILE", tmp_path / ".cred.key")
    monkeypatch.setattr(c, "_keyring_module", lambda: FakeKeyring(fail_set=True))
    with pytest.raises(c.CredentialKeyError):
        c._get_or_create_key()


def test_file_backend_only_when_explicit(monkeypatch, tmp_path):
    monkeypatch.setenv("HAEHAN_CRED_KEY_BACKEND", "file")
    monkeypatch.setattr(c, "KEY_FILE", tmp_path / ".cred.key")
    monkeypatch.setattr(c, "_keyring_module", lambda: pytest.fail("file 백엔드에서는 keyring 을 쓰지 않는다"))
    key = c._get_or_create_key()
    assert (tmp_path / ".cred.key").read_bytes().strip() == key


def test_error_messages_never_contain_secrets(env):
    fake, _ = env
    fake.fail_get = True
    with pytest.raises(c.CredentialKeyError) as exc:
        c._get_or_create_key()
    assert "Dummy" not in str(exc.value) and "locked" not in str(exc.value)


def test_naver_save_credentials_goes_to_encrypted_store_not_plaintext(env, monkeypatch, tmp_path):
    from scripts.naver.common import auth

    monkeypatch.setattr(auth, "ENV_FILE", tmp_path / ".env_naver")
    auth.save_credentials("naver_user", "Dummy-Pw-2")
    assert not (tmp_path / ".env_naver").exists()  # 평문 파일을 만들지 않는다
    raw = (tmp_path / "credentials.json").read_text(encoding="utf-8")
    assert "Dummy-Pw-2" not in raw  # 저장된 파일에 평문 비밀번호가 없다
    assert c.get_cred("naver:naver_user")["pw"] == "Dummy-Pw-2"
    assert c.get_cred("naver")["id"] == "naver_user"  # 기본 계정이 비어 있으면 함께 채운다
