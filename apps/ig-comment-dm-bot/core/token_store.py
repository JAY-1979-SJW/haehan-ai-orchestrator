"""Instagram 액세스 토큰을 OS 자격증명 저장소(keyring)에 암호화 저장/조회.

Windows 는 DPAPI 백엔드를 자동 사용하므로 파일로 토큰이 노출되지 않는다.
"""

from __future__ import annotations

from contextlib import suppress

import keyring

_SERVICE_NAME = "ig-comment-dm-bot"
_USERNAME = "access_token"


def save_token(token: str) -> None:
    keyring.set_password(_SERVICE_NAME, _USERNAME, token)


def load_token() -> str | None:
    return keyring.get_password(_SERVICE_NAME, _USERNAME)


def delete_token() -> None:
    with suppress(keyring.errors.PasswordDeleteError):
        keyring.delete_password(_SERVICE_NAME, _USERNAME)
