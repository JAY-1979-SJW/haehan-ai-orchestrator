"""민원24/정부24 온라인 민원 접수 자동화.

승인 정책
=========
- 폼 작성, 첨부파일 업로드, 페이지 탐색: 자동 진행 (승인 없음)
- 최종 제출 버튼 클릭 직전: 단 1회 사용자 승인

사용법
======
  python scripts/local_agent/minwon_submit.py \\
    --title "건축허가 신청" \\
    --content "내용..." \\
    --attach ./도면.pdf ./신청서.hwp

지원 서비스
===========
- 국민신문고 (www.epeople.go.kr) — 기본
- 정부24 (www.gov.kr)
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Literal

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from ai_orchestrator.local_agent.browser.cdp import (
    open_cdp_session, is_cdp_available, CDPConnectionError,
)
from ai_orchestrator.local_agent.browser.intent_token import create_intent, SCOPE_INTERACTION
from ai_orchestrator.local_agent.browser.actions import (
    navigate, click, type_text, upload_file,
    screenshot, wait_ms,
)
from ai_orchestrator.local_agent.browser.audit_log import get_audit_path

MinwonService = Literal["gov24", "epeople"]

_SERVICE_CONFIG = {
    "gov24": {
        "name": "정부24",
        "url": "https://www.gov.kr/portal/minwon/main",
        "origins": ("www.gov.kr", "minwon.go.kr", "auth.gov.kr"),
        "search_field": "input#searchText",
        "search_btn": "button.btn_search",
        "submit_btn": "button[type='submit'], .btn-submit",
    },
    "epeople": {
        "name": "국민신문고",
        "url": "https://www.epeople.go.kr/nep/cit/cmplt/retrieveNewWriteComplaint.npaid",
        "origins": ("www.epeople.go.kr", "uat.epeople.go.kr"),
        "title_field": "input#complaintTitle",
        "content_field": "textarea#complaintContent",
        "submit_btn": "button#btnWrite",
    },
}


def _ask_submit_approval(title: str, service_name: str,
                          attachments: list[Path]) -> bool:
    """제출 직전 1회만 사용자 승인 요청."""
    print(f"\n{'='*60}")
    print(f"[최종 확인] 민원을 접수합니다.")
    print(f"  서비스: {service_name}")
    print(f"  제목: {title}")
    if attachments:
        print(f"  첨부: {', '.join(a.name for a in attachments)}")
    print(f"{'='*60}")
    ans = input("→ 제출하시겠습니까? (y/n): ").strip().lower()
    return ans in ("y", "yes", "네", "예")


def submit_minwon(
    title: str,
    content: str,
    attachments: list[Path] | None = None,
    service: MinwonService = "epeople",
    minwon_type: str = "일반민원",
    port: int = 9222,
    output_dir: Path | None = None,
) -> dict:
    """민원 접수 실행. 제출 직전 1회만 사용자 승인."""
    audit_path = get_audit_path()
    cfg = _SERVICE_CONFIG.get(service)
    if not cfg:
        return {"ok": False, "error": f"지원하지 않는 서비스: {service}"}

    output_dir = output_dir or Path("data/reports/minwon")
    output_dir.mkdir(parents=True, exist_ok=True)
    attachments = attachments or []

    check = is_cdp_available(port=port)
    if not check["available"]:
        print(f"[민원] Chrome CDP 연결 필요")
        print(f"       python scripts/local_agent/start_chrome_with_cdp.py")
        return {"ok": False, "error": "CDP 미연결"}

    intent = create_intent(
        natural_language=f"민원 접수: {title[:100]}",
        allowed_origins=cfg["origins"],
        scope=SCOPE_INTERACTION,
    )

    print(f"[민원] {cfg['name']} 민원 접수 준비")
    print(f"  종류: {minwon_type}")
    print(f"  제목: {title}")

    try:
        with open_cdp_session(port=port, require_existing_chrome=True) as session:
            page = session.new_tab(cfg["url"])

            # 1. 페이지 이동 (자동)
            navigate(page, cfg["url"], intent=intent, audit_path=audit_path,
                     force=True, wait_until="networkidle")
            print(f"[민원] {cfg['name']} 접속")

            # 2. 로그인 필요 시 사용자 직접 처리
            page.wait_for_load_state("networkidle", timeout=10000)
            page_text = page.inner_text("body")
            if "로그인" in page_text:
                print("\n[민원] 로그인이 필요합니다. 브라우저에서 로그인 후 엔터를 누르세요.")
                input("→ 로그인 완료 후 엔터: ")
                navigate(page, cfg["url"], intent=intent, audit_path=audit_path,
                         force=True, wait_until="networkidle")

            # 3. 폼 작성 (자동 — 승인 없음)
            if service == "epeople":
                _fill_epeople_form(page, title, content, attachments, intent, audit_path, cfg)
            elif service == "gov24":
                _fill_gov24_form(page, title, content, attachments, intent, audit_path, cfg)

            # 4. 제출 전 스크린샷
            ss_before = output_dir / f"minwon_before_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            screenshot(page, ss_before, intent=intent, audit_path=audit_path, force=True)
            print(f"[민원] 작성 완료 스크린샷: {ss_before}")

            # 5. ★ 제출 직전 단 1회 승인 ★
            if not _ask_submit_approval(title, cfg["name"], attachments):
                print("[민원] 사용자가 제출을 취소했습니다.")
                return {"ok": False, "error": "사용자 취소"}

            # 6. 제출 실행 (force=True — 승인 완료)
            submit_sel = cfg.get("submit_btn", "button[type='submit']")
            r = click(page, submit_sel, label="민원 접수 제출",
                      intent=intent, audit_path=audit_path, force=True)
            wait_ms(3000)
            page.wait_for_load_state("networkidle", timeout=30000)

            # 7. 완료 스크린샷
            ss_done = output_dir / f"minwon_done_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            screenshot(page, ss_done, intent=intent, audit_path=audit_path, force=True)

            if r.ok:
                print(f"[민원] ✓ 접수 완료")
                print(f"  결과 스크린샷: {ss_done}")
                return {
                    "ok": True,
                    "title": title,
                    "service": service,
                    "screenshot_done": str(ss_done),
                    "intent_id": intent.intent_id,
                }
            else:
                return {"ok": False, "error": f"제출 실패: {r.error}"}

    except CDPConnectionError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _fill_epeople_form(page, title, content, attachments, intent, audit_path, cfg) -> None:
    wait_ms(1000)
    type_text(page, cfg["title_field"], title, label="민원 제목",
              intent=intent, audit_path=audit_path, force=True)
    wait_ms(300)
    type_text(page, cfg["content_field"], content, label="민원 내용",
              intent=intent, audit_path=audit_path, force=True)
    for att in attachments:
        if not att.exists():
            print(f"[민원] 첨부파일 없음: {att}")
            continue
        r = upload_file(page, "input[type='file']", att, label=att.name,
                        intent=intent, audit_path=audit_path, force=True)
        if r.ok:
            print(f"[민원] 첨부: {att.name}")
        wait_ms(800)


def _fill_gov24_form(page, title, content, attachments, intent, audit_path, cfg) -> None:
    search_field = cfg.get("search_field")
    if search_field:
        type_text(page, search_field, title[:50], label="민원 검색",
                  intent=intent, audit_path=audit_path, force=True)
        click(page, cfg["search_btn"], label="검색",
              intent=intent, audit_path=audit_path, force=True)
        wait_ms(2000)


def main() -> None:
    parser = argparse.ArgumentParser(description="온라인 민원 접수 (제출 직전 1회 승인)")
    parser.add_argument("--title", required=True, help="민원 제목")
    parser.add_argument("--content", default="", help="민원 내용")
    parser.add_argument("--type", default="일반민원", help="민원 종류")
    parser.add_argument("--attach", nargs="*", type=Path, help="첨부파일")
    parser.add_argument("--service", choices=["gov24", "epeople"],
                        default="epeople")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--port", type=int, default=9222)
    args = parser.parse_args()

    result = submit_minwon(
        title=args.title,
        content=args.content,
        attachments=args.attach or [],
        service=args.service,
        minwon_type=args.type,
        port=args.port,
        output_dir=args.output,
    )

    if result["ok"]:
        print(f"\n결과: ✓ 접수 완료")
    else:
        print(f"\n결과: 실패 — {result.get('error')}")
        sys.exit(1)


if __name__ == "__main__":
    main()
