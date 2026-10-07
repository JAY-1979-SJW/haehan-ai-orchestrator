"""테스트: 기존 상품 정보 추출 → 자동 등록 입력 검증.

흐름:
  1. https://smartstore.naver.com/bigsun2024 접속
  2. 첫 번째 상품 정보 추출 (이름/가격/카테고리/이미지URL/설명)
  3. 추출 데이터로 ProductRegister 자동 입력 (★ 임시저장만, 발행 X)
  4. 어떤 셀렉터가 작동했는지/실패했는지 보고

목적: 셀렉터 검증 + 자동화 가능 범위 파악
"""

from __future__ import annotations

import contextlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from scripts.browser.cdp.connection import get_page  # noqa: E402
from scripts.browser.popup.popup_detector import handle_page_popups  # noqa: E402
from scripts.common.logger import get_logger  # noqa: E402
from scripts.naver.common.auth import ensure_naver_login  # noqa: E402

_log = get_logger(__name__)
STORE_URL = "https://smartstore.naver.com/bigsun2024"


def extract_first_product(page) -> dict:
    """스토어에서 첫번째 상품 정보 추출."""
    page.goto(STORE_URL, timeout=20000, wait_until="domcontentloaded")
    time.sleep(3)
    with contextlib.suppress(Exception):
        handle_page_popups(page, timeout_s=1.5)

    # 상품 목록 추출
    products = page.evaluate("""
    () => {
        const list = [];
        document.querySelectorAll('a[href*="/products/"]').forEach(a => {
            const href = a.href || '';
            const m = /\\/products\\/(\\d+)/.exec(href);
            if (!m) return;
            const title = a.querySelector('strong, .title, [class*="title"]')?.innerText?.trim() ||
                          (a.innerText || '').trim().substring(0, 60);
            const img = a.querySelector('img')?.src || '';
            const price = a.querySelector('[class*="price"]')?.innerText?.trim() || '';
            if (title) {
                list.push({id: m[1], title: title.substring(0, 80), img, price, url: href});
            }
        });
        // 중복 제거
        const seen = new Set();
        return list.filter(p => {
            if (seen.has(p.id)) return false;
            seen.add(p.id);
            return true;
        });
    }
    """)
    print(f"  스토어 상품 발견: {len(products)}개")
    if not products:
        return {}
    first = products[0]
    print(f"  첫번째: {first['title']}")
    print(f"  URL: {first['url']}")
    return first


def extract_product_detail(page, product_url: str) -> dict:
    """상품 상세 페이지에서 정보 추출 (셀렉터 다양화)."""
    page.goto(product_url, timeout=20000, wait_until="domcontentloaded")
    time.sleep(4)
    with contextlib.suppress(Exception):
        handle_page_popups(page, timeout_s=1.5)

    # 페이지 스크롤로 모든 컨텐츠 로드
    page.evaluate("window.scrollTo(0, 500)")
    time.sleep(1)
    page.evaluate("window.scrollTo(0, 0)")
    time.sleep(0.5)

    detail = page.evaluate("""
    () => {
        const result = {url: location.href, title: document.title};

        // 상품명 — 더 넓은 셀렉터
        const nameEl = document.querySelector(
            'h3._22kNQuEXmb, ._22kNQuEXmb, h3[class*="ProductDetail"], h3, h2[class*="title"], [class*="product_title"]'
        );
        result.name = nameEl?.innerText?.trim() || '';

        // 가격 — text 패턴
        const txt = document.body?.innerText || '';
        const priceMatch = /(\\d{1,3}(?:,\\d{3})+|\\d{3,})\\s*원/.exec(txt);
        result.price = priceMatch ? priceMatch[1].replace(/,/g, '') : '';

        // 카테고리 (브레드크럼)
        const crumbs = Array.from(document.querySelectorAll(
            '[class*="breadcrumb"] a, [class*="category-path"] a, [class*="Category"] a, nav a[href*="category"]'
        )).map(a => (a.innerText || '').trim()).filter(t => t && t.length < 20);
        result.category = [...new Set(crumbs)].join('>');

        // 이미지 (스마트스토어 상품 페이지)
        const imgs = new Set();
        document.querySelectorAll('img').forEach(img => {
            const src = img.src || '';
            if (src.includes('shop-phinf.pstatic.net') || src.includes('shopping-phinf')) {
                imgs.add(src);
            }
        });
        result.images = Array.from(imgs).slice(0, 5);

        // 속성 테이블
        result.attributes = {};
        document.querySelectorAll('table tr, dl').forEach(row => {
            const ths = row.querySelectorAll('th, td, dt, dd');
            if (ths.length >= 2) {
                const k = (ths[0].innerText || '').trim();
                const v = (ths[1].innerText || '').trim();
                if (k && v && k.length < 20 && v.length < 80) {
                    result.attributes[k] = v;
                }
            }
        });

        // 상세 설명 일부
        const detailEl = document.querySelector('[class*="detail_box"], #INTRODUCE, [class*="ProductDetail"]');
        result.description = (detailEl?.innerText || '').substring(0, 300);

        return result;
    }
    """)
    return detail


def _extract_detail_and_save(page, first):
    """2. 상세 정보 추출 + 결과 저장."""
    # 2. 상세 정보 추출
    print(f"\n  [2] 상품 상세 추출: {first['url']}")
    detail = extract_product_detail(page, first["url"])
    print(f"     이름: {detail.get('name', '')[:60]}")
    print(f"     가격: {detail.get('price', '')}")
    print(f"     카테고리: {detail.get('category', '')}")
    print(f"     이미지: {len(detail.get('images', []))}개")
    if detail.get("attributes"):
        print("     속성:")
        for k, v in list(detail["attributes"].items())[:10]:
            print(f"       {k}: {v}")

    # 결과 저장
    out = ROOT / "data" / "sample_product_data.json"
    out.write_text(json.dumps(detail, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  ✓ 저장: {out.name}")
    return detail


def _fill_register_form(page, first, detail) -> None:
    """3. 자동 등록 페이지로 데이터 입력 (저장 안 함)."""
    # 3. 자동 등록 입력 테스트
    print("\n  [3] 자동 등록 페이지로 데이터 입력 (★ 저장 안 함)")
    from scripts.naver.smartstore.product import ProductRegister

    pr = ProductRegister(page)

    if not pr.open():
        print("  ✗ 등록 페이지 열기 실패")
        return
    print("     ✓ 등록 페이지 진입")

    # 카테고리
    if detail.get("category"):
        cat = detail["category"].split(">")[-1].strip()
        if cat:
            r = pr.set_category(cat)
            mark = "✓" if r.get("ok") else "✗"
            print(f"     [{mark}] 카테고리 '{cat}': {r}")
    else:
        # 카테고리 없으면 임의 카테고리로 테스트
        r = pr.set_category("디지털/가전")
        mark = "✓" if r.get("ok") else "✗"
        print(f"     [{mark}] 카테고리 '디지털/가전' (기본): {r}")

    # 상품명
    name = (detail.get("name") or first.get("title") or "Test Product").strip()
    if name:
        test_name = f"[자동입력테스트] {name[:50]}"
        r = pr.set_product_name(test_name)
        mark = "✓" if r.get("ok") else "✗"
        print(f"     [{mark}] 상품명: {r.get('ok')}")

    # 모델명
    model = detail.get("attributes", {}).get("모델명") or detail.get("attributes", {}).get("모델") or "TEST-MODEL-001"
    r = pr.set_model_name(model)
    mark = "✓" if r.get("ok") else "✗"
    print(f"     [{mark}] 모델명 '{model}': {r.get('ok')}")

    # 사은품
    r = pr.set_gift("[테스트] 무료 사은품 증정")
    mark = "✓" if r.get("ok") else "✗"
    print(f"     [{mark}] 사은품: {r.get('ok')}")

    # 이벤트 문구
    r = pr.set_event_text("[테스트] 20만원 이상 12개월 무이자 할부")
    mark = "✓" if r.get("ok") else "✗"
    print(f"     [{mark}] 이벤트 문구: {r.get('ok')}")

    # KC 인증 (선택)
    r = pr.set_kc_exemption("구매대행")
    mark = "✓" if r.get("ok") else "✗"
    print(f"     [{mark}] KC 인증 면제 '구매대행': {r.get('ok')}")

    print("\n  [4] 입력 완료 (★ 저장 안 함, 사용자 확인 후 수동 저장 가능)")
    print("     브라우저에서 입력 결과 확인 가능")
    print("     성공한 셀렉터들이 검증되었습니다.")


def main():
    page = get_page()
    print(f"\n{'=' * 70}")
    print("  기존 상품 정보 추출 → 자동 등록 입력 테스트")
    print(f"{'=' * 70}\n")

    # 로그인 확인
    r = ensure_naver_login(page)
    if not r.get("ok"):
        print("  ✗ 로그인 실패")
        return

    # 1. 스토어에서 첫 상품 추출
    print("  [1] 스토어 접속 + 상품 목록 추출")
    first = extract_first_product(page)
    if not first:
        print("  ✗ 상품 없음")
        return

    detail = _extract_detail_and_save(page, first)

    _fill_register_form(page, first, detail)


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001 - 스마트스토어 상품등록 필드 테스트 스크립트(읽기전용 분석, 저장 버튼 클릭까지만 확인하고 실제 제출 안 함) — 팝업처리 실패 무시, 필드추출 실패는 에러로 기록
        import traceback

        traceback.print_exc()
        sys.exit(1)
