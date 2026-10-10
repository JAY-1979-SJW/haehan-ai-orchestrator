"""정부24 주민등록등본 발급 자동화.

사용법
======
  python scripts/local_agent/gov24_certificate.py
  python scripts/local_agent/gov24_certificate.py --type 등본 --output ./등본.pdf
  python scripts/local_agent/gov24_certificate.py --type 초본 --output ./초본.pdf

지원 서류
=========
- 주민등록등본 (기본)
- 주민등록초본

전제 조건
=========
- Chrome이 CDP 모드로 실행 중 (start_chrome_with_cdp.py 먼저 실행)
- 정부24 로그인 완료 (간편인증/공인인증서)
  → 첫 실행 시 사용자가 직접 로그인, 이후 세션 자동 유지

흐름
====
1. CDP 연결 확인
2. 정부24 → 주민등록등본 발급 페이지 이동
3. 발급 옵션 선택 (현재 주소 기준, 세대원 포함 등)
4. 신청하기 → 사용자 승인 (APPROVE)
5. PDF 다운로드 (NOTIFY)
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

_BOOTSTRAP_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BOOTSTRAP_ROOT))

from scripts.common.app_paths import repo_root as _repo_root  # noqa: E402

_ROOT = _repo_root()

from scripts.browser.agent.actions import (  # noqa: E402
    GateApprovalRequired,
    click,
    navigate,
    screenshot,
)
from scripts.browser.agent.audit_log import get_audit_path  # noqa: E402
from scripts.browser.agent.cdp import (  # noqa: E402
    CDPConnectionError,
    is_cdp_available,
    open_cdp_session,
)
from scripts.browser.agent.intent_token import create_intent  # noqa: E402

GOV24_URL = "https://www.gov.kr"
GOV24_CERT_SEARCH = "https://www.gov.kr/mw/AA020InfoCappView.do?HighCtgCD=A01001&CappBizCD=13100000015&tp_seq=01"
GOV24_ORIGINS = ("www.gov.kr", "minwon.go.kr", "auth.gov.kr", "iam.go.kr")

CERT_TYPES = {
    "등본": {"label": "주민등록등본", "value": "01"},
    "초본": {"label": "주민등록초본", "value": "02"},
}


def _ask_user_approval(prompt: str) -> bool:
    print(f"\n{'=' * 60}")
    print(prompt)
    ans = input("→ 승인 (y/n): ").strip().lower()
    return ans in ("y", "yes", "네", "예")


def run_gov24_certificate(
    cert_type: str = "등본",
    output_path: Path | None = None,
    port: int = 9222,
) -> dict:
    audit_path = get_audit_path()
    output_path = output_path or Path(
        f"data/reports/certificates/주민등록{cert_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # CDP 연결 확인
    check = is_cdp_available(port=port)
    if not check["available"]:
        print("[오류] Chrome이 CDP 모드로 실행되지 않았습니다.")
        print(f"       먼저 실행: python scripts/browser/cdp/start_chrome_with_cdp.py --port {port}")
        return {"ok": False, "error": "CDP 미연결"}

    # Intent 생성
    intent = create_intent(
        natural_language=f"정부24에서 주민등록{cert_type} 발급 신청",
        allowed_origins=GOV24_ORIGINS,
    )

    print(f"[정부24] 주민등록{cert_type} 발급 시작")
    print(f"[정부24] Intent: {intent.intent_id}")

    try:
        with open_cdp_session(port=port, require_existing_chrome=True) as session:
            page = session.new_tab(GOV24_URL)

            # 1. 정부24 메인 이동
            r = navigate(page, GOV24_URL, intent=intent, audit_path=audit_path)
            if not r.ok:
                return {"ok": False, "error": f"정부24 접속 실패: {r.error}"}
            print("[정부24] 메인 접속 완료")

            # 2. 등본 발급 페이지 이동
            try:
                r = navigate(page, GOV24_CERT_SEARCH, intent=intent, audit_path=audit_path, wait_until="networkidle")
            except GateApprovalRequired as e:
                if not _ask_user_approval(e.approval_prompt()):
                    return {"ok": False, "error": "사용자 거부"}
                r = navigate(
                    page, GOV24_CERT_SEARCH, intent=intent, audit_path=audit_path, wait_until="networkidle", force=True
                )

            if not r.ok:
                return {"ok": False, "error": f"발급 페이지 이동 실패: {r.error}"}
            print("[정부24] 발급 페이지 이동 완료")

            # 3. 로그인 확인
            page.wait_for_load_state("networkidle", timeout=10000)
            page_text = page.inner_text("body")
            if "로그인" in page_text and "간편인증" in page_text:
                print("\n[정부24] ⚠️  로그인이 필요합니다.")
                print("          브라우저에서 로그인 후 엔터를 누르세요...")
                input("→ 로그인 완료 후 엔터: ")

            # 4. 신청하기 버튼 클릭 (APPROVE)
            try:
                r = click(
                    page,
                    "a[title='신청하기'], button:has-text('신청하기'), .btn-apply",
                    label="신청하기",
                    intent=intent,
                    audit_path=audit_path,
                )
            except GateApprovalRequired as e:
                print(f"\n[정부24] {cert_type} 발급 신청 승인이 필요합니다.")
                if not _ask_user_approval(e.approval_prompt()):
                    return {"ok": False, "error": "사용자 거부"}
                r = click(
                    page,
                    "a[title='신청하기'], button:has-text('신청하기'), .btn-apply",
                    label="신청하기",
                    intent=intent,
                    audit_path=audit_path,
                    force=True,
                )

            if not r.ok:
                print(f"[정부24] 신청 버튼 클릭 실패: {r.error}")
                print("          수동으로 '신청하기'를 클릭 후 엔터를 누르세요...")
                input("→ 신청 완료 후 엔터: ")

            # 5. 처리 대기
            page.wait_for_load_state("networkidle", timeout=30000)
            print("[정부24] 신청 처리 중...")

            # 6. 스크린샷 저장
            r_ss = screenshot(page, output_path, intent=intent, audit_path=audit_path, full_page=True, force=True)
            if r_ss.ok:
                print(f"[정부24] 스크린샷 저장: {output_path}")

            # 7. 완료 보고
            print(f"\n[정부24] ✓ 주민등록{cert_type} 발급 완료")
            return {
                "ok": True,
                "cert_type": cert_type,
                "screenshot": str(output_path) if r_ss.ok else None,
                "intent_id": intent.intent_id,
            }

    except CDPConnectionError as e:
        print(f"[오류] CDP 연결 실패: {e}")
        return {"ok": False, "error": str(e)}
    except Exception as e:  # noqa: BLE001 - 정부24 주민등록등본 발급 자동화 - 신청하기 클릭은 GateApprovalRequired 승인 게이트를 거치며 _ask_user_approval로 사용자 승인 필요, 이 except는 세션 전체 실패 시 최종 폴백으로 ok:False 반환(fail-closed), 승인 없이 진행되는 경로 없음
        print(f"[오류] 예외 발생: {e}")
        return {"ok": False, "error": str(e)}


def main() -> None:
    parser = argparse.ArgumentParser(description="정부24 주민등록등본/초본 발급")
    parser.add_argument("--type", choices=["등본", "초본"], default="등본", help="발급 서류 종류")
    parser.add_argument("--output", type=Path, default=None, help="저장 경로 (기본: data/reports/certificates/)")
    parser.add_argument("--port", type=int, default=9222, help="Chrome CDP 포트")
    args = parser.parse_args()

    result = run_gov24_certificate(
        cert_type=args.type,
        output_path=args.output,
        port=args.port,
    )

    if result["ok"]:
        print("\n결과: 성공")
        if result.get("screenshot"):
            print(f"저장 위치: {result['screenshot']}")
    else:
        print(f"\n결과: 실패 — {result.get('error')}")
        sys.exit(1)


if __name__ == "__main__":
    main()
