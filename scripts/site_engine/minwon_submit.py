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
from typing import Any, Literal

_BOOTSTRAP_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BOOTSTRAP_ROOT))

from scripts.common.app_paths import repo_root as _repo_root  # noqa: E402

_ROOT = _repo_root()

from scripts.browser.agent.actions import (  # noqa: E402 - sys.path.insert 이후 로컬 import (레거시, 이번 작업과 무관)
    click,
    navigate,
    screenshot,
    type_text,
    upload_file,
    wait_ms,
)
from scripts.browser.agent.approval_server import (  # noqa: E402 - sys.path.insert 이후 로컬 import (레거시, 이번 작업과 무관)
    request_approval,
)
from scripts.browser.agent.audit_log import (  # noqa: E402 - sys.path.insert 이후 로컬 import (레거시, 이번 작업과 무관)
    get_audit_path,
)
from scripts.browser.agent.cdp import (  # noqa: E402 - sys.path.insert 이후 로컬 import (레거시, 이번 작업과 무관)
    CDPConnectionError,
    is_cdp_available,
    open_cdp_session,
)
from scripts.browser.agent.intent_token import (  # noqa: E402 - sys.path.insert 이후 로컬 import (레거시, 이번 작업과 무관)
    SCOPE_INTERACTION,
    create_intent,
)

MinwonService = Literal["gov24", "epeople"]

_SERVICE_CONFIG: dict[str, dict[str, Any]] = {
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


def _ask_submit_approval(title: str, service_name: str, attachments: list[Path]) -> bool:
    """제출 직전 1회 승인 — 브라우저 팝업 UI."""
    return request_approval(
        action="submit",
        label=f"민원 접수: {title}",
        category="LEGAL",
        detail={
            "서비스": service_name,
            "제목": title,
            "첨부파일": ", ".join(a.name for a in attachments) if attachments else "없음",
        },
    )


def submit_minwon(  # noqa: PLR0913 - 공개 시그니처 유지(동작 불변 리팩터링 범위)
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
        print("[민원] Chrome CDP 연결 필요")
        print("       python scripts/browser/cdp/start_chrome_with_cdp.py")
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
            navigate(page, cfg["url"], intent=intent, audit_path=audit_path, force=True, wait_until="networkidle")
            print(f"[민원] {cfg['name']} 접속")

            # 2. 로그인 필요 시 사용자 직접 처리
            page.wait_for_load_state("networkidle", timeout=10000)
            page_text = page.inner_text("body")
            if "로그인" in page_text:
                print("\n[민원] 로그인이 필요합니다. 브라우저에서 로그인 후 엔터를 누르세요.")
                input("→ 로그인 완료 후 엔터: ")
                navigate(page, cfg["url"], intent=intent, audit_path=audit_path, force=True, wait_until="networkidle")

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
            r = click(page, submit_sel, label="민원 접수 제출", intent=intent, audit_path=audit_path, force=True)
            wait_ms(3000)
            page.wait_for_load_state("networkidle", timeout=30000)

            # 7. 완료 스크린샷
            ss_done = output_dir / f"minwon_done_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            screenshot(page, ss_done, intent=intent, audit_path=audit_path, force=True)

            if r.ok:
                print("[민원] ✓ 접수 완료")
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
    except Exception as e:  # noqa: BLE001 - 민원 접수 자동화 - 제출 직전 request_approval()로 사용자 승인 게이트를 이미 통과한 뒤에만 제출 실행. except는 CDP연결/폼작성/제출 전체를 감싸 실패시 ok:False 반환(fail-closed), 승인 우회나 자격증명 노출 없음
        return {"ok": False, "error": str(e)}


def _fill_epeople_form(page, title, content, attachments, intent, audit_path, cfg) -> None:  # noqa: PLR0913 - 공개 시그니처 유지(동작 불변 리팩터링 범위)
    wait_ms(1000)
    type_text(page, cfg["title_field"], title, label="민원 제목", intent=intent, audit_path=audit_path, force=True)
    wait_ms(300)
    type_text(page, cfg["content_field"], content, label="민원 내용", intent=intent, audit_path=audit_path, force=True)
    for att in attachments:
        if not att.exists():
            print(f"[민원] 첨부파일 없음: {att}")
            continue
        r = upload_file(
            page, "input[type='file']", att, label=att.name, intent=intent, audit_path=audit_path, force=True
        )
        if r.ok:
            print(f"[민원] 첨부: {att.name}")
        wait_ms(800)


def _fill_gov24_form(page, title, content, attachments, intent, audit_path, cfg) -> None:  # noqa: PLR0913 - 공개 시그니처 유지(동작 불변 리팩터링 범위)
    search_field = cfg.get("search_field")
    if search_field:
        type_text(page, search_field, title[:50], label="민원 검색", intent=intent, audit_path=audit_path, force=True)
        click(page, cfg["search_btn"], label="검색", intent=intent, audit_path=audit_path, force=True)
        wait_ms(2000)


def main() -> None:
    parser = argparse.ArgumentParser(description="온라인 민원 접수 (제출 직전 1회 승인)")
    parser.add_argument("--title", required=True, help="민원 제목")
    parser.add_argument("--content", default="", help="민원 내용")
    parser.add_argument("--type", default="일반민원", help="민원 종류")
    parser.add_argument("--attach", nargs="*", type=Path, help="첨부파일")
    parser.add_argument("--service", choices=["gov24", "epeople"], default="epeople")
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
        print("\n결과: ✓ 접수 완료")
    else:
        print(f"\n결과: 실패 — {result.get('error')}")
        sys.exit(1)


if __name__ == "__main__":
    main()
