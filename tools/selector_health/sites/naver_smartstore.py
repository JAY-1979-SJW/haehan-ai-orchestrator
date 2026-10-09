"""네이버 스마트스토어 상품등록 폼 셀렉터 헬스체크 명세.

2026-08-15 실측으로 확인한 사실을 그대로 반영(전부 실제로 자동화를 깨뜨린 것들):
  - 대표이미지 영역에 `input[type=file]` 이 **없다**. `a.btn-add-img` 를 눌러
    '내 사진 불러오기' 모달을 띄워야 file input 이 생성된다.
    → 기존 upload_main_image() 가 set_input_files 타임아웃으로 사망했다.
  - 상세설명 '스마트 에디터 ONE' 버튼은 페이지 하단(y≈3358)에 있어
    스크롤 없이 뷰포트 좌표로 클릭하면 빗나간다.
    → 기존 _click_editor_btn() 이 항상 실패했다.
  - 에디터는 같은 탭이 아니라 **별도 탭(#/editor)** 으로 열린다.
    → 같은 페이지에서 에디터 요소를 찾으면 없다.

주의: 이 검사는 읽기 전용이다. 저장/임시저장/발행 버튼은 절대 클릭하지 않는다.
"""

from __future__ import annotations

import time
from typing import Any

from tools.selector_health.core import SelectorCheck, SiteSpec

CREATE_URL = "https://sell.smartstore.naver.com/#/products/create"


def _expand_all_sections(page: Any) -> int:
    """접힌 섹션을 모두 펼친다.

    ⚠ 이게 없으면 검사 결과가 실행마다 달라진다(2026-08-15 실제 발생).
    상품등록 폼은 원산지·검색설정·구매수량 등 상당수 섹션이 기본적으로 접혀 있고,
    접힌 섹션의 입력요소는 DOM 에 없어 멀쩡한 셀렉터가 '사망'으로 오탐된다.
    """
    total = 0
    for _ in range(2):  # 펼치면서 새로 생기는 토글까지 2회
        try:
            n = page.evaluate(
                """() => {
                    const tg = [...document.querySelectorAll('a')]
                        .filter(a => /메뉴토글/.test(a.innerText || ''));
                    let n = 0;
                    tg.forEach(a => {
                        if (!/active/.test(a.className || '')) {
                            try { a.click(); n++; } catch (e) {}
                        }
                    });
                    return n;
                }"""
            )
        except Exception:  # noqa: BLE001 - 셀렉터 헬스체크(사이트 구조 변경 감지 도구) — 실패는 그대로 False(셀렉터 비정상)로 판정, 이 도구의 목적 자체가 실패를 감지하는 것, 쓰기·결제 없음(2026-09-28 검토)
            break
        total += n or 0
        time.sleep(3.0)
        if not n:
            break
    return total


def _dismiss_popups(page: Any) -> None:
    """진입 시 뜨는 공지/임시저장 복원 팝업 닫기 + 접힌 섹션 펼치기.

    상품등록 페이지는 '임시저장 된 내용(N건)을 불러오시겠습니까?' 및 공지 레이어가
    떠서 이후 클릭을 가로챈다. 불러오기는 누르지 않고 닫기만 한다.
    """
    for _ in range(5):
        closed = False
        for sel in (
            '[class*="modal"] button[class*="close"]',
            '[class*="modal"] a[class*="close"]',
            'button:has-text("닫기")',
            'button:has-text("확인")',
        ):
            try:
                el = page.locator(sel).first
                if el.is_visible(timeout=900):
                    el.click(timeout=2000)
                    time.sleep(0.7)
                    closed = True
                    break
            except Exception:  # noqa: BLE001 - 셀렉터 헬스체크(사이트 구조 변경 감지 도구) — 실패는 그대로 False(셀렉터 비정상)로 판정, 이 도구의 목적 자체가 실패를 감지하는 것, 쓰기·결제 없음(2026-09-28 검토)
                continue
        if not closed:
            break

    # 팝업을 닫은 뒤 섹션을 펼쳐야 접힌 곳의 셀렉터가 검사 대상이 된다
    _expand_all_sections(page)


def _enable_tag_direct_input(page: Any) -> bool:
    """'태그 직접 입력' 체크박스를 켠다 — 태그 위젯은 ng-if 로 이때만 생성된다."""
    try:
        cb = page.locator('input[ng-model="vm.viewData.isDirectInput"]').first
        if cb.count() == 0:
            return False
        if not cb.is_checked():
            page.evaluate("() => document.querySelector('input[ng-model=\"vm.viewData.isDirectInput\"]').click()")
            page.wait_for_timeout(1200)
        return bool(cb.is_checked())
    except Exception:  # noqa: BLE001 - 셀렉터 헬스체크(사이트 구조 변경 감지 도구) — 실패는 그대로 False(셀렉터 비정상)로 판정, 이 도구의 목적 자체가 실패를 감지하는 것, 쓰기·결제 없음(2026-09-28 검토)
        return False


def _open_image_modal(page: Any) -> bool:
    """'내 사진 불러오기' 모달 열기 — file input 은 이 모달 안에만 생성된다.

    주의(2026-08-15 실측): 첫 번째 a.btn-add-img 를 눌러도 안 열릴 수 있다.
    **이미 이미지가 채워진 슬롯**은 모달을 띄우지 않기 때문이다.
    (대표이미지가 등록된 상태에서 nth(0) 무반응 / nth(1) 정상 확인)
    → 빈 슬롯을 만날 때까지 순회한다.
    """

    def _has_input() -> bool:
        try:
            return page.locator("input[type=file]").count() > 0
        except Exception:  # noqa: BLE001 - 셀렉터 헬스체크(사이트 구조 변경 감지 도구) — 실패는 그대로 False(셀렉터 비정상)로 판정, 이 도구의 목적 자체가 실패를 감지하는 것, 쓰기·결제 없음(2026-09-28 검토)
            return False

    if _has_input():
        return True

    try:
        n = page.locator("a.btn-add-img").count()
    except Exception:  # noqa: BLE001 - 셀렉터 헬스체크(사이트 구조 변경 감지 도구) — 실패는 그대로 False(셀렉터 비정상)로 판정, 이 도구의 목적 자체가 실패를 감지하는 것, 쓰기·결제 없음(2026-09-28 검토)
        return False

    for i in range(min(n, 5)):
        try:
            btn = page.locator("a.btn-add-img").nth(i)
            btn.scroll_into_view_if_needed(timeout=3000)
            time.sleep(0.4)
            btn.click(timeout=4000)
        except Exception:  # noqa: BLE001 - 셀렉터 헬스체크(사이트 구조 변경 감지 도구) — 실패는 그대로 False(셀렉터 비정상)로 판정, 이 도구의 목적 자체가 실패를 감지하는 것, 쓰기·결제 없음(2026-09-28 검토)
            continue
        time.sleep(2.0)
        if _has_input():
            return True
    return False


def _dismiss_confirm_modal(page):
    for _ in range(3):
        try:
            b = page.locator('button:has-text("확인")').first
            if b.is_visible(timeout=800):
                b.click(timeout=2000)
                time.sleep(0.8)
            else:
                break
        except Exception:  # noqa: BLE001 - 셀렉터 헬스체크(사이트 구조 변경 감지 도구) — 실패는 그대로 False(셀렉터 비정상)로 판정, 이 도구의 목적 자체가 실패를 감지하는 것, 쓰기·결제 없음(2026-09-28 검토)
            break


def _select_any_category(page: Any) -> bool:
    """카테고리를 하나 선택한다 — 경로 표시(info-result)는 선택 후에만 나타난다.

    읽기 전용 검사이지만 이 요소만은 상태를 만들어야 확인할 수 있다.
    저장은 하지 않으므로 실제 상품에는 영향이 없다.
    """
    try:
        if page.locator(".info-result.text-info").count() > 0:
            return True
    except Exception:  # noqa: BLE001 - 여러 방법을 순차 시도하는 진단 로직 — 하나 실패해도 다음 확인으로 계속(2026-09-28 검토)
        pass
    try:
        sel = 'input[placeholder*="카테고리"]:not([type="radio"]):not([type="checkbox"])'
        el = page.locator(sel).first
        el.scroll_into_view_if_needed(timeout=4000)
        time.sleep(0.4)
        el.click(timeout=4000)
        el.fill("인테리어조명", timeout=4000, force=True)
        page.evaluate(
            """(sel) => { const e = document.querySelector(sel);
                 if (e) { e.dispatchEvent(new Event('input', {bubbles:true}));
                          e.dispatchEvent(new Event('focus', {bubbles:true})); } }""",
            sel,
        )
        time.sleep(3.0)
        opts = page.locator(".selectize-dropdown .option")
        for i in range(min(opts.count(), 20)):
            o = opts.nth(i)
            if not o.is_visible(timeout=400):
                continue
            t = (o.inner_text(timeout=400) or "").strip()
            if ">" in t and t.rsplit(">", 1)[-1].strip() == "인테리어조명":
                o.click(timeout=3000)
                time.sleep(2.0)
                break
    except Exception:  # noqa: BLE001 - 셀렉터 헬스체크(사이트 구조 변경 감지 도구) — 실패는 그대로 False(셀렉터 비정상)로 판정, 이 도구의 목적 자체가 실패를 감지하는 것, 쓰기·결제 없음(2026-09-28 검토)
        return False
    # KC인증 모달 닫기
    _dismiss_confirm_modal(page)
    try:
        return page.locator(".info-result.text-info").count() > 0
    except Exception:  # noqa: BLE001 - 셀렉터 헬스체크(사이트 구조 변경 감지 도구) — 실패는 그대로 False(셀렉터 비정상)로 판정, 이 도구의 목적 자체가 실패를 감지하는 것, 쓰기·결제 없음(2026-09-28 검토)
        return False


def _enter_default_mode(page: Any) -> bool:
    """상세설명 '직접 작성'(기본) 모드로 되돌린다.

    'HTML 작성' 모드와 배타적이라, HTML 모드에서는 스마트에디터 버튼과
    카테고리 안내(info-result)가 DOM 에서 사라진다(2026-08-15 실측).
    검사 순서에 따라 상태가 오염되므로 명시적으로 기본 모드를 만든다.
    """
    try:
        el = page.locator('a:has-text("직접 작성")').first
        el.scroll_into_view_if_needed(timeout=4000)
        time.sleep(0.4)
        el.click(timeout=4000)
        time.sleep(2.0)
    except Exception:  # noqa: BLE001 - 여러 방법을 순차 시도하는 진단 로직 — 하나 실패해도 다음 확인으로 계속(2026-09-28 검토)
        pass
    try:
        return page.locator('button:has-text("스마트 에디터 ONE")').count() > 0
    except Exception:  # noqa: BLE001 - 셀렉터 헬스체크(사이트 구조 변경 감지 도구) — 실패는 그대로 False(셀렉터 비정상)로 판정, 이 도구의 목적 자체가 실패를 감지하는 것, 쓰기·결제 없음(2026-09-28 검토)
        return False


def _enter_html_mode(page: Any) -> bool:
    """상세설명 'HTML 작성' 모드 진입 — 본문 textarea 는 이 모드에서만 나타난다.

    2026-08-15 실측: 기본 화면에는 상세설명 입력창이 없고, 스마트에디터는 별도 탭이라
    폼에서 텍스트를 넣으려면 이 모드가 유일한 경로다.
    """
    try:
        if page.locator('textarea[ng-model="vm.editorContent"]').count() > 0:
            return True
    except Exception:  # noqa: BLE001 - 여러 방법을 순차 시도하는 진단 로직 — 하나 실패해도 다음 확인으로 계속(2026-09-28 검토)
        pass
    try:
        el = page.locator('a:has-text("HTML 작성")').first
        el.scroll_into_view_if_needed(timeout=4000)
        time.sleep(0.5)
        el.click(timeout=5000)
    except Exception:  # noqa: BLE001 - 셀렉터 헬스체크(사이트 구조 변경 감지 도구) — 실패는 그대로 False(셀렉터 비정상)로 판정, 이 도구의 목적 자체가 실패를 감지하는 것, 쓰기·결제 없음(2026-09-28 검토)
        return False
    time.sleep(2.5)
    try:
        return page.locator('textarea[ng-model="vm.editorContent"]').count() > 0
    except Exception:  # noqa: BLE001 - 셀렉터 헬스체크(사이트 구조 변경 감지 도구) — 실패는 그대로 False(셀렉터 비정상)로 판정, 이 도구의 목적 자체가 실패를 감지하는 것, 쓰기·결제 없음(2026-09-28 검토)
        return False


CHECKS = [
    # ── 기본 입력 필드 ──
    SelectorCheck("PRODUCT_NAME", 'input[name="product.name"]', note="상품명. 죽으면 set_product_name 실패"),
    SelectorCheck("SALE_PRICE", 'input[name="product.salePrice"]', note="판매가. 필수값이라 죽으면 등록 자체 불가"),
    SelectorCheck("STOCK_QTY", 'input[name="product.stockQuantity"]', note="재고수량"),
    SelectorCheck(
        "CATEGORY_INPUT",
        'input[placeholder*="카테고리"]',
        note="카테고리 검색창. 자동완성 첫 항목을 무조건 고르지 말 것",
    ),
    # ── 이미지 (모달 방식) ──
    SelectorCheck("IMAGE_ADD_BTN", "a.btn-add-img", note="대표/추가이미지 등록 버튼. 이걸 눌러야 모달이 열린다"),
    SelectorCheck(
        "IMAGE_FILE_INPUT",
        "input[type=file]",
        requires="image_modal",
        expect="present",
        note="폼에는 없고 '내 사진 불러오기' 모달 안에만 존재(2026-08-15). "
        "multiple 지원 → 여러 장 한 번에 set_input_files 가능",
    ),
    # ── 상세설명 ──
    # ⚠ 'HTML 작성' 모드로 전환하면 이 버튼이 DOM 에서 사라진다(모드 배타).
    #   그래서 html_mode 선행조건이 걸린 검사들보다 **앞에** 두어 기본 모드에서 검사한다.
    #   (core 가 선행조건 없는 검사를 먼저 실행하므로 순서상 안전)
    SelectorCheck(
        "SMART_EDITOR_BTN",
        'button:has-text("스마트 에디터 ONE")',
        requires="default_mode",
        expect="present",
        note="페이지 하단에 있음. 스크롤 없이 좌표 클릭하면 빗나감. "
        "클릭 시 별도 탭(#/editor)으로 열린다. "
        "'HTML 작성' 모드에서는 사라지므로 기본 모드에서만 검사 가능",
    ),
    # ── 저장 (존재만 확인, 클릭 금지) ──
    SelectorCheck("TEMP_SAVE_BTN", 'button:has-text("임시저장")', note="가격 없이 저장할 때 사용하는 버튼"),
    # ── 2026-08-15 실측으로 갱신한 셀렉터들 ──
    # 구버전 셀렉터 75개 중 23개가 죽어 있었고, 아래는 새로 측정해 살려낸 것들이다.
    # 다시 드리프트하면 해당 기능이 조용히 죽으므로 주간 감시 대상에 포함한다.
    SelectorCheck(
        "CATEGORY_PATH_DISPLAY",
        ".info-result.text-info",
        requires="category_selected",
        expect="present",
        note="선택한 카테고리 경로 표시. **카테고리를 고른 뒤에만 나타난다**. "
        "구 .category-path 는 사망. selectize-input .item 은 페이지 전역 "
        "오탐(15개, '수취인명')이라 쓰면 안 됨",
    ),
    SelectorCheck(
        "CATEGORY_SELECTIZE_INSTANCE",
        "input.selectized",
        expect="present",
        note="Selectize 위젯 인스턴스가 붙는 요소. setValue() 폴백의 근거",
    ),
    # ⚠ 거짓 통과였던 항목 (2026-08-15 재실측)
    #   'SEARCH_TAG_INPUT' = input[ng-model="vm.searchKeyword"] 는 **존재는 하지만**
    #   태그 입력이 아니라 브랜드/제조사 자동완성(maxItems=1)이다.
    #   존재 검사만으로는 '맞는 요소인지'를 알 수 없어 OK 로 보고됐고,
    #   그 오해로 태그 자동화가 다섯 번 실패했다.
    #   → 실제 태그 위젯으로 교체한다.
    SelectorCheck(
        "SEARCH_TAG_DIRECT_CHECKBOX",
        'input[ng-model="vm.viewData.isDirectInput"]',
        expect="present",
        note="'태그 직접 입력' 체크박스. 이걸 켜야 태그 위젯이 ng-if 로 생성된다",
    ),
    SelectorCheck(
        "SEARCH_TAG_WIDGET",
        'select[config="::vm.config.directInputSelectizeConfig"]',
        expect="present",
        requires="tag_direct_input",
        note="태그 위젯 본체. settings.create 가 검증 함수라 addItem() 은 무효",
    ),
    SelectorCheck(
        "SEO_PAGE_TITLE",
        'input[ng-model="vm.product.detailAttribute.seoInfo.pageTitle"]',
        expect="present",
        note="SEO 페이지 타이틀",
    ),
    SelectorCheck(
        "ORIGIN_AREA_TYPE",
        'select[ng-model="vm.viewData.originAreaInfo.originAreaExposureType"]',
        expect="present",
        note="원산지. input 이 아니라 3단 SELECT 구조로 바뀌었음",
    ),
    SelectorCheck(
        "OPTION_GROUP_NAME",
        'input[ng-model="choiceOptionInput.groupName"]',
        expect="present",
        note="옵션명(예: 길이). 구 OPTION_TABLE/OPTION_SINGLE_TYPE 등은 전부 사망",
    ),
    SelectorCheck(
        "OPTION_VALUE_NAME",
        'input[ng-model="choiceOptionInput.name"]',
        expect="present",
        note="옵션값(예: 1200mm)",
    ),
    SelectorCheck(
        "PURCHASE_MIN_QTY",
        'input[ng-model="vm.product.detailAttribute.purchaseQuantityInfo.minPurchaseQuantity"]',
        expect="present",
        note="최소구매수량. ng-model 경로가 detailAttribute 아래로 깊어졌음",
    ),
    SelectorCheck(
        "TAX_TYPE_RADIO",
        'input[ng-model="vm.product.detailAttribute.taxType"]',
        expect="present",
        note="부가세 구분 라디오",
    ),
    SelectorCheck(
        "DESCRIPTION_MODE_HTML",
        'a:has-text("HTML 작성")',
        note="상세설명 HTML 모드 전환. 이걸 켜야 텍스트 입력창이 나타난다",
    ),
    SelectorCheck(
        "DESCRIPTION_TEXT",
        'textarea[ng-model="vm.editorContent"]',
        requires="html_mode",
        expect="present",
        note="상세설명 본문(SEO 텍스트). 이미지 속 글자는 검색에 안 잡히므로 필수. 'HTML 작성' 모드에서만 나타남",
    ),
]

SPEC = SiteSpec(
    key="naver_smartstore",
    title="스마트스토어 상품등록 폼",
    url=CREATE_URL,
    checks=CHECKS,
    preconditions={
        "image_modal": _open_image_modal,
        "html_mode": _enter_html_mode,
        "default_mode": _enter_default_mode,
        "category_selected": _select_any_category,
        "tag_direct_input": _enable_tag_direct_input,
    },
    setup=_dismiss_popups,
    settle_s=7.0,
)
