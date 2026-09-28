"""루씨에어 코타라 커넥트 CTC 실링팬 137cm — 스마트스토어 상품 등록 스크립트.

기존 scripts/_tmp_master.py(+_tmp_full_html.py, _tmp_html_consts2.py)를 대체한다
(2026-09-28 정리). 그 3개는 img/p/h/small_note 헬퍼와 상세페이지 HTML을 이 상품
전용으로 하드코딩했었는데, 그 로직 전체가 이미 있던
scripts/naver/smartstore/product/page_builder.py의 ProductPageBuilder와
중복 구현이었다(DUP-02). 비포/애프터 사진, 상담 흐름 안내, 타 판매처 가격
비교 3가지는 이 빌더에 없던 섹션이라 새로 추가했다 — 이제 다른 상품도 이
3개 섹션을 데이터만 바꿔 재사용할 수 있다.

사용법(카테고리 선택까지 끝난 스마트스토어 상품등록 탭이 CDP 9222에 이미
열려 있어야 함):
    python -m scripts.naver.smartstore.register_lucci_ctc_fan
"""

from __future__ import annotations

import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MEDIA_BASE_URL = "https://haehan-ai.kr/orchestrator/api/v1/public-media/"
UPLOAD_MAPPING_PATH = ROOT / "data" / "smartstore_drafts" / "_upload_mapping.json"
MAIN_IMAGE_PATH = ROOT / "data" / "smartstore_drafts" / "main_image_white.png"

CATEGORY_CHECK_TEXT = "천장형선풍기"
PRODUCT_NAME = "루씨에어 코타라 커넥트 CTC 실링팬 137cm 화이트 IoT BLDC 저소음 천장형선풍기 설치포함"
PRODUCT_PRICE = 649000
PRODUCT_STOCK = 20


def _media_url(media_map: dict, key: str) -> str:
    return MEDIA_BASE_URL + media_map[key]


def build_product_data(media_map: dict) -> dict:
    """ProductPageBuilder.render()에 넘길 상품 데이터. 다른 상품을 등록할 때는
    이 함수(또는 이런 모양의 dict)만 새로 만들면 된다 — 아래 main()의 나머지는
    그대로 재사용 가능."""

    def url(key: str) -> str:
        return _media_url(media_map, key)

    return {
        "name": PRODUCT_NAME,
        "price": PRODUCT_PRICE,
        "hero_image": {"url": url("hero"), "alt": "루씨에어 코타라 커넥트 CTC 137cm 화이트"},
        "before_after_title": "실링팬 하나로 공간은 얼마나 달라질까요?",
        "before_after_pairs": [
            {
                "before_url": url("before"),
                "before_alt": "실링팬 없는 거실",
                "before_caption": "WITHOUT CEILING FAN (예시 이미지 · 배치 시안)",
                "after_url": url("after"),
                "after_alt": "실링팬 설치된 거실",
                "after_caption": "WITH CEILING FAN (예시 이미지 · 배치 시안)",
            },
        ],
        "gallery_images": [
            {"url": url("g01"), "alt": "실링팬 설치 이미지"},
            {"url": url("g03"), "alt": "루씨에어 코타라 커넥트 CTC 정면"},
            {"url": url("g05"), "alt": "Lucci Connect 앱 IoT 제어"},
            {"url": url("g12"), "alt": "BLDC 모터"},
            {"url": url("g14"), "alt": "2년/4년 보증"},
            {"url": url("g16"), "alt": "TÜV Rheinland 소음 시험"},
        ],
        "specs": {
            "품명/모델명": "루씨에어 코타라 커넥트 CTC 실링팬 137cm<br>LucciAir Kotara Connect CTC 137cm BLDC Fan",
            "사이즈": "137 x 137 x 18.5 cm, 무게 4.5kg (적정 층고 2.3m 이상, 연장봉 결합 불가)",
            "모터": "BLDC, 최대 218㎥/min 공기순환",
            "정격전압 / 소비전력": "220V / 15.8W",
            "IoT": "Lucci Connect 전용 앱 제어 (전원·풍속·타이머)",
            "소음": "TÜV Rheinland 시험, 1단 운전 시 18.1dB",
            "KC 인증정보": "해당함 (전기용품 안전인증 대상)",
            "제조자(사) / 제조국": "루씨에어 / 메종드컨셉(주) · 중국산(메종드컨셉 명의 수입)",
            "색상": "3 Colors — 화이트 / 우드(내추럴) / 다크(에스프레소)",
            "품질보증": "제품 2년, 모터 4년",
        },
        "price_compare_title": "온라인 가격도 충분히 비교해 보세요",
        "price_compare_rows": [
            {"label": "비스로바 / 설치맨닷컴 / 루씨에어코리아 (제품만)", "price": "670,000원"},
            {"label": "나드 라이프스타일 (제품만)", "price": "636,490원"},
            {"label": "반딧불 전파사 (제품+기본설치)", "price": "649,000원", "highlight": True},
        ],
        "notice_items": [
            "천장 구조 / 천장 높이 / 설치 위치 / 주변 조명 위치 / 팬 회전반경 / 기존 배선 상태를 확인합니다.",
            "천장 보강, 신규 배선·스위치 이동, 고소작업, 특수천장, 기존 제품 철거, 목공·도배 마감이 "
            "필요한 경우 추가비용이 발생할 수 있습니다.",
            "현장에서 갑자기 추가비용을 청구하지 않습니다 — 사전 고지 후 고객 확인을 받고 진행합니다.",
        ],
        "consult_title": "아직 어떤 실링팬을 골라야 할지 모르시겠다면",
        "consult_lead": "먼저 제품부터 구매하지 않으셔도 됩니다. 거실 사진 한 장을 보내주세요.",
        "consult_steps": ["공간 사진 전송", "공간에 맞는 실링팬 검토", "배치 시안 제작", "제품 선택", "설치 상담"],
        "consult_cta": "반딧불 전파사 상담 010-7387-6635",
    }


def build_detail_html(media_map: dict) -> str:
    from scripts.naver.smartstore.product.page_builder import ProductPageBuilder

    builder = ProductPageBuilder()
    builder.select(["hero", "before_after", "spec", "price_compare", "notice", "consult_flow"])
    return builder.render(build_product_data(media_map))


def main() -> None:
    from playwright.sync_api import sync_playwright

    from scripts.naver.smartstore.product.description_editor import SmartEditorSession
    from scripts.naver.smartstore.product.general_product import GeneralProductRegister

    media_map = json.loads(UPLOAD_MAPPING_PATH.read_text(encoding="utf-8"))
    detail_html = build_detail_html(media_map)

    with sync_playwright() as p_pw:
        browser = p_pw.chromium.connect_over_cdp("http://127.0.0.1:9222")
        ctx = browser.contexts[0]
        page = next(pg for pg in ctx.pages if "sell.smartstore.naver.com" in pg.url)

        # 카테고리는 이미 선택된 상태(이전 단계) — 검증만
        txt = page.evaluate("document.body.innerText")
        assert CATEGORY_CHECK_TEXT in txt, "카테고리 미선택 상태 — 중단"
        print("STEP category: OK (already selected)")

        reg = GeneralProductRegister(page)
        reg._opened = True
        r1 = reg.set_product_name(PRODUCT_NAME)
        print("STEP name:", r1)
        r2 = reg.set_price(PRODUCT_PRICE)
        print("STEP price:", r2)
        r3 = reg.set_stock(PRODUCT_STOCK)
        print("STEP stock:", r3)
        reg._dismiss_blocking_modals()
        time.sleep(1)
        r4 = reg.upload_main_image(str(MAIN_IMAGE_PATH))
        print("STEP main_image:", r4)
        assert all([r1["ok"], r2["ok"], r3["ok"], r4["ok"]]), "기본정보 입력 실패 — 중단"

        ed = SmartEditorSession(page)
        ok_open = ed.open()
        print("STEP editor_open:", ok_open, "| ed.page.url:", ed.page.url)
        assert ok_open, "에디터 진입 실패 — 중단"

        r5 = ed.block.insert_html(detail_html)
        print("STEP html_insert:", r5)
        assert r5["ok"], "HTML 삽입 실패 — 중단"

        time.sleep(1)
        btn_coords = ed.page.evaluate("""
            () => {
                const btn = document.querySelector('button.btn-primary.progress-button');
                if (!btn) return null;
                const r = btn.getBoundingClientRect();
                return {x: r.x + r.width/2, y: r.y + r.height/2};
            }
        """)
        print("STEP submit_btn_coords:", btn_coords)
        assert btn_coords, "등록 버튼 못 찾음 — 중단"

        ed.page.mouse.click(btn_coords["x"], btn_coords["y"])
        print("STEP submit_clicked")
        time.sleep(3)


if __name__ == "__main__":
    main()
