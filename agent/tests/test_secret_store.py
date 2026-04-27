"""로컬 시크릿 스토어 테스트.

필수 검증:
1) 저장 후 조회 가능
2) list_secrets 결과에 평문 password 미노출
3) 감사 로그에 password/민감 키 미기록
4) 삭제 동작 확인
5) 없는 site_key 조회 시 안전한 실패 (None 반환)
6) 동일 site_key 덮어쓰기 정책 (created_at 보존, updated_at 갱신)
7) 암호화된 파일이 평문 password 를 포함하지 않음
8) dict/json 변환 시 password 미노출 (SiteSecret.to_public_dict, repr)
+) cryptography 미설치 시 가짜 암호화로 우회되지 않고 명시적으로 실패
"""
from __future__ import annotations

import json
import os
import sys
import time

import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)

PW = "TOPSECRETPW-0xF0F0-UNIQUE"
PW_ALT = "ALTPW-12345-QQQQQ-UNIQUE"
USER = "alice@example.com"
NOTE_MARKER = "note memo with spaces"  # 공백 포함 → Fernet base64 출력에 못 들어감


@pytest.fixture(autouse=True)
def _isolated_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_SECRETS_DIR", str(tmp_path))
    yield


def _read_log(tmp_path) -> list:
    p = tmp_path / "secret_actions.jsonl"
    if not p.exists():
        return []
    return [
        json.loads(ln)
        for ln in p.read_text(encoding="utf-8").strip().splitlines()
    ]


def _raw_log(tmp_path) -> str:
    p = tmp_path / "secret_actions.jsonl"
    return p.read_text(encoding="utf-8") if p.exists() else ""


# ══════════════════════════════════════════════════════════════════════
# 1) 저장 후 조회 가능
# ══════════════════════════════════════════════════════════════════════
def test_save_then_get_returns_masked_record():
    from agent.secrets import store

    pub = store.save_secret("naver", USER, PW, note="memo")
    assert pub["site_key"] == "naver"
    assert pub["note"] == "memo"
    assert pub["username_masked"] != USER
    assert "password" not in pub
    assert "username" not in pub
    assert pub["created_at"] and pub["updated_at"]

    got = store.get_secret("naver")
    assert got is not None
    assert got["site_key"] == "naver"
    assert got["note"] == "memo"
    assert "password" not in got
    assert "username" not in got


# ══════════════════════════════════════════════════════════════════════
# 2) list_secrets 평문 password 미노출
# ══════════════════════════════════════════════════════════════════════
def test_list_secrets_never_exposes_password():
    from agent.secrets import store

    store.save_secret("naver", USER, PW)
    store.save_secret("google", "bob@test.io", PW_ALT)

    items = store.list_secrets()
    assert {i["site_key"] for i in items} == {"naver", "google"}
    for item in items:
        assert "password" not in item
        assert "username" not in item
        assert "username_masked" in item

    raw = json.dumps(items, ensure_ascii=False)
    assert PW not in raw
    assert PW_ALT not in raw
    assert USER not in raw


# ══════════════════════════════════════════════════════════════════════
# 3) 감사 로그에 민감정보 미기록
# ══════════════════════════════════════════════════════════════════════
def test_audit_log_does_not_record_sensitive_values(tmp_path):
    from agent.secrets import store

    store.save_secret("naver", USER, PW, note=NOTE_MARKER)
    store.get_secret("naver")
    store.list_secrets()
    store.delete_secret("naver")

    raw = _raw_log(tmp_path)
    assert PW not in raw
    assert USER not in raw
    assert NOTE_MARKER not in raw
    # 민감 키 이름 자체도 로그에 들어가면 안 된다
    for banned in ("password", "token", "cookie", "authorization", "session"):
        assert banned not in raw.lower(), f"banned key '{banned}' leaked to log"


def test_audit_log_records_action_and_site_key(tmp_path):
    from agent.secrets import store

    store.save_secret("naver", USER, PW)
    store.get_secret("naver")
    store.delete_secret("naver")

    entries = _read_log(tmp_path)
    actions = [(e["action"], e["site_key"], e["ok"]) for e in entries]
    assert ("save", "naver", True) in actions
    assert ("get", "naver", True) in actions
    assert ("delete", "naver", True) in actions


# ══════════════════════════════════════════════════════════════════════
# 4) 삭제 동작
# ══════════════════════════════════════════════════════════════════════
def test_delete_removes_record_and_is_idempotent_false():
    from agent.secrets import store

    store.save_secret("naver", USER, PW)
    assert store.get_secret("naver") is not None
    assert store.delete_secret("naver") is True
    assert store.get_secret("naver") is None
    # 이미 제거된 site_key 삭제는 False
    assert store.delete_secret("naver") is False


# ══════════════════════════════════════════════════════════════════════
# 5) 없는 site_key 안전한 실패
# ══════════════════════════════════════════════════════════════════════
def test_get_missing_site_returns_none():
    from agent.secrets import store

    assert store.get_secret("no_such_site") is None


def test_invalid_site_key_raises_value_error():
    from agent.secrets import store

    for bad in ("", "   ", None, 123):
        with pytest.raises((ValueError, TypeError)):
            store.get_secret(bad)  # type: ignore[arg-type]


def test_empty_password_is_rejected():
    from agent.secrets import store

    with pytest.raises(ValueError):
        store.save_secret("naver", USER, "")


# ══════════════════════════════════════════════════════════════════════
# 6) 동일 site_key 덮어쓰기 정책
# ══════════════════════════════════════════════════════════════════════
def test_overwrite_preserves_created_at_and_updates_updated_at():
    from agent.secrets import store

    first = store.save_secret("naver", USER, PW)
    time.sleep(0.01)
    second = store.save_secret("naver", "bob@test.io", PW_ALT, note="changed")

    assert first["created_at"] == second["created_at"], \
        "created_at must be preserved on overwrite"
    assert second["updated_at"] >= first["updated_at"]

    got = store.get_secret("naver")
    assert got["note"] == "changed"
    # 기존 비밀번호 평문이 스토어 내 어디에도 남지 않아야 한다 (새 비번으로 교체됨)
    # 암호화된 파일 바이트 수준 확인은 아래 7번 테스트에서 다룸


# ══════════════════════════════════════════════════════════════════════
# 7) 암호화된 파일 평문 미포함
# ══════════════════════════════════════════════════════════════════════
def test_encrypted_file_does_not_contain_plaintext(tmp_path):
    from agent.secrets import store

    store.save_secret("naver", USER, PW, note=NOTE_MARKER)

    enc_path = tmp_path / "secrets.json.enc"
    assert enc_path.exists()
    blob = enc_path.read_bytes()

    # password / username(email) / note 마커 모두 평문으로 보이면 안 된다
    assert PW.encode() not in blob
    assert USER.encode() not in blob  # '@', '.' 은 Fernet base64 알파벳 밖
    assert NOTE_MARKER.encode() not in blob  # 공백 포함 → base64 출력에 존재 불가
    # JSON 필드 이름도 평문으로 보이면 안 된다
    assert b"\"password\"" not in blob
    assert b"\"username\"" not in blob


def test_key_file_is_separate_and_present(tmp_path):
    from agent.secrets import store

    store.save_secret("naver", USER, PW)
    assert (tmp_path / "secrets.key").exists()
    assert (tmp_path / "secrets.json.enc").exists()


# ══════════════════════════════════════════════════════════════════════
# 8) dict/json 변환 시 password 미노출
# ══════════════════════════════════════════════════════════════════════
def test_site_secret_to_public_dict_hides_password():
    from agent.secrets.models import SiteSecret

    s = SiteSecret(
        site_key="naver",
        username=USER,
        password=PW,
        note=None,
        created_at="t0",
        updated_at="t1",
    )
    pub = s.to_public_dict()
    assert "password" not in pub
    assert "username" not in pub
    assert pub["username_masked"] != USER
    # json 직렬화에도 비밀번호가 들어가면 안 된다
    assert PW not in json.dumps(pub, ensure_ascii=False)


def test_site_secret_repr_hides_password():
    from agent.secrets.models import SiteSecret

    s = SiteSecret(
        site_key="naver", username=USER, password=PW,
        note=None, created_at="t0", updated_at="t1",
    )
    r = repr(s)
    assert PW not in r
    assert USER not in r  # username 도 마스킹되어 있어야 함


# ══════════════════════════════════════════════════════════════════════
# +) cryptography 미설치 시 가짜 암호화로 넘어가지 않고 명시적으로 실패
# ══════════════════════════════════════════════════════════════════════
def test_encryption_unavailable_fails_loud(monkeypatch):
    from agent.secrets import crypto, store

    monkeypatch.setattr(crypto, "_AVAILABLE", False)
    with pytest.raises(crypto.EncryptionNotAvailable):
        store.save_secret("naver", USER, PW)


def test_is_available_reflects_runtime():
    from agent.secrets import crypto

    # 실제 러닝 환경에서는 cryptography 가 있어야 PASS 가능
    assert crypto.is_available() is True


# ══════════════════════════════════════════════════════════════════════
# 라운드트립: 내부 전용 경로로만 평문 비밀번호 복원 가능
# ══════════════════════════════════════════════════════════════════════
def test_internal_plain_getter_restores_password_but_is_not_public():
    from agent.secrets import store

    store.save_secret("naver", USER, PW)
    sec = store._get_secret_plain_internal("naver")
    assert sec is not None
    assert sec.password == PW
    assert sec.username == USER
    # 공개 API 는 절대 평문 비밀번호를 반환하지 않는다
    assert "password" not in store.get_secret("naver")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
