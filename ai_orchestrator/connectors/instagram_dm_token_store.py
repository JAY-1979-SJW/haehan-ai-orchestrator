"""Instagram access token 암호화 저장 — OS 자격증명 저장소(keyring, Windows DPAPI).

multi-tenant 확장을 위해 계정(instagram_user_id)별로 별도 키를 쓴다
(apps/ig-comment-dm-bot/core/token_store.py 는 단일계정 전용이라 여기서는 확장).
instagram_dm_db.encrypted_access_token 컬럼에는 토큰 원문이 아니라
이 모듈이 발급한 참조 키(instagram_user_id)만 저장되고, 실제 토큰 값은 keyring에만 있다.
"""

from __future__ import annotations

import keyring

_SERVICE_NAME = "haehan-ai-instagram-dm"


def save_token(instagram_user_id: str, token: str) -> None:
    keyring.set_password(_SERVICE_NAME, instagram_user_id, token)


def load_token(instagram_user_id: str) -> str | None:
    return keyring.get_password(_SERVICE_NAME, instagram_user_id)


def delete_token(instagram_user_id: str) -> None:
    try:
        keyring.delete_password(_SERVICE_NAME, instagram_user_id)
    except keyring.errors.PasswordDeleteError:
        pass
