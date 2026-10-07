import base64
import logging
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime

from ai_orchestrator.core.config import GMAIL_CREDENTIALS_PATH, GMAIL_TOKEN_PATH

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
_BODY_MAX = 5000  # inbox에 저장할 body 최대 길이


def _get_service():
    """OAuth2 인증 후 Gmail API service 반환."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = None
    if GMAIL_TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(GMAIL_TOKEN_PATH), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not GMAIL_CREDENTIALS_PATH.exists():
                raise FileNotFoundError(
                    f"Gmail credentials 없음: {GMAIL_CREDENTIALS_PATH}\n"
                    "Google Cloud Console에서 OAuth2 credentials.json을 다운받아 해당 경로에 저장하세요."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(GMAIL_CREDENTIALS_PATH), SCOPES)
            creds = flow.run_local_server(port=0)
        GMAIL_TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")

    from googleapiclient.discovery import build

    return build("gmail", "v1", credentials=creds)


def _decode_b64(data: str) -> str:
    try:
        return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001 - Gmail 읽기전용 수집 — base64 디코드/날짜파싱/메시지파싱/전체수집 실패 시 각각 빈문자열·현재시각·None·빈리스트로 안전 폴백, 쓰기 동작 없음.
        logger.debug("base64 디코드 실패: %s", type(exc).__name__)
        return ""


def _extract_body(payload: dict) -> str:
    """payload에서 text/plain 본문 추출 (재귀)."""
    mime = payload.get("mimeType", "")
    if mime == "text/plain":
        data = payload.get("body", {}).get("data", "")
        return _decode_b64(data) if data else ""

    for part in payload.get("parts", []):
        text = _extract_body(part)
        if text:
            return text
    return ""


def _parse_message(msg: dict) -> dict | None:
    """Gmail 메시지 dict → 내부 포맷으로 변환.

    2026-09-29 확장: thread_id/message_id_header 필드 추가(회신 발송 API에 필요 —
    users.messages.send 로 스레드에 묶으려면 References/In-Reply-To 헤더에 원본의
    RFC Message-ID가 필요하다, 공식 가이드 확인). 기존 필드는 그대로라 기존 호출부
    (fetch_recent_emails/collect_to_inbox)는 영향 없음.
    """
    try:
        headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
        message_id = msg.get("id", "")
        if not message_id:
            return None

        from_addr = headers.get("from", "")
        subject = headers.get("subject", "(no subject)")
        date_str = headers.get("date", "")

        try:
            received_at = parsedate_to_datetime(date_str).isoformat() if date_str else ""
        except Exception as exc:  # noqa: BLE001 - Gmail 읽기전용 수집 — base64 디코드/날짜파싱/메시지파싱/전체수집 실패 시 각각 빈문자열·현재시각·None·빈리스트로 안전 폴백, 쓰기 동작 없음.
            logger.debug("메일 날짜 파싱 실패: %s", type(exc).__name__)
            received_at = datetime.now(UTC).isoformat()

        body = _extract_body(msg.get("payload", {}))
        body_summary = body[:200].strip()

        return {
            "message_id": message_id,
            "from": from_addr,
            "subject": subject,
            "body": body[:_BODY_MAX],
            "body_summary": body_summary,
            "received_at": received_at,
            "thread_id": msg.get("threadId", ""),
            "message_id_header": headers.get("message-id", ""),
        }
    except Exception as e:  # noqa: BLE001 - Gmail 읽기전용 수집 — base64 디코드/날짜파싱/메시지파싱/전체수집 실패 시 각각 빈문자열·현재시각·None·빈리스트로 안전 폴백, 쓰기 동작 없음.
        logger.error("메시지 파싱 실패 | id=%s | %s", msg.get("id", "?"), e)
        return None


def fetch_recent_emails(max_results: int = 50, hours: int = 24) -> list[dict]:
    """Gmail에서 최근 메일 가져오기. 인증 실패 시 빈 리스트 반환."""
    try:
        service = _get_service()
        after_ts = int((datetime.now(UTC) - timedelta(hours=hours)).timestamp())
        response = service.users().messages().list(userId="me", q=f"after:{after_ts}", maxResults=max_results).execute()

        msg_refs = response.get("messages", [])
        result = []
        for ref in msg_refs:
            msg = service.users().messages().get(userId="me", id=ref["id"], format="full").execute()
            parsed = _parse_message(msg)
            if parsed:
                result.append(parsed)

        logger.info("Gmail 수집: %d건 (max=%d, hours=%d)", len(result), max_results, hours)
        return result

    except FileNotFoundError as e:
        logger.warning("Gmail credentials 없음 — 수집 생략: %s", e)
        return []
    except Exception as e:  # noqa: BLE001 - Gmail 읽기전용 수집 — base64 디코드/날짜파싱/메시지파싱/전체수집 실패 시 각각 빈문자열·현재시각·None·빈리스트로 안전 폴백, 쓰기 동작 없음.
        logger.error("Gmail 수집 실패: %s", e)
        return []


def fetch_unread_emails(max_results: int = 10) -> list[dict]:
    """Gmail API로 안 읽은 메일 조회(CDP 대체). google_oauth 공용 자격증명 사용
    (gmail.readonly 스코프로 충분 — 이 함수는 읽기전용)."""
    from ai_orchestrator.connectors.google import oauth as google_oauth

    service = google_oauth.build_service("gmail", "v1")
    response = service.users().messages().list(userId="me", q="is:unread", maxResults=max_results).execute()
    msg_refs = response.get("messages", [])
    result = []
    for ref in msg_refs:
        msg = service.users().messages().get(userId="me", id=ref["id"], format="full").execute()
        parsed = _parse_message(msg)
        if parsed:
            result.append(parsed)
    logger.info("Gmail 안읽은메일 조회: %d건", len(result))
    return result


def _reject_header_injection(value: str, field: str) -> str:
    """MIME 헤더에 그대로 들어갈 값에 CR/LF가 섞여있으면 거부(헤더 인젝션 방지 —
    예: to="a@b.com\\nBcc: x@evil.com" 로 임의 헤더 추가/수신자 은닉 시도).
    2026-09-29 pre-push AI 리뷰 지적 반영."""
    if "\r" in value or "\n" in value:
        raise ValueError(f"{field}에 줄바꿈 문자를 포함할 수 없습니다(헤더 인젝션 방지)")
    return value


def send_reply(*, thread_id: str, in_reply_to: str, to: str, subject: str, body: str) -> dict:
    """Gmail API로 회신 발송(CDP GmailAPI.reply+send 대체). gmail.send 스코프 필요.

    RFC 2822 MIME 메시지를 만들어 base64url 인코딩 후 users.messages.send 호출
    (공식 가이드: 요청 바디는 {"raw": ...} 하나뿐). 스레드에 묶으려면 Subject를
    원본과 동일하게, In-Reply-To/References 헤더에 원본 Message-ID를 넣어야 한다
    (threadId는 별도로도 전달 — 공식 가이드 확인).
    """
    from email.mime.text import MIMEText

    from ai_orchestrator.connectors.google import oauth as google_oauth

    to = _reject_header_injection(to, "to")
    subject = _reject_header_injection(subject, "subject")
    in_reply_to = _reject_header_injection(in_reply_to, "in_reply_to")

    service = google_oauth.build_service("gmail", "v1")

    mime_subject = subject if subject.lower().startswith("re:") else f"Re: {subject}"
    message = MIMEText(body, _charset="utf-8")
    message["to"] = to
    message["subject"] = mime_subject
    if in_reply_to:
        message["In-Reply-To"] = in_reply_to
        message["References"] = in_reply_to

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
    sent = (
        service.users()
        .messages()
        .send(userId="me", body={"raw": raw, "threadId": thread_id} if thread_id else {"raw": raw})
        .execute()
    )
    logger.info("Gmail API 회신 발송 완료: id=%s thread=%s", sent.get("id"), sent.get("threadId"))
    return {"ok": True, "id": sent.get("id", ""), "thread_id": sent.get("threadId", "")}


def collect_to_inbox(max_results: int = 50, hours: int = 24) -> dict:
    """Gmail 수집 → inbox 저장. 중복 skip. 요약 반환."""
    from ai_orchestrator.tasks.inbox import create_inbox_item, exists_by_external_id

    emails = fetch_recent_emails(max_results=max_results, hours=hours)
    saved = skipped = 0

    for mail in emails:
        if exists_by_external_id(mail["message_id"], source_type="email"):
            skipped += 1
            logger.debug("중복 skip: %s", mail["message_id"])
            continue

        create_inbox_item(
            source_type="email",
            source_account=mail["from"],
            external_id=mail["message_id"],
            sender=mail["from"],
            title=mail["subject"],
            body_raw=mail["body"],
            body_summary=mail["body_summary"],
            linked_task_id="",
            metadata={"received_at": mail["received_at"]},
        )
        saved += 1

    logger.info("inbox 저장 완료: saved=%d, skipped=%d, total=%d", saved, skipped, len(emails))
    return {"saved": saved, "skipped": skipped, "total": len(emails)}
