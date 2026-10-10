"""Google 도구 채팅 명령 API."""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from tools.gates.auth import require_role

from ._helpers import audit, duration_ms

router = APIRouter()

# 키워드 → 도메인·액션 매핑
_CMD_MAP = [
    (
        ["메일", "이메일", "gmail", "받은편지", "보내"],
        "Gmail",
        "mail.google.com",
        "gmail_open",
        "https://mail.google.com/",
    ),
    (
        ["일정", "캘린더", "calendar", "미팅", "약속"],
        "캘린더",
        "calendar.google.com",
        "calendar_create_event",
        "https://calendar.google.com/",
    ),
    (
        ["드라이브", "drive", "파일 보", "파일 업"],
        "Drive",
        "drive.google.com",
        "drive_open",
        "https://drive.google.com/",
    ),
    (["문서", "docs", "구글닥스"], "Docs", "docs.google.com", "docs_open", "https://docs.google.com/"),
    (["시트", "sheets", "스프레드"], "Sheets", "docs.google.com", "sheets_open", "https://sheets.google.com/"),
    (
        ["유튜브 스튜디오", "studio", "영상 업로드"],
        "YouTube Studio",
        "studio.youtube.com",
        "youtube_studio_open",
        "https://studio.youtube.com/",
    ),
    (["유튜브", "youtube", "영상"], "YouTube", "www.youtube.com", "youtube_open", "https://www.youtube.com/"),
    (
        ["분석", "analytics", "트래픽"],
        "Analytics",
        "analytics.google.com",
        "analytics_open",
        "https://analytics.google.com/",
    ),
    (["광고", "ads", "캠페인"], "Google Ads", "ads.google.com", "ads_open", "https://ads.google.com/"),
    (
        ["gcp", "클라우드", "cloud", "bigquery", "vm", "배포"],
        "GCP Console",
        "console.cloud.google.com",
        "cloud_console_open",
        "https://console.cloud.google.com/",
    ),
    (
        ["gemini", "제미나이", "ai 채팅", "ai 질문"],
        "Gemini",
        "gemini.google.com",
        "gemini_open",
        "https://gemini.google.com/",
    ),
    (
        ["search console", "서치콘솔", "색인", "seo"],
        "Search Console",
        "search.google.com",
        "search_console_open",
        "https://search.google.com/",
    ),
    (["keep", "메모", "노트"], "Keep", "keep.google.com", "keep_open", "https://keep.google.com/"),
    (["tasks", "작업", "할일"], "Tasks", "tasks.google.com", "tasks_open", "https://tasks.google.com/"),
    (["meet", "화상", "화상회의"], "Meet", "meet.google.com", "meet_open", "https://meet.google.com/"),
    (["사진", "photos", "포토"], "Photos", "photos.google.com", "photos_open", "https://photos.google.com/"),
    (
        ["firebase", "파이어베이스"],
        "Firebase",
        "console.firebase.google.com",
        "firebase_console_open",
        "https://console.firebase.google.com/",
    ),
    (
        ["ai studio", "aistudio", "api 키 생성"],
        "AI Studio",
        "aistudio.google.com",
        "ai_studio_open",
        "https://aistudio.google.com/",
    ),
    (["adsense", "어드센스", "수익"], "AdSense", "adsense.google.com", "adsense_open", "https://adsense.google.com/"),
    (
        ["merchant", "머천트", "상품"],
        "Merchant Center",
        "merchants.google.com",
        "merchant_center_open",
        "https://merchants.google.com/",
    ),
    (
        ["tag manager", "태그매니저"],
        "Tag Manager",
        "tagmanager.google.com",
        "tag_manager_open",
        "https://tagmanager.google.com/",
    ),
    (
        ["looker", "루커", "대시보드"],
        "Looker Studio",
        "lookerstudio.google.com",
        "looker_studio_open",
        "https://lookerstudio.google.com/",
    ),
    (
        ["비즈니스 프로필", "business profile"],
        "Business",
        "business.google.com",
        "business_profile_open",
        "https://business.google.com/",
    ),
    (
        ["연락처", "contacts", "주소록"],
        "연락처",
        "contacts.google.com",
        "contacts_open",
        "https://contacts.google.com/",
    ),
    (
        ["colab", "코랩", "노트북", "파이썬"],
        "Colab",
        "colab.research.google.com",
        "colab_open",
        "https://colab.research.google.com/",
    ),
    (
        ["play console", "플레이", "앱 배포"],
        "Play Console",
        "play.google.com",
        "play_console_open",
        "https://play.google.com/console/",
    ),
    (
        ["apps script", "앱스스크립트"],
        "Apps Script",
        "script.google.com",
        "apps_script_open",
        "https://script.google.com/",
    ),
]

# 도메인별 한국어 설명
_DOMAIN_DESC = {
    "Gmail": "이메일 수신·발송·검색",
    "캘린더": "일정 조회·생성·관리",
    "Drive": "파일 저장·공유·검색",
    "Docs": "문서 작성·편집·공유",
    "Sheets": "스프레드시트 조회·셀 업데이트",
    "YouTube Studio": "영상 업로드·메타데이터 편집",
    "YouTube": "영상 시청·댓글·구독",
    "Analytics": "웹사이트 트래픽·전환 분석",
    "Google Ads": "광고 캠페인 조회·예산 관리",
    "GCP Console": "Cloud Run·GCE·BigQuery 등 16개 서비스",
    "Gemini": "Gemini AI 채팅·프롬프트 제출",
    "Search Console": "검색 노출·색인 요청·사이트맵",
}


def _match_command(message: str) -> dict | None:
    lm = message.lower()
    for words, domain, host, action, url in _CMD_MAP:
        if any(w in lm for w in words):
            return {"domain": domain, "host": host, "action_key": action, "url": url}
    return None


class ChatRequest(BaseModel):
    message: str
    domain: str = ""
    action_key: str = ""
    host: str = ""


class ActionRequest(BaseModel):
    host: str
    action_key: str


@router.post("/chat")
def google_chat(
    body: ChatRequest,
    user: dict = Depends(require_role("admin", "owner")),
) -> dict[str, Any]:
    """자연어 명령을 Google 도메인 액션으로 매핑."""
    t0 = time.monotonic()
    msg = body.message.strip()

    matched = (
        _match_command(msg)
        if not body.action_key
        else {"domain": body.domain, "host": body.host, "action_key": body.action_key, "url": ""}
    )

    if not matched:
        audit("GOOGLE_CHAT_UNMATCHED", user, status="unmatched", note=msg[:100])
        return {
            "ok": False,
            "reply": (
                "어떤 구글 서비스를 원하시나요? 예시:\n"
                "• 'Gmail 받은편지함 보여줘'\n"
                "• '드라이브에서 최근 파일 찾아줘'\n"
                "• '캘린더에 내일 오전 10시 미팅 추가해줘'\n"
                "• 'YouTube Studio 열어줘'"
            ),
            "suggestions": ["Gmail", "Drive", "캘린더", "YouTube", "GCP Console"],
            "duration_ms": duration_ms(t0),
        }

    domain = matched["domain"]
    action = matched["action_key"]
    desc = _DOMAIN_DESC.get(domain, "")

    # 상태 변경 액션은 승인 메시지 반환 (실제 실행은 사용자 승인 후)
    requires_approval = not action.endswith("_open")
    if requires_approval:
        reply = (
            f"**{domain}** — {desc}\n"
            f"`{action}` 실행은 승인이 필요합니다.\n"
            f"아래 버튼을 눌러 진행하거나 사이트를 직접 여세요."
        )
        audit(
            "GOOGLE_CHAT_APPROVAL_REQUIRED", user, status="approval_required", note=f"domain={domain} action={action}"
        )
    else:
        reply = f"**{domain}** 을(를) 열겠습니다. {desc}"
        audit("GOOGLE_CHAT_OPEN", user, status="ok", note=f"domain={domain} action={action}")

    return {
        "ok": True,
        "reply": reply,
        "domain": domain,
        "host": matched["host"],
        "action": action,
        "url": matched.get("url", ""),
        "requires_approval": requires_approval,
        "duration_ms": duration_ms(t0),
    }


@router.post("/action")
def google_action(
    body: ActionRequest,
    user: dict = Depends(require_role("admin", "owner")),
) -> dict[str, Any]:
    """도메인 액션 실행 (읽기 전용만 자동, 상태 변경은 승인 필요)."""
    t0 = time.monotonic()
    action = body.action_key

    if action.endswith("_open"):
        audit("GOOGLE_ACTION_OPEN", user, status="ok", note=f"action={action}")
        return {"ok": True, "message": "사이트를 열 준비가 됐습니다.", "action": action, "duration_ms": duration_ms(t0)}

    audit("GOOGLE_ACTION_APPROVAL_REQUIRED", user, status="approval_required", note=f"action={action}")
    return {
        "ok": False,
        "reason": "approval_required",
        "message": f"{action} 실행은 명시적 승인이 필요합니다.",
        "duration_ms": duration_ms(t0),
    }
