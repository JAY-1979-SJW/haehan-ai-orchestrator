"""네이버 메일 순차 대량 발송용 SMTP 연결 재사용 어댑터.

기준서: docs/specs/2026-10-02_mail_bulk_sequential.md §3
수신자마다 로그인하면 로그인 반복이 차단 사유가 될 수 있어 **연결 1개를 열어 여러 통을 차례로 보낸다.**
발송 직전에 NOOP 으로 연결을 확인하고 끊겼으면 다시 접속한다(아직 메일이 나가기 전이라 중복 위험이 없다).
`send_message` 도중 끊기면 서버가 받았는지 알 수 없으므로 `send_unknown` 으로 알리고 **재시도하지 않는다.**
결과에 비밀번호·본문을 넣지 않는다.
"""

from __future__ import annotations

import contextlib
import smtplib
import socket
from collections.abc import Callable
from typing import Any

from scripts.naver.mail.imap import sender
from scripts.naver.mail.imap.protocol import (
    AUTH_HINT,
    SMTP_HOST,
    SMTP_PORT,
    TIMEOUT_SEC,
    load_password,
    password_env_name,
)

_MSG_LIMIT = 200


def _smtp_text(error: BaseException) -> str:
    raw = getattr(error, "smtp_error", b"")
    text = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw or "")
    return (text or type(error).__name__)[:_MSG_LIMIT]


class BulkSmtp:
    """로그인한 SMTP 연결 하나를 빌려 쓰는 컨텍스트 매니저. `send(draft)` 를 여러 번 부른다."""

    def __init__(
        self, account: str, *, password: str | None = None, factory: Callable[..., Any] = smtplib.SMTP_SSL
    ) -> None:
        self.account = account
        self._password = load_password(account) if password is None else password
        self._factory = factory
        self._conn: Any = None

    def __enter__(self) -> BulkSmtp:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def close(self) -> None:
        if self._conn is not None:
            with contextlib.suppress(Exception):  # 종료 정리 실패는 결과에 영향 없음
                self._conn.quit()
            self._conn = None

    def _open(self) -> dict[str, Any] | None:
        """연결+로그인. 실패하면 결과 dict, 성공이면 None."""
        if not self._password:
            return {
                "ok": False,
                "error": "no_password",
                "code": None,
                "message": f".env 에 {password_env_name(self.account)} 가 없습니다",
            }
        try:
            socket.setdefaulttimeout(TIMEOUT_SEC)
            conn = self._factory(SMTP_HOST, SMTP_PORT)
        except Exception as e:  # noqa: BLE001 - 접속 실패를 결과로 돌려준다
            return {
                "ok": False,
                "error": "connect_failed",
                "code": None,
                "message": f"SMTP 서버에 접속하지 못했습니다 ({type(e).__name__})",
            }
        try:
            conn.login(self.account, self._password)
        except smtplib.SMTPAuthenticationError as e:
            with contextlib.suppress(Exception):
                conn.quit()
            return {
                "ok": False,
                "error": "auth_failed",
                "code": e.smtp_code,
                "message": "SMTP 로그인이 거부되었습니다. " + AUTH_HINT,
            }
        except (smtplib.SMTPException, OSError) as e:
            with contextlib.suppress(Exception):
                conn.quit()
            return {
                "ok": False,
                "error": "connect_failed",
                "code": None,
                "message": f"SMTP 로그인 중 오류 ({type(e).__name__})",
            }
        self._conn = conn
        return None

    def _ensure(self) -> dict[str, Any] | None:
        """살아 있는 연결을 보장한다. 보낼 메일은 아직 나가지 않았으므로 재접속해도 안전하다."""
        if self._conn is not None:
            try:
                code, _ = self._conn.noop()
                if code == 250:
                    return None
            except (smtplib.SMTPException, OSError):
                pass
            self.close()
        return self._open()

    def send(self, draft: sender.Draft) -> dict[str, Any]:
        """메일 1통을 보낸다. ok=True 면 서버가 받아 갔다. 결과에 `error`·`code`·`message` 로 분류 근거를 준다."""
        failed = self._ensure()
        if failed is not None:
            return failed
        msg = sender.build_full_message(draft)
        try:
            refused = self._conn.send_message(msg)
        except smtplib.SMTPRecipientsRefused as e:
            code = next(iter(e.recipients.values()), (None, b""))[0]
            return {"ok": False, "error": "send_failed", "code": code, "message": "수신자가 거부되었습니다"}
        except smtplib.SMTPResponseException as e:
            return {"ok": False, "error": "send_failed", "code": e.smtp_code, "message": _smtp_text(e)}
        except (smtplib.SMTPException, OSError) as e:
            self.close()  # 연결 상태를 모르므로 다음 건은 새로 접속한다
            return {
                "ok": False,
                "error": "send_unknown",
                "code": None,
                "message": f"전송 결과를 확인하지 못했습니다 ({type(e).__name__})",
            }
        return {"ok": True, "refused": sorted(refused), "code": 250, "message": ""}
