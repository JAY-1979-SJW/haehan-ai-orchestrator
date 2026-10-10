"""
하이웍스 메일 읽기 전용 수집 모듈
방식: POP3 평문 (포트 110) — 하이웍스는 IMAP 미지원, POP3만 제공
      SSL/995는 서버 인증서 문제로 연결 불가 확인(2026-04-22)
서버: mailapp.hiworks.co.kr:110
읽기 전용: DELE 명령 미사용, 메일 상태 변경 없음
"""

import contextlib
import email
import email.header
import os
import poplib
import re
from datetime import UTC, datetime
from email.utils import parseaddr, parsedate_to_datetime

from orchestrator_v1.core.logger import get_logger

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


def _decode_payload(part: email.message.Message) -> str | None:
    """파트 payload 를 디코드. payload 가 없으면 None."""
    payload = part.get_payload(decode=True)
    if not payload or not isinstance(payload, bytes):
        return None
    charset = part.get_content_charset() or "utf-8"
    return payload.decode(charset, errors="replace")


def _collect_body_parts(msg: email.message.Message) -> tuple[list[str], list[str]]:
    """메일에서 (text/plain 조각, text/html 조각) 목록을 수집한다."""
    plain_parts: list[str] = []
    html_parts: list[str] = []

    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            cd = str(part.get("Content-Disposition", ""))
            if "attachment" in cd:
                continue
            text = _decode_payload(part)
            if text is None:
                continue
            if ct == "text/plain":
                plain_parts.append(text)
            elif ct == "text/html":
                html_parts.append(text)
    else:
        text = _decode_payload(msg)
        if text is not None:
            if msg.get_content_type() == "text/html":
                html_parts.append(text)
            else:
                plain_parts.append(text)
    return plain_parts, html_parts


def _extract_body(msg: email.message.Message) -> str:
    """text/plain 우선, 없으면 text/html 태그 제거, 그 외 빈 문자열."""
    plain_parts, html_parts = _collect_body_parts(msg)

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
            return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S")
        except Exception:  # noqa: S110, BLE001
            pass
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S")


def _build_external_id(msg: email.message.Message, uidl: str) -> str:
    """Message-ID 우선, 없으면 POP3 UIDL 기반."""
    msg_id = msg.get("Message-ID", "").strip()
    if msg_id:
        return msg_id
    return f"uidl:{uidl}"


def _load_uidl_map(pop: poplib.POP3) -> dict[int, str]:
    """UIDL 번호→고유 ID 맵. UIDL 미지원 시 빈 맵(fallback)."""
    uidl_map: dict[int, str] = {}
    try:
        _, uidl_lines, _ = pop.uidl()
        for line in uidl_lines:
            parts = line.decode("ascii", errors="replace").split(" ", 1)
            if len(parts) == 2:
                uidl_map[int(parts[0])] = parts[1].strip()
    except Exception:  # noqa: S110, BLE001
        pass  # UIDL 미지원 시 fallback
    return uidl_map


def _fetch_one_mail(pop: poplib.POP3, idx: int, uidl_map: dict[int, str], account: str) -> dict:
    """POP3 에서 idx 번 메일 1건을 읽어 수집 dict 로 변환."""
    _, raw_lines, _ = pop.retr(idx)
    raw = b"\r\n".join(raw_lines)
    msg = email.message_from_bytes(raw)

    uidl = uidl_map.get(idx, str(idx))
    external_id = _build_external_id(msg, uidl)
    _, sender_addr = parseaddr(msg.get("From", ""))

    return {
        "external_id": external_id,
        "sender": sender_addr or msg.get("From", ""),
        "title": _decode_header_value(msg.get("Subject", "(제목 없음)")),
        "body_raw": _extract_body(msg),
        "received_at": _parse_received_at(msg),
        "source_account": account,
    }


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
        uidl_map = _load_uidl_map(pop)

        # 최신 limit건 (번호 역순)
        start = max(1, num_messages - limit + 1)
        indices = list(range(num_messages, start - 1, -1))

        for idx in indices:
            try:
                results.append(_fetch_one_mail(pop, idx, uidl_map, account))
            except Exception as e:  # noqa: BLE001 - 하이웍스 POP3 메일 읽기전용 수집 - 개별 메일 파싱 실패는 continue, 연결 종료 실패는 무시
                log.warning("메일 파싱 오류 idx=%d: %s", idx, e)
                continue

        log.info("하이웍스 메일 수집 완료: %d건 (limit=%d)", len(results), limit)

    except poplib.error_proto as e:
        log.error("POP3 인증/프로토콜 오류: %s", e)
    except OSError as e:
        log.error("POP3 네트워크 오류: %s", e)
    except Exception as e:  # noqa: BLE001 - 하이웍스 POP3 메일 읽기전용 수집 - 개별 메일 파싱 실패는 continue, 연결 종료 실패는 무시
        log.error("하이웍스 메일 수집 중 예외: %s", e)
    finally:
        if pop is not None:
            with contextlib.suppress(Exception):
                pop.quit()

    return results
