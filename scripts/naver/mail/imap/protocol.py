"""네이버 메일 공식 프로토콜(IMAP/SMTP) 점검 — 읽기 전용(로그인과 목록·통계 조회만, 메일을 읽음 처리하거나 보내지 않는다).

기준서·절차서: docs/specs/2026-10-01_naver_mail_imap_smtp.md
- 서버: IMAP imap.naver.com:993(SSL) / SMTP smtp.naver.com:465(SSL). 네이버 메일 환경설정 화면의 "메일 프로그램 환경 설정 안내"가 정본.
- 로그인: 네이버 아이디 + **애플리케이션 비밀번호**(2단계 인증 사용 계정). 비밀번호는 `.env` 의 `NAVER_MAIL_PW_<아이디 대문자>` 에서 읽고 출력·기록하지 않는다.
"""

from __future__ import annotations

import contextlib
import imaplib
import os
import smtplib
import socket
from collections.abc import Callable
from typing import Any

from scripts.common.app_paths import repo_root

ROOT = repo_root()
IMAP_HOST, IMAP_PORT = "imap.naver.com", 993
SMTP_HOST, SMTP_PORT = "smtp.naver.com", 465
TIMEOUT_SEC = 25
AUTH_HINT = (
    "네이버 메일 환경설정 > POP3/IMAP 설정 > IMAP/SMTP 설정에서 '사용함'으로 저장했는지, "
    "애플리케이션 비밀번호가 맞는지 확인하세요"
)


def password_env_name(account: str) -> str:
    return "NAVER_MAIL_PW_" + account.upper()


def load_password(account: str) -> str:
    """`.env`(또는 환경변수)의 앱 비밀번호. 없으면 빈 문자열."""
    name = password_env_name(account)
    value = os.environ.get(name, "")
    if value:
        return value
    try:
        from dotenv import dotenv_values

        return str(dotenv_values(ROOT / ".env").get(name) or "")
    except Exception:  # noqa: BLE001 - .env 를 못 읽으면 비밀번호 없음으로 처리(점검이 no_password 로 안내)
        return ""


def _fail(kind: str, message: str) -> dict[str, Any]:
    return {"ok": False, "error": kind, "message": message}


def _inbox_counts(status_line: str) -> dict[str, int]:
    """`"INBOX" (MESSAGES 155 UNSEEN 76)` 에서 항목별 숫자를 꺼낸다."""
    words = status_line.split("(")[-1].rstrip(") ").split()
    return {words[i]: int(words[i + 1]) for i in range(0, len(words) - 1, 2) if words[i + 1].isdigit()}


def check_imap(account: str, password: str, *, factory: Callable[..., Any] = imaplib.IMAP4_SSL) -> dict[str, Any]:
    """IMAP 로그인 후 폴더 수와 받은편지함 통계(전체·안 읽음)만 읽는다. `STATUS` 는 읽음 표시를 바꾸지 않는다."""
    if not password:
        return _fail("no_password", f".env 에 {password_env_name(account)} 가 없습니다")
    try:
        socket.setdefaulttimeout(TIMEOUT_SEC)
        conn = factory(IMAP_HOST, IMAP_PORT)
    except Exception as e:  # noqa: BLE001 - 접속 실패를 결과로 돌려준다
        return _fail("connect_failed", f"IMAP 서버에 접속하지 못했습니다 ({type(e).__name__})")
    try:
        try:
            conn.login(account, password)
        except imaplib.IMAP4.error:
            return _fail("auth_failed", "IMAP 로그인이 거부되었습니다. " + AUTH_HINT)
        _, folders = conn.list()
        _, status = conn.status("INBOX", "(MESSAGES UNSEEN)")
        counts = _inbox_counts(status[0].decode("utf-8", "replace") if status and status[0] else "")
        return {
            "ok": True,
            "folders": len(folders or []),
            "inbox_total": counts.get("MESSAGES", 0),
            "inbox_unseen": counts.get("UNSEEN", 0),
        }
    finally:
        with contextlib.suppress(Exception):  # 종료 정리 실패는 결과에 영향 없음
            conn.logout()


def check_smtp(account: str, password: str, *, factory: Callable[..., Any] = smtplib.SMTP_SSL) -> dict[str, Any]:
    """SMTP 인증만 확인한다(메일은 보내지 않는다)."""
    if not password:
        return _fail("no_password", f".env 에 {password_env_name(account)} 가 없습니다")
    try:
        socket.setdefaulttimeout(TIMEOUT_SEC)
        conn = factory(SMTP_HOST, SMTP_PORT)
    except Exception as e:  # noqa: BLE001 - 접속 실패를 결과로 돌려준다
        return _fail("connect_failed", f"SMTP 서버에 접속하지 못했습니다 ({type(e).__name__})")
    try:
        try:
            conn.login(account, password)
        except smtplib.SMTPAuthenticationError:
            return _fail("auth_failed", "SMTP 로그인이 거부되었습니다. " + AUTH_HINT)
        return {"ok": True}
    finally:
        with contextlib.suppress(Exception):  # 종료 정리 실패는 결과에 영향 없음
            conn.quit()


def check(
    account: str,
    *,
    imap_factory: Callable[..., Any] = imaplib.IMAP4_SSL,
    smtp_factory: Callable[..., Any] = smtplib.SMTP_SSL,
) -> dict[str, Any]:
    """IMAP·SMTP 점검 결과. 로그인 실패를 반복하면 계정이 잠길 수 있어 IMAP 이 인증 거부면 SMTP 는 시도하지 않는다."""
    password = load_password(account)
    imap = check_imap(account, password, factory=imap_factory)
    if imap.get("error") == "auth_failed":
        smtp = _fail("skipped", "IMAP 인증이 거부되어 SMTP 는 시도하지 않았습니다(계정 잠금 방지)")
    else:
        smtp = check_smtp(account, password, factory=smtp_factory)
    return {"account": account, "ok": bool(imap["ok"] and smtp["ok"]), "imap": imap, "smtp": smtp}


def describe(result: dict[str, Any]) -> str:
    """사람이 읽는 한 줄 요약."""
    imap, smtp = result["imap"], result["smtp"]
    left = (
        f"IMAP: 폴더 {imap['folders']}개, 받은편지함 {imap['inbox_total']}통(안 읽음 {imap['inbox_unseen']})"
        if imap["ok"]
        else "IMAP: " + imap["message"]
    )
    right = "SMTP: 인증 성공" if smtp["ok"] else "SMTP: " + smtp["message"]
    return f"{left} | {right}"
