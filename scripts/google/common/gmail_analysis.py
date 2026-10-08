"""Gmail mail analysis helpers.

The analysis layer may read a selected visible message, but it never prints raw
mail body text, downloads attachments, sends replies, labels, stars, or deletes
messages. Reports store redacted previews and structured business signals only.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
REPORT_DIR = ROOT / "data" / "google_gmail_analysis"
LATEST_REPORT = ROOT / "data" / "google_gmail_analysis_latest.json"

EMAIL_RE = re.compile(r"\b([A-Za-z0-9_.+\-]{1,4})[A-Za-z0-9_.+\-]*@([A-Za-z0-9.\-]+\.[A-Za-z]{2,})\b")
PHONE_RE = re.compile(r"\b01[016789][-.\s]?\d{3,4}[-.\s]?\d{4}\b")
SECRET_RE = re.compile(
    r"\b(password|passwd|token|secret|api[_-]?key|authorization|bearer|cookie|session[_-]?id|otp)\b",
    re.IGNORECASE,
)
MONEY_RE = re.compile(r"(?:(?:KRW|USD|₩|\$)\s*)?\d[\d,]*(?:\.\d+)?\s*(?:원|만원|억원|달러|USD|KRW)?")
DATE_RE = re.compile(
    r"(?:20\d{2}[-./년]\s*)?\d{1,2}[-./월]\s*\d{1,2}(?:일|까지)?|(?:오늘|내일|금일|익일|이번 주|다음 주|마감)"
)

CATEGORY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("quote_request", ("견적", "quote", "quotation", "단가", "금액", "가격")),
    ("order_or_delivery", ("주문", "발주", "배송", "납품", "출고", "delivery", "order")),
    ("invoice_or_payment", ("세금계산서", "청구", "결제", "입금", "invoice", "payment", "billing")),
    ("meeting_or_schedule", ("회의", "미팅", "일정", "방문", "calendar", "meeting")),
    ("security_notice", ("보안", "로그인", "인증", "비밀번호", "security", "verification")),
    ("support_or_issue", ("오류", "장애", "문제", "지원", "문의", "issue", "support")),
    ("marketing_or_newsletter", ("newsletter", "뉴스레터", "프로모션", "할인", "이벤트", "광고")),
)

ACTION_KEYWORDS = (
    "요청", "확인", "회신", "검토", "처리", "제출", "보내", "공유", "작성", "문의",
    "request", "confirm", "review", "reply", "send", "submit", "check",
)


@dataclass
class GmailAnalysis:
    ok: bool
    provider: str = "gmail"
    mode: str = "read_analyze_no_state_change"
    mail_index: int = 0
    analyzed_at: str = ""
    category: str = "general"
    priority: str = "low"
    subject_preview: str = ""
    sender_preview: str = ""
    body_preview_redacted: str = ""
    body_hash: str = ""
    body_char_count: int = 0
    pii_detected: dict[str, int] = field(default_factory=dict)
    action_items: list[str] = field(default_factory=list)
    deadline_hints: list[str] = field(default_factory=list)
    money_hints: list[str] = field(default_factory=list)
    attachment_hint: bool = False
    reply_draft_suggestion: str = ""
    state_change: bool = False
    final_send_clicked: bool = False
    attachment_downloaded: bool = False
    warnings: list[str] = field(default_factory=list)
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def analyze_text(*, subject: str = "", sender: str = "", body: str = "", mail_index: int = 0) -> GmailAnalysis:
    """Analyze one mail body without exposing raw content."""
    redacted_subject = redact_text(subject)[:160]
    redacted_sender = redact_text(sender)[:80]
    redacted_body = redact_text(body)
    combined = f"{subject}\n{body}"
    category = classify_category(combined)
    priority = classify_priority(combined, category)
    redacted_combined = f"{redacted_subject} {redacted_body}".strip()
    actions = extract_action_items(redacted_combined)
    deadline_hints = unique_limited(DATE_RE.findall(redacted_combined), 8)
    money_hints = unique_limited(MONEY_RE.findall(redacted_combined), 8)
    attachment_hint = bool(re.search(r"첨부|attachment|attached|파일", combined, re.IGNORECASE))
    reply = build_reply_draft_suggestion(category, actions, deadline_hints)
    pii = {
        "email": len(EMAIL_RE.findall(body + "\n" + sender + "\n" + subject)),
        "phone": len(PHONE_RE.findall(body)),
        "sensitive_word": len(SECRET_RE.findall(body + "\n" + subject)),
    }
    warnings: list[str] = []
    if pii["sensitive_word"]:
        warnings.append("sensitive word redacted from analysis input")
    return GmailAnalysis(
        ok=True,
        mail_index=mail_index,
        analyzed_at=datetime.now(timezone.utc).isoformat(),
        category=category,
        priority=priority,
        subject_preview=redacted_subject,
        sender_preview=redacted_sender,
        body_preview_redacted=redacted_body[:1000],
        body_hash=hashlib.sha256(redacted_body.encode("utf-8")).hexdigest(),
        body_char_count=len(body),
        pii_detected=pii,
        action_items=actions,
        deadline_hints=deadline_hints,
        money_hints=money_hints,
        attachment_hint=attachment_hint,
        reply_draft_suggestion=reply,
        warnings=warnings,
    )


def analyze_visible_message(page: Any, mail_index: int = 0) -> tuple[dict[str, Any], Path]:
    """Open and analyze one visible Gmail message in the current user session."""
    from scripts.google.common.gmail_api import GmailAPI

    api = GmailAPI(page)
    read = api.read(mail_index)
    if not read.get("ok"):
        result = GmailAnalysis(
            ok=False,
            mail_index=mail_index,
            analyzed_at=datetime.now(timezone.utc).isoformat(),
            error=str(read.get("error", "read_failed"))[:160],
        )
        return save_analysis(result)
    analysis = analyze_text(
        subject=read.get("subject_preview", ""),
        sender=read.get("sender_preview", ""),
        body=read.get("body_preview", ""),
        mail_index=mail_index,
    )
    return save_analysis(analysis)


def save_analysis(analysis: GmailAnalysis) -> tuple[dict[str, Any], Path]:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    LATEST_REPORT.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    target = REPORT_DIR / f"gmail_analysis_{timestamp}.json"
    data = analysis.to_dict()
    text = json.dumps(data, ensure_ascii=False, indent=2)
    target.write_text(text, encoding="utf-8")
    LATEST_REPORT.write_text(text, encoding="utf-8")
    return data, target


def print_analysis_summary(result: dict[str, Any], path: Path) -> None:
    print("=" * 60)
    print("Gmail mail analysis")
    print("=" * 60)
    print(f"ok: {result.get('ok')}")
    print(f"category: {result.get('category')}")
    print(f"priority: {result.get('priority')}")
    print(f"action_items: {len(result.get('action_items') or [])}")
    print(f"deadline_hints: {len(result.get('deadline_hints') or [])}")
    print(f"money_hints: {len(result.get('money_hints') or [])}")
    print(f"attachment_hint: {result.get('attachment_hint')}")
    print(f"state_change: {result.get('state_change')}")
    print(f"final_send_clicked: {result.get('final_send_clicked')}")
    print(f"attachment_downloaded: {result.get('attachment_downloaded')}")
    if result.get("warnings"):
        print("warnings:")
        for warning in result["warnings"]:
            print(f"- {warning}")
    print(f"saved: {path}")
    print(f"latest: {LATEST_REPORT}")


def redact_text(text: str) -> str:
    text = text or ""
    text = EMAIL_RE.sub(lambda m: f"{m.group(1)}***@{m.group(2)}", text)
    text = PHONE_RE.sub("[redacted-phone]", text)
    text = SECRET_RE.sub("[redacted-sensitive]", text)
    return re.sub(r"\s+", " ", text).strip()


def classify_category(text: str) -> str:
    lowered = (text or "").lower()
    for category, keywords in CATEGORY_RULES:
        if any(keyword.lower() in lowered for keyword in keywords):
            return category
    return "general"


def classify_priority(text: str, category: str) -> str:
    lowered = (text or "").lower()
    if any(word in lowered for word in ("긴급", "마감", "장애", "오류", "urgent", "asap", "immediately")):
        return "high"
    if category in {"quote_request", "invoice_or_payment", "support_or_issue", "security_notice"}:
        return "medium"
    if category == "marketing_or_newsletter":
        return "low"
    return "low"


def extract_action_items(text: str) -> list[str]:
    sentences = re.split(r"(?<=[.!?。])\s+|[\n\r]+", text or "")
    items: list[str] = []
    for sentence in sentences:
        clean = sentence.strip()
        if not clean:
            continue
        lowered = clean.lower()
        if any(keyword in lowered for keyword in ACTION_KEYWORDS):
            items.append(clean[:180])
    return unique_limited(items, 8)


def build_reply_draft_suggestion(category: str, actions: list[str], deadlines: list[str]) -> str:
    if category == "quote_request":
        base = "요청하신 내용을 확인했습니다. 필요한 조건을 검토한 뒤 견적 가능 여부와 추가 확인사항을 회신드리겠습니다."
    elif category == "invoice_or_payment":
        base = "결제/청구 관련 내용을 확인했습니다. 내부 내역과 대조한 뒤 처리 결과를 회신드리겠습니다."
    elif category == "support_or_issue":
        base = "문의하신 문제를 확인했습니다. 원인과 조치 가능 범위를 점검한 뒤 회신드리겠습니다."
    elif category == "security_notice":
        base = "보안 알림 내용을 확인했습니다. 본인 활동 여부와 계정 상태를 먼저 점검하겠습니다."
    else:
        base = "메일 내용을 확인했습니다. 필요한 사항을 검토한 뒤 회신드리겠습니다."
    if actions:
        base += " 요청사항은 별도 체크리스트로 확인하겠습니다."
    if deadlines:
        base += " 언급된 일정도 함께 확인하겠습니다."
    return base


def unique_limited(values: list[str], limit: int) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        value = str(value).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value[:120])
        if len(out) >= limit:
            break
    return out
