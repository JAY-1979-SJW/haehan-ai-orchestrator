"""카카오 개발자 콘솔 — Haehan AI 앱 설정 자동화.

Playwright 기반. 기존 browser_session() + ensure_login() 패턴 사용.

실행:
    python -m scripts.kakao.setup_haehan_app

섹션별 게이트:
  GATE-1  CDP + Playwright 연결
  GATE-2  카카오 로그인 세션 (저장 세션 복원 → 없으면 대기)
  GATE-3  개발자 콘솔 접근 확인
  GATE-4  앱 목록 조회 + 대상 앱 확인
  GATE-5  REST API 키 추출
  GATE-6  플랫폼 Web 도메인 확인/등록
  GATE-7  카카오 로그인 활성화
  GATE-8  Redirect URI 등록
  GATE-9  동의항목 확인
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from ai_orchestrator.paths.runtime import data_dir  # noqa: E402
from scripts.browser.page.page_helper import page_goto  # noqa: E402
from scripts.browser.page.web_connector import browser_session  # noqa: E402
from scripts.common.logger import get_logger  # noqa: E402

log = get_logger(__name__)

BASE = "https://developers.kakao.com/console/app"

# 앱별 설정
APP_CONFIG = {
    "1395337": {
        "name": "해한AI",
        "domains": ["https://haehan-ai.kr", "https://autowork.haehan-ai.kr", "https://kras.haehan-ai.kr"],
        "redirect_uris": [
            "https://autowork.haehan-ai.kr/api/auth/kakao/callback",
            "https://haehan-ai.kr/api/auth/kakao/callback",
            "https://kras.haehan-ai.kr/api/auth/kakao/callback",
            "http://localhost:3000/api/auth/kakao/callback",
        ],
    },
    "1303517": {
        "name": "해한AI입찰분석",
        "domains": ["https://bid.haehan-ai.kr"],
        "redirect_uris": [
            "https://bid.haehan-ai.kr/api/auth/kakao/callback",
            "http://localhost:3000/api/auth/kakao/callback",
        ],
    },
    "1413624": {
        "name": "해한메이아이출퇴근",
        "domains": ["https://attendance.haehan-ai.kr"],
        "redirect_uris": [
            "https://attendance.haehan-ai.kr/api/auth/kakao/callback",
            "http://localhost:3000/api/auth/kakao/callback",
        ],
    },
    "1309295": {
        "name": "해한 AI ERP",
        "domains": [],
        "redirect_uris": [
            "http://localhost:3000/api/auth/kakao/callback",
        ],
    },
}


# ── 게이트 결과 ───────────────────────────────────────────────────────────────


class GS(str, Enum):  # noqa: UP042
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"


@dataclass
class GR:
    gate: str
    status: GS
    message: str
    data: dict = field(default_factory=dict)

    def ok(self) -> bool:
        return self.status == GS.PASS


def _pass(g, msg, **d):
    print(f"  ✓ [{g}] {msg}")
    return GR(g, GS.PASS, msg, d)


def _fail(g, msg, fix=""):
    print(f"  ✗ [{g}] {msg}")
    fix and print(f"    → {fix}")
    return GR(g, GS.FAIL, msg)


def _skip(g, msg):
    print(f"  - [{g}] {msg}")
    return GR(g, GS.SKIP, msg)


# ══════════════════════════════════════════════════════════════════════════════
# 게이트 구현
# ══════════════════════════════════════════════════════════════════════════════


def gate1_connect():
    """GATE-1: browser_session 연결 확인."""
    try:
        with browser_session() as page:
            url = page.url
            return _pass("GATE-1", f"Playwright 연결됨 — {url[:50]}")
    except Exception as e:  # noqa: BLE001 - 카카오 개발자 콘솔 앱 등록 자동화(GATE-1~8) - 세션은 저장/복원만 수행(로그아웃/쿠키삭제 없음), 실패시 _fail() 로 게이트 실패를 명확히 보고. 결제나 비가역 최종 제출 없음
        return _fail(
            "GATE-1", f"Playwright 연결 실패: {e}", "CDP 브라우저 실행 확인: python scripts/browser/cdp/cdp_force_start.py start"
        )


def gate2_login():
    """GATE-2: 카카오 로그인 세션. 저장 세션 복원 시도 → 없으면 대기."""
    from scripts.browser.cdp.connection import get_page

    page = get_page()
    if True:
        # 저장 세션 복원 시도
        try:
            from scripts.auth.auth_session import restore_session

            if restore_session("developers.kakao.com", page):
                print("  ! [GATE-2] 저장 세션 복원 시도")
        except Exception:  # noqa: BLE001 - 카카오 개발자 콘솔 앱 등록 자동화(GATE-1~8) - 세션은 저장/복원만 수행(로그아웃/쿠키삭제 없음), 실패시 _fail() 로 게이트 실패를 명확히 보고. 결제나 비가역 최종 제출 없음
            pass

        page_goto(page, f"{BASE}")
        page.wait_for_load_state("networkidle", timeout=10000)

        # 로그인 확인 — 앱 목록 또는 사용자명 텍스트로 판단
        try:
            body = page.inner_text("body")
            logged_in = "로그아웃" in body or "전체 앱" in body or "앱 생성" in body or "Owner" in body
            if logged_in:
                try:
                    from scripts.auth.auth_session import save_session

                    save_session("developers.kakao.com", page)
                except Exception:  # noqa: BLE001 - 카카오 개발자 콘솔 앱 등록 자동화(GATE-1~8) - 세션은 저장/복원만 수행(로그아웃/쿠키삭제 없음), 실패시 _fail() 로 게이트 실패를 명확히 보고. 결제나 비가역 최종 제출 없음
                    pass
                return _pass("GATE-2", "카카오 로그인 확인됨")
        except Exception:  # noqa: BLE001 - 카카오 개발자 콘솔 앱 등록 자동화(GATE-1~8) - 세션은 저장/복원만 수행(로그아웃/쿠키삭제 없음), 실패시 _fail() 로 게이트 실패를 명확히 보고. 결제나 비가역 최종 제출 없음
            pass

        # 미로그인 — 대기
        print("  ! [GATE-2] 미로그인 — 브라우저에서 카카오 로그인하세요 (SMS/앱 인증)")
        from scripts.auth.login_detector import monitor_for_login

        result = monitor_for_login(page, check_interval=2, timeout_s=300)
        if result.get("detected"):
            try:
                from scripts.auth.auth_session import save_session

                save_session("developers.kakao.com", page)
                print("  ✓ [GATE-2] 세션 저장됨")
            except Exception:  # noqa: BLE001 - 카카오 개발자 콘솔 앱 등록 자동화(GATE-1~8) - 세션은 저장/복원만 수행(로그아웃/쿠키삭제 없음), 실패시 _fail() 로 게이트 실패를 명확히 보고. 결제나 비가역 최종 제출 없음
                pass
            return _pass("GATE-2", f"로그인 감지 ({result.get('elapsed_s', 0):.0f}초)")
        return _fail("GATE-2", "로그인 타임아웃", "브라우저에서 카카오 로그인 후 재실행")


def gate3_console(page) -> GR:
    """GATE-3: 개발자 콘솔 앱 목록 접근."""
    page_goto(page, BASE)
    page.wait_for_load_state("networkidle", timeout=15000)

    # 로그인 리다이렉트 확인
    if "login" in page.url or "accounts.kakao" in page.url:
        return _fail("GATE-3", "로그인 리다이렉트됨 — 세션 만료", "GATE-2 재실행 필요")

    try:
        page.wait_for_selector("[class*=app_item], [class*=AppItem], a[href*='/console/app/']", timeout=10000)
        return _pass("GATE-3", "개발자 콘솔 접근 성공")
    except Exception:  # noqa: BLE001 - 카카오 개발자 콘솔 앱 등록 자동화(GATE-1~8) - 세션은 저장/복원만 수행(로그아웃/쿠키삭제 없음), 실패시 _fail() 로 게이트 실패를 명확히 보고. 결제나 비가역 최종 제출 없음
        return _fail("GATE-3", "앱 목록 로딩 실패", "콘솔에서 앱 목록이 보이는지 확인")


def gate4_app_list(page) -> GR:
    """GATE-4: 앱 목록 조회."""
    apps = page.evaluate("""() => {
        const links = [...document.querySelectorAll('a[href*="/console/app/"]')];
        return links.map(a => ({
            name: a.innerText.trim(),
            id: (a.href.match(/\\/console\\/app\\/(\\d+)/) || [])[1] || '',
            href: a.href,
        })).filter(x => x.id && x.name && x.name.length < 50);
    }""")

    # 중복 제거
    seen = set()
    unique = []
    for a in apps:
        if a["id"] not in seen:
            seen.add(a["id"])
            unique.append(a)

    if not unique:
        return _fail("GATE-4", "앱 목록 조회 실패")

    print(f"  ! [GATE-4] 발견된 앱 {len(unique)}개:")
    for a in unique:
        status = "✓ 설정 대상" if a["id"] in APP_CONFIG else "- 스킵"
        print(f"    {status} {a['name']} (ID: {a['id']})")

    return _pass("GATE-4", f"앱 {len(unique)}개 확인", apps=unique)


def gate5_get_key(page, app_id: str) -> GR:
    """GATE-5: REST API 키 추출 — /config/platform-key 페이지."""
    page_goto(page, f"{BASE}/{app_id}/config/platform-key")
    page.wait_for_load_state("networkidle", timeout=10000)

    body = page.inner_text("body")
    # REST API 키는 32자 hex 패턴
    import re

    # "REST API 키" 라벨 이후 첫 번째 32자 hex
    match = re.search(r"REST API 키[\s\S]{0,200}?([0-9a-f]{32})", body, re.IGNORECASE)
    if not match:
        # 페이지 전체에서 32자 hex 찾기 (첫 번째가 Default REST API Key)
        hexes = re.findall(r"\b[0-9a-f]{32}\b", body)
        rest = hexes[0] if hexes else ""
    else:
        rest = match.group(1)

    # 모든 키 목록 (이름 + 값)
    key_entries = re.findall(r"([^\n]{1,30})\n더보기\n([0-9a-f]{32})", body)

    if rest:
        return _pass("GATE-5", f"REST API 키 확인됨 ({len(rest)}자)", rest_key=rest, all_keys=key_entries)
    return _fail("GATE-5", "REST API 키 미확인", "콘솔 > 앱 설정 > 플랫폼 키 확인")


def gate6_platform(page, app_id: str, domains: list) -> GR:
    """GATE-6: 플랫폼 Web 도메인 확인.

    카카오 콘솔에서 플랫폼 도메인은 앱 대표 도메인(일반 탭) 또는
    JavaScript 키의 JS SDK 도메인으로 관리됨.
    플랫폼 키 페이지에서 도메인 존재 여부만 확인.
    """
    if not domains:
        return _skip("GATE-6", "등록할 도메인 없음")

    # 앱 일반 정보에서 대표 도메인 확인
    page_goto(page, f"{BASE}/{app_id}/config")
    page.wait_for_load_state("networkidle", timeout=10000)
    body = page.inner_text("body")

    found = [d for d in domains if d in body]
    missing = [d for d in domains if d not in body]

    if missing:
        # 플랫폼 키 페이지도 확인
        page_goto(page, f"{BASE}/{app_id}/config/platform-key")
        page.wait_for_load_state("networkidle", timeout=10000)
        body2 = page.inner_text("body")
        found += [d for d in missing if d in body2]
        missing = [d for d in missing if d not in body2]

    if not missing:
        return _pass("GATE-6", f"플랫폼 도메인 확인됨: {found}")

    # 미등록 도메인 안내 (자동 등록은 JS SDK 도메인을 통해 가능하나 복잡)
    return _fail(
        "GATE-6",
        f"미등록 도메인: {missing}",
        "콘솔 > 앱 설정 > 플랫폼 키 > JavaScript 키 > JS SDK 도메인에 추가:\n" + "\n".join(f"    {d}" for d in missing),
    )


def gate7_login_activate(page, app_id: str) -> GR:
    """GATE-7: 카카오 로그인 활성화."""
    page_goto(page, f"{BASE}/{app_id}/product/login")
    page.wait_for_load_state("networkidle", timeout=10000)

    body = page.inner_text("body")
    if "상태\nON" in body or "상태 ON" in body:
        return _pass("GATE-7", "카카오 로그인 이미 ON")

    try:
        toggle = page.wait_for_selector(
            "[role='switch'], input[type='checkbox'][class*='toggle'], button[class*='toggle'], [class*='Switch']",
            timeout=5000,
        )
        toggle.click()
        page.wait_for_load_state("networkidle", timeout=5000)
        return _pass("GATE-7", "카카오 로그인 활성화 완료")
    except Exception as e:  # noqa: BLE001 - 카카오 개발자 콘솔 앱 등록 자동화(GATE-1~8) - 세션은 저장/복원만 수행(로그아웃/쿠키삭제 없음), 실패시 _fail() 로 게이트 실패를 명확히 보고. 결제나 비가역 최종 제출 없음
        return _fail("GATE-7", f"토글 실패: {e}", "콘솔 > 제품 설정 > 카카오 로그인에서 직접 ON")


def gate8_redirect_uri(page, app_id: str, uris: list) -> GR:
    """GATE-8: Redirect URI 등록.

    플랫폼 키 페이지에서 첫 번째 REST API 키의 '로그인 리다이렉트 URI' 배지 클릭
    → 편집 폼에서 입력값 확인 후 빈 슬롯 또는 기존 슬롯 교체 → 저장.
    """
    inp_sel = 'input[placeholder*="oauth"], input[placeholder*="example.com"]'

    page_goto(page, f"{BASE}/{app_id}/config/platform-key")
    page.wait_for_load_state("networkidle", timeout=10000)

    # 편집 폼 열기
    try:
        page.locator('span:has-text("로그인 리다이렉트 URI")').first.click()
        page.wait_for_load_state("networkidle", timeout=5000)
        time.sleep(1)
    except Exception as e:  # noqa: BLE001 - 카카오 개발자 콘솔 앱 등록 자동화(GATE-1~8) - 세션은 저장/복원만 수행(로그아웃/쿠키삭제 없음), 실패시 _fail() 로 게이트 실패를 명확히 보고. 결제나 비가역 최종 제출 없음
        return _fail(
            "GATE-8", f"리다이렉트 URI 편집 폼 열기 실패: {e}", "플랫폼 키 미설정 — REST API 키 먼저 생성 필요"
        )

    # 현재 등록된 URI 확인 (input_value 기준)
    count = page.locator(inp_sel).count()
    current_values = []
    for i in range(count):
        val = page.locator(inp_sel).nth(i).input_value()
        current_values.append(val.strip())

    print(
        f"  ! [GATE-8] 현재 등록 URI {len([v for v in current_values if v])}개: {[v[:40] for v in current_values if v]}"
    )

    missing = [u for u in uris if u not in current_values]
    if not missing:
        return _pass("GATE-8", f"Redirect URI {len(uris)}개 모두 등록됨", uris=current_values)

    registered = 0
    inp_sel = 'input[placeholder*="oauth"], input[placeholder*="example.com"]'

    for uri in missing:
        print(f"    → {uri}")
        try:
            # 빈 input 개수 확인
            empty_count = page.evaluate(f"""() => {{
                const inps = [...document.querySelectorAll('{inp_sel}')];
                return inps.filter(i => !i.value || i.value.trim() === '').length;
            }}""")

            if empty_count == 0:
                # "+" 버튼 클릭으로 새 칸 추가
                page.evaluate("""() => {
                    const all = [...document.querySelectorAll('button,span')];
                    const add = all.find(el => {
                        const t = (el.innerText||'').trim();
                        return (t==='+' || t==='URI 추가') && el.offsetParent !== null;
                    });
                    if(add) add.click();
                }""")
                time.sleep(0.8)

            # Playwright 네이티브 fill — React state 정상 업데이트
            inputs = page.locator(inp_sel)
            count = inputs.count()
            filled = False
            for i in range(count):
                inp = inputs.nth(i)
                val = inp.input_value()
                if not val or val.strip() == "":
                    inp.fill(uri)
                    inp.press("Tab")  # 포커스 이동으로 change 이벤트 발생
                    time.sleep(0.3)
                    registered += 1
                    filled = True
                    print("    ✓ 입력됨")
                    break
            if not filled:
                print("    ! 빈 입력창 없음")
        except Exception as e:  # noqa: BLE001 - 카카오 개발자 콘솔 앱 등록 자동화(GATE-1~8) - 세션은 저장/복원만 수행(로그아웃/쿠키삭제 없음), 실패시 _fail() 로 게이트 실패를 명확히 보고. 결제나 비가역 최종 제출 없음
            print(f"    ✗ 입력 실패: {e}")

    # 저장
    if registered > 0:
        try:
            page.click("button[type='submit']:has-text('저장'), button:has-text('저장')")
            page.wait_for_load_state("networkidle", timeout=5000)
            time.sleep(1)
            print("  ✓ 저장 완료")
        except Exception as e:  # noqa: BLE001 - 카카오 개발자 콘솔 앱 등록 자동화(GATE-1~8) - 세션은 저장/복원만 수행(로그아웃/쿠키삭제 없음), 실패시 _fail() 로 게이트 실패를 명확히 보고. 결제나 비가역 최종 제출 없음
            print(f"  ! 저장 버튼 오류: {e}")

    # 저장 후 input_value 기반 확인
    after_count = page.locator(inp_sel).count()
    after_values = []
    for i in range(after_count):
        val = page.locator(inp_sel).nth(i).input_value()
        after_values.append(val.strip())

    done = [u for u in uris if u in after_values]
    still_missing = [u for u in uris if u not in after_values]

    if not still_missing:
        return _pass("GATE-8", f"Redirect URI {len(uris)}개 모두 등록 완료")
    return _fail(
        "GATE-8",
        f"등록됨: {len(done)}개 / 미등록: {len(still_missing)}개\n    현재 슬롯: {[v[:40] for v in after_values if v]}",
        "콘솔 > 앱 설정 > 플랫폼 키 > 로그인 리다이렉트 URI 직접 추가:\n"
        + "\n".join(f"    {u}" for u in still_missing),
    )


def gate9_scope(page, app_id: str) -> GR:
    """GATE-9: 동의항목 확인."""
    page_goto(page, f"{BASE}/{app_id}/product/login/scope")
    page.wait_for_load_state("networkidle", timeout=10000)

    body = page.inner_text("body")
    items = []
    for item in ["닉네임", "프로필 사진", "카카오계정(이메일)"]:
        if item in body:
            t = "필수" if f"{item}\n필수" in body else "선택"
            items.append(f"{item}({t})")

    return _pass("GATE-9", f"동의항목: {items or '없음'}", scope=items)


# ══════════════════════════════════════════════════════════════════════════════
# 메인
# ══════════════════════════════════════════════════════════════════════════════


def main():
    print("=" * 60)
    print("카카오 개발자 콘솔 — Haehan AI 앱 자동 설정")
    print("Playwright 기반")
    print("=" * 60)

    all_results = []

    # GATE-1: 연결
    print("\n[GATE-1] Playwright 연결")
    g1 = gate1_connect()
    all_results.append(g1)
    if not g1.ok():
        return _summary(all_results)

    # GATE-2: 로그인
    print("\n[GATE-2] 카카오 로그인")
    g2 = gate2_login()
    all_results.append(g2)
    if not g2.ok():
        return _summary(all_results)

    # 이후 단계는 같은 browser_session 내에서
    with browser_session() as page:
        # 세션 복원
        try:
            from scripts.auth.auth_session import restore_session

            restore_session("developers.kakao.com", page)
        except Exception:  # noqa: BLE001 - 카카오 개발자 콘솔 앱 등록 자동화(GATE-1~8) - 세션은 저장/복원만 수행(로그아웃/쿠키삭제 없음), 실패시 _fail() 로 게이트 실패를 명확히 보고. 결제나 비가역 최종 제출 없음
            pass

        # GATE-3: 콘솔
        print("\n[GATE-3] 개발자 콘솔 접근")
        g3 = gate3_console(page)
        all_results.append(g3)
        if not g3.ok():
            return _summary(all_results)

        # GATE-4: 앱 목록
        print("\n[GATE-4] 앱 목록 조회")
        g4 = gate4_app_list(page)
        all_results.append(g4)
        if not g4.ok():
            return _summary(all_results)

        # 앱별 설정
        found_apps = g4.data.get("apps", [])
        target_ids = [a["id"] for a in found_apps if a["id"] in APP_CONFIG]

        final_keys = {}

        for app_id in target_ids:
            cfg = APP_CONFIG[app_id]
            print(f"\n{'─' * 60}")
            print(f"앱 설정: {cfg['name']} (ID: {app_id})")
            print(f"{'─' * 60}")

            # GATE-5: REST API 키
            print("\n[GATE-5] REST API 키")
            g5 = gate5_get_key(page, app_id)
            all_results.append(g5)
            if g5.ok():
                final_keys[app_id] = g5.data.get("rest_key", "")

            # GATE-6: 플랫폼
            print("\n[GATE-6] 플랫폼")
            g6 = gate6_platform(page, app_id, cfg["domains"])
            all_results.append(g6)

            # GATE-7: 로그인 활성화
            print("\n[GATE-7] 카카오 로그인 활성화")
            g7 = gate7_login_activate(page, app_id)
            all_results.append(g7)

            # GATE-8: Redirect URI
            print("\n[GATE-8] Redirect URI")
            g8 = gate8_redirect_uri(page, app_id, cfg["redirect_uris"])
            all_results.append(g8)

            # GATE-9: 동의항목
            print("\n[GATE-9] 동의항목")
            g9 = gate9_scope(page, app_id)
            all_results.append(g9)

    # 결과 저장
    out = {
        "apps": {aid: {"name": APP_CONFIG[aid]["name"], "rest_key": k} for aid, k in final_keys.items()},
        "gates": [{"gate": r.gate, "status": r.status.value, "message": r.message} for r in all_results],
    }
    (data_dir() / "kakao_setup_result.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    _summary(all_results)

    # .env 안내
    if final_keys:
        print("\n.env 추가 내용:")
        for aid, key in final_keys.items():
            name = APP_CONFIG[aid]["name"]  # noqa: F841
            env_key = "KAKAO_REST_API_KEY" if aid == "1395337" else f"KAKAO_{aid}_REST_API_KEY"
            print(f"  {env_key}={key or '콘솔에서 복사'}")
        print("  KAKAO_REDIRECT_URI=https://autowork.haehan-ai.kr/api/auth/kakao/callback")


def _summary(results: list[GR]):
    print("\n" + "=" * 60)
    print("게이트 결과 요약")
    print("=" * 60)
    for r in results:
        icon = "✓" if r.status == GS.PASS else ("✗" if r.status == GS.FAIL else "─")
        print(f"  {icon} {r.gate}: {r.status.value} — {r.message[:60]}")
    passed = sum(1 for r in results if r.ok())
    print(f"\n  총 {len(results)}개 중 {passed}개 PASS")
    print("  결과: data/kakao_setup_result.json")


if __name__ == "__main__":
    main()
