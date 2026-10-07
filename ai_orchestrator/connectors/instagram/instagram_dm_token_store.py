"""Instagram access token 암호화 저장 — 플랫폼별 분기.

- Windows(로컬 데스크톱): OS 자격증명 저장소(keyring, DPAPI). requirements.txt에서
  keyring은 sys_platform == "win32"에만 설치되므로 Linux에서는 import 자체가 실패한다.
- 그 외(Linux 서버 컨테이너 등): keyring이 D-Bus/SecretStorage 백엔드를 요구해
  헤드리스 컨테이너에서 동작하지 않는다 — 대신 TOKEN_ENCRYPTION_KEY(Fernet 키, 환경변수)로
  암호화한 파일(storage/instagram_dm_tokens.enc.json)에 계정별 토큰을 저장한다.

multi-tenant 확장을 위해 계정(instagram_user_id)별로 별도 키/엔트리를 쓴다.
"""

from __future__ import annotations

import contextlib
import json
import os
import sys

from ai_orchestrator.paths.runtime import storage_dir

_USE_KEYRING = sys.platform == "win32"

if _USE_KEYRING:
    import keyring

    _SERVICE_NAME = "haehan-ai-instagram-dm"

    def save_token(instagram_user_id: str, token: str) -> None:
        keyring.set_password(_SERVICE_NAME, instagram_user_id, token)

    def load_token(instagram_user_id: str) -> str | None:
        return keyring.get_password(_SERVICE_NAME, instagram_user_id)

    def delete_token(instagram_user_id: str) -> None:
        with contextlib.suppress(keyring.errors.PasswordDeleteError):
            keyring.delete_password(_SERVICE_NAME, instagram_user_id)

else:
    from cryptography.fernet import Fernet, InvalidToken

    _STORE_PATH = storage_dir() / "instagram_dm_tokens.enc.json"

    class TokenEncryptionKeyMissing(RuntimeError):
        pass

    def _fernet() -> Fernet:
        key = os.environ.get("TOKEN_ENCRYPTION_KEY", "").strip()
        if not key:
            raise TokenEncryptionKeyMissing(
                "TOKEN_ENCRYPTION_KEY 환경변수가 없습니다 — 서버 환경(non-Windows)에서는 "
                "keyring 대신 이 키로 토큰을 파일에 암호화 저장합니다. "
                '발급: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
            )
        return Fernet(key.encode("utf-8"))

    def _load_all() -> dict[str, str]:
        if not _STORE_PATH.exists():
            return {}
        try:
            return json.loads(_STORE_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def _save_all(data: dict[str, str]) -> None:
        _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _STORE_PATH.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        with contextlib.suppress(OSError):
            _STORE_PATH.chmod(0o600)

    def save_token(instagram_user_id: str, token: str) -> None:
        f = _fernet()
        data = _load_all()
        data[instagram_user_id] = f.encrypt(token.encode("utf-8")).decode("utf-8")
        _save_all(data)

    def load_token(instagram_user_id: str) -> str | None:
        f = _fernet()
        data = _load_all()
        enc = data.get(instagram_user_id)
        if not enc:
            return None
        try:
            return f.decrypt(enc.encode("utf-8")).decode("utf-8")
        except InvalidToken:
            return None

    def delete_token(instagram_user_id: str) -> None:
        data = _load_all()
        if instagram_user_id in data:
            del data[instagram_user_id]
            _save_all(data)
