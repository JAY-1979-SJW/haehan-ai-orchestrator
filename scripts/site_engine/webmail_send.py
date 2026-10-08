"""웹메일(Gmail/네이버/카카오) 이메일 발송 자동화.

사용법
======
  python scripts/sites/webmail_send.py \\
    --to recipient@example.com \\
    --subject "제목" \\
    --body "본문" \\
    --attach ./첨부파일.pdf

전제 조건
=========
- Chrome이 CDP 모드로 실행 중 (start_chrome_with_cdp.py)
- 이메일 계정 로그인 완료 (1회 후 세션 유지)

지원 서비스
===========
- Gmail (mail.google.com)
- 네이버 메일 (mail.naver.com)
- 카카오메일 (mail.kakao.com)

이메일 발송은 항상 APPROVE (외부 발송 카테고리) → 사용자 최종 확인 필수.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Literal

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from scripts.browser.agent.actions import (  # noqa: E402
    click,
    navigate,
    type_text,
    upload_file,
    wait_ms,
)
from scripts.browser.agent.approval_server import request_approval  # noqa: E402
from scripts.browser.agent.audit_log import get_audit_path  # noqa: E402
from scripts.browser.agent.cdp import (  # noqa: E402
    CDPConnectionError,
    is_cdp_available,
    open_cdp_session,
)
from scripts.browser.agent.intent_token import SCOPE_INTERACTION, create_intent  # noqa: E402

MailService = Literal["gmail", "naver", "kakao"]

_SERVICE_CONFIG: dict[str, dict[str, Any]] = {
    "gmail": {
        "url": "https://mail.google.com/mail/u/0/#inbox",
        "origins": ("mail.google.com", "accounts.google.com"),
        "compose_btn": "[gh='cm']",  # 편지쓰기
        "to_field": "input[name='to']",
        "subject_field": "input[name='subjectbox']",
        "body_field": "div[aria-label='메시지 텍스트']",
        "attach_btn": "div[command='Files']",  # 첨부파일
        "send_btn": "div[data-tooltip*='보내기']",
    },
    "naver": {
        "url": "https://mail.naver.com/",
        "origins": ("mail.naver.com", "nid.naver.com"),
        "compose_btn": "a.btn_write, button.btn_write",
        "to_field": "input#receiverInput",
        "subject_field": "input#subject",
        "body_field": "div.content_area",
        "attach_btn": "button.btn_attach",
        "send_btn": "button.btn_send",
    },
    "kakao": {
        "url": "https://mail.kakao.com/",
        "origins": ("mail.kakao.com", "accounts.kakao.com"),
        "compose_btn": "button.btn-compose, a.compose",
        "to_field": "input[placeholder*='받는사람']",
        "subject_field": "input[placeholder*='제목']",
        "body_field": "div.note-editable",
        "attach_btn": "button.btn-attach",
        "send_btn": "button.btn-send",
    },
}


def _ask_approval(to: str, subject: str, service: str, attachments: list[Path]) -> bool:
    return request_approval(
        action="send_email",
        label=f"이메일 발송: {subject}",
        category="SEND",
        detail={
            "수신자": to,
            "제목": subject,
            "서비스": service,
            "첨부": ", ".join(a.name for a in attachments) if attachments else "없음",
        },
    )


def _upload_attachments(page, attachments: list[Path], intent, audit_path) -> None:
    """첨부파일을 순서대로 업로드. 없는 파일은 건너뛰고, 실패는 출력만 한다."""
    for att in attachments:
        if not att.exists():
            print(f"[메일] 첨부파일 없음: {att}")
            continue
        r_up = upload_file(
            page,
            "input[type='file']",
            att,
            label=att.name,
            intent=intent,
            audit_path=audit_path,
            force=True,
        )
        if r_up.ok:
            print(f"[메일] 첨부 완료: {att.name}")
        else:
            print(f"[메일] 첨부 실패: {att.name} — {r_up.error}")
        wait_ms(1000)


def send_email(
    to: str,
    subject: str,
    body: str,
    attachments: list[Path] | None = None,
    service: MailService = "gmail",
    port: int = 9222,
) -> dict:
    """웹메일로 이메일 발송."""
    audit_path = get_audit_path()
    cfg = _SERVICE_CONFIG.get(service)
    if not cfg:
        return {"ok": False, "error": f"지원하지 않는 서비스: {service}"}

    check = is_cdp_available(port=port)
    if not check["available"]:
        print(f"[메일] Chrome CDP 연결 필요 (포트 {port})")
        print("       python scripts/browser/cdp/start_chrome_with_cdp.py")
        return {"ok": False, "error": "CDP 미연결"}

    # 이메일 발송은 항상 APPROVE → Intent에 명시적 포함
    intent = create_intent(
        natural_language=f"이메일 발송: {subject[:100]}",
        allowed_origins=cfg["origins"],
        scope=SCOPE_INTERACTION,
    )

    print(f"[메일] {service} 이메일 발송 시작")
    print(f"  수신: {to}")
    print(f"  제목: {subject}")
    print(f"  첨부: {[a.name for a in attachments] if attachments else '없음'}")

    # 최종 사용자 확인 — 브라우저 팝업 승인
    confirm = _ask_approval(to, subject, service, attachments or [])
    if not confirm:
        return {"ok": False, "error": "사용자 거부"}

    try:
        with open_cdp_session(port=port, require_existing_chrome=True) as session:
            page = session.new_tab(cfg["url"])

            # 메일 메인 이동
            navigate(page, cfg["url"], intent=intent, audit_path=audit_path, force=True)
            page.wait_for_load_state("networkidle", timeout=15000)

            # 편지쓰기 버튼
            r = click(page, cfg["compose_btn"], label="편지쓰기", intent=intent, audit_path=audit_path, force=True)
            if not r.ok:
                return {"ok": False, "error": f"편지쓰기 버튼 실패: {r.error}"}

            wait_ms(1500)

            # 수신자
            r = type_text(page, cfg["to_field"], to, label="받는사람", intent=intent, audit_path=audit_path, force=True)
            if not r.ok:
                return {"ok": False, "error": f"수신자 입력 실패: {r.error}"}
            page.keyboard.press("Enter")
            wait_ms(500)

            # 제목
            type_text(
                page, cfg["subject_field"], subject, label="제목", intent=intent, audit_path=audit_path, force=True
            )
            wait_ms(300)

            # 본문
            page.click(cfg["body_field"])
            page.keyboard.type(body, delay=20)
            wait_ms(300)

            # 첨부파일
            if attachments:
                _upload_attachments(page, attachments, intent, audit_path)

            # 전송
            r_send = click(page, cfg["send_btn"], label="이메일 발송", intent=intent, audit_path=audit_path, force=True)
            wait_ms(2000)

            if r_send.ok:
                print("[메일] ✓ 발송 완료")
                return {"ok": True, "to": to, "subject": subject, "service": service}
            else:
                return {"ok": False, "error": f"발송 버튼 실패: {r_send.error}"}

    except CDPConnectionError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:  # noqa: BLE001 - 웹메일 발송 자동화 - 이 except는 세션 전체(CDP 연결 등) 실패 시 최종 폴백으로 ok:False 반환(fail-closed), 발송 성공을 임의로 단정하지 않음
        return {"ok": False, "error": str(e)}


def main() -> None:
    parser = argparse.ArgumentParser(description="웹메일 이메일 발송")
    parser.add_argument("--to", required=True, help="수신자 이메일")
    parser.add_argument("--subject", required=True, help="제목")
    parser.add_argument("--body", default="", help="본문")
    parser.add_argument("--attach", nargs="*", type=Path, help="첨부파일 경로")
    parser.add_argument("--service", choices=["gmail", "naver", "kakao"], default="gmail", help="메일 서비스")
    parser.add_argument("--port", type=int, default=9222)
    args = parser.parse_args()

    result = send_email(
        to=args.to,
        subject=args.subject,
        body=args.body,
        attachments=args.attach or [],
        service=args.service,
        port=args.port,
    )

    if result["ok"]:
        print("\n결과: ✓ 발송 완료")
    else:
        print(f"\n결과: 실패 — {result.get('error')}")
        sys.exit(1)


if __name__ == "__main__":
    main()
