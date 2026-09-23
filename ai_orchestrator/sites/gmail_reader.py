import base64
import logging
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime

from ai_orchestrator.config import GMAIL_CREDENTIALS_PATH, GMAIL_TOKEN_PATH

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
    except Exception:
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
    """Gmail 메시지 dict → 내부 포맷으로 변환."""
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
        except Exception:
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
        }
    except Exception as e:
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
    except Exception as e:
        logger.error("Gmail 수집 실패: %s", e)
        return []


def collect_to_inbox(max_results: int = 50, hours: int = 24) -> dict:
    """Gmail 수집 → inbox 저장. 중복 skip. 요약 반환."""
    from ai_orchestrator.inbox import create_inbox_item, exists_by_external_id

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
