"""
하이웍스 메일 읽기 전용 수집 모듈
방식: POP3 평문 (포트 110) — 하이웍스는 IMAP 미지원, POP3만 제공
      SSL/995는 서버 인증서 문제로 연결 불가 확인(2026-04-22)
서버: mailapp.hiworks.co.kr:110
읽기 전용: DELE 명령 미사용, 메일 상태 변경 없음
"""
import email
import email.header
import os
import poplib
import re
from datetime import datetime, timezone
from email.utils import parseaddr, parsedate_to_datetime
from typing import Optional

from logger import get_logger

log = get_logger("hiworks_mail_reader")

HIWORKS_POP3_HOST = "mailapp.hiworks.co.kr"
HIWORKS_POP3_PORT = 110


def _get_credentials() -> tuple[str, str]:
    account = os.environ.get("HIWORKS_MAIL_ACCOUNT", "")
    password = os.environ.get("HIWORKS_MAIL_PASSWORD", "")
    return account, password


def _decode_header_value(raw) -> str:
    if raw is None:
        return ""
    parts = email.header.decode_header(raw)
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            try:
                decoded.append(part.decode(charset or "utf-8", errors="replace"))
            except (LookupError, UnicodeDecodeError):
                decoded.append(part.decode("utf-8", errors="replace"))
        else:
            decoded.append(part)
    return "".join(decoded).strip()


def _extract_body(msg: email.message.Message) -> str:
    """text/plain 우선, 없으면 text/html 태그 제거, 그 외 빈 문자열."""
    plain_parts: list[str] = []
    html_parts: list[str] = []

    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            cd = str(part.get("Content-Disposition", ""))
            if "attachment" in cd:
                continue
            payload = part.get_payload(decode=True)
            if not payload:
                continue
            charset = part.get_content_charset() or "utf-8"
            text = payload.decode(charset, errors="replace")
            if ct == "text/plain":
                plain_parts.append(text)
            elif ct == "text/html":
                html_parts.append(text)
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            text = payload.decode(charset, errors="replace")
            if msg.get_content_type() == "text/html":
                html_parts.append(text)
            else:
                plain_parts.append(text)

    if plain_parts:
        return "\n".join(plain_parts).strip()
    if html_parts:
        raw_html = "\n".join(html_parts)
        text = re.sub(r"<[^>]+>", " ", raw_html)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()
    return ""


def _parse_received_at(msg: email.message.Message) -> str:
    date_str = msg.get("Date", "")
    if date_str:
        try:
            dt = parsedate_to_datetime(date_str)
            return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        except Exception:
            pass
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def _build_external_id(msg: email.message.Message, uidl: str) -> str:
    """Message-ID 우선, 없으면 POP3 UIDL 기반."""
    msg_id = msg.get("Message-ID", "").strip()
    if msg_id:
        return msg_id
    return f"uidl:{uidl}"


def fetch_recent_mails(limit: int = 20) -> list[dict]:
    """
    하이웍스 POP3에서 최근 limit건 읽기.
    읽기 전용 — DELE 미사용, 메일 상태 변경 없음.
    연결 실패 시 빈 목록 반환 + 경고 로그.
    """
    account, password = _get_credentials()
    if not account or not password:
        log.warning("HIWORKS_MAIL_ACCOUNT 또는 HIWORKS_MAIL_PASSWORD 미설정 — 수집 건너뜀")
        return []

    results: list[dict] = []

    pop = None
    try:
        pop = poplib.POP3(HIWORKS_POP3_HOST, HIWORKS_POP3_PORT)
        pop.user(account)
        pop.pass_(password)

        num_messages = len(pop.list()[1])
        if num_messages == 0:
            log.info("수신함 메일 없음")
            return []

        # UIDL로 안정적인 고유 ID 확보
        uidl_map: dict[int, str] = {}
        try:
            _, uidl_lines, _ = pop.uidl()
            for line in uidl_lines:
                parts = line.decode("ascii", errors="replace").split(" ", 1)
                if len(parts) == 2:
                    uidl_map[int(parts[0])] = parts[1].strip()
        except Exception:
            pass  # UIDL 미지원 시 fallback

        # 최신 limit건 (번호 역순)
        start = max(1, num_messages - limit + 1)
        indices = list(range(num_messages, start - 1, -1))

        for idx in indices:
            try:
                _, raw_lines, _ = pop.retr(idx)
                raw = b"\r\n".join(raw_lines)
                msg = email.message_from_bytes(raw)

                uidl = uidl_map.get(idx, str(idx))
                external_id = _build_external_id(msg, uidl)
                _, sender_addr = parseaddr(msg.get("From", ""))

                results.append({
                    "external_id": external_id,
                    "sender": sender_addr or msg.get("From", ""),
                    "title": _decode_header_value(msg.get("Subject", "(제목 없음)")),
                    "body_raw": _extract_body(msg),
                    "received_at": _parse_received_at(msg),
                    "source_account": account,
                })
            except Exception as e:
                log.warning("메일 파싱 오류 idx=%d: %s", idx, e)
                continue

        log.info("하이웍스 메일 수집 완료: %d건 (limit=%d)", len(results), limit)

    except poplib.error_proto as e:
        log.error("POP3 인증/프로토콜 오류: %s", e)
    except OSError as e:
        log.error("POP3 네트워크 오류: %s", e)
    except Exception as e:
        log.error("하이웍스 메일 수집 중 예외: %s", e)
    finally:
        if pop is not None:
            try:
                pop.quit()
            except Exception:
                pass

    return results
