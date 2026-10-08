"""스마트스토어 그룹상품 등록 자동화 (raw CDP 기반, L5 Site Module).

`GeneralProductRegister`(scripts/naver/smartstore/product/general_product.py)와
달리 그룹상품 등록 화면은 **AngularJS + selectize.js**로 만들어져 있다
(일반 상품등록은 React 계열 — 같은 스마트스토어센터 안에서도 화면마다 프레임워크가
다르다, 2026-08-23 실측). 판매옵션 입력창은 selectize가 만든 가짜 UI일 뿐이고
실제 값은 화면에 안 보이는 `<select multiple>`에 selectize 내부 API로만 반영된다.

**함정 (반드시 이 방식으로 채워야 함)**: `input.value` 네이티브 setter로 값만
주입하고 input/change 이벤트를 dispatch해도 화면엔 텍스트가 보이지만
"목록으로 적용" 버튼은 계속 disabled로 남는다(2026-08-23 다수 시행착오로 확정).
반드시:
  1. `$(select)[0].selectize.createItem(값)` 을 옵션값 하나하나에 대해 호출 —
     텍스트를 실제 "칩"으로 커밋시킨다.
  2. `angular.element(document.body).injector().get('$rootScope').$apply()` 로
     Angular digest를 강제 실행 — 이게 없으면 `ng-disabled` 바인딩이 안 갱신된다.
selectize의 `createItem()`은 자동 저장된 값(네이버 제공 옵션값)이면 그 값을,
없으면 "직접입력"으로 새 항목을 만든다(추천 옵션값 사용을 권장하는 안내 문구가
화면에 뜨지만 직접입력도 동작은 함).

2026-08-23 실사 확인 범위 — **이 파일이 구현하는 것**:
  1. 그룹상품 등록 화면 진입
  2. 카테고리 선택 (트리 탐색, 카테고리명검색 탭은 자동완성이 불안정해 미사용)
  3. 그룹상품명 입력
  4. 판매옵션 속성(색상/사이즈 등 카테고리마다 다름) 값 입력 — selectize API로
     확정, "판매옵션 목록 (총 N개)" 그리드가 실제 조합 수(색상×사이즈 등)로
     생성되는 것까지 라이브 검증 완료(3색상×3사이즈 → 9개)
  5. "목록으로 적용" — 옵션 조합을 그리드에 생성

**알려진 한계 — 카테고리 트리 리프 클릭이 불안정함(2026-08-23)**: 트리를
위→아래로 순서대로 클릭하는 방식(`select_category`)이 첫 성공 시엔 됐지만,
`open()`으로 페이지를 새로 고친 직후 반복 실행하면 리프 항목 클릭이 포커스만
줄 뿐 실제 선택으로 이어지지 않는 경우가 반복 관찰됐다. `el.click()`, 실제
좌표 `Input.dispatchMouseEvent`, 재시도 루프 전부 시도했지만 원인(Angular
ng-click 바인딩 타이밍? hover 상태 선행 필요?)을 못 찾았다. **호출 후 반드시
`select_category()`의 반환값 또는 그룹상품명 필드 렌더링 여부로 성공을
확인하고, 실패 시 별도 조사가 필요하다** — 이 상태로 그냥 다음 단계로
넘어가면 이후 모든 필드 입력이 조용히 실패한다(카테고리 미선택 시 아래
섹션 자체가 렌더링 안 됨).

**아직 구현 안 된 것** (다음 단계, 별도 기준서 필요):
  - 카테고리 트리 클릭 불안정성 원인 규명 (위 참고)
  - 판매옵션 목록 그리드의 재고/판매가/할인가 "일괄입력" — 그리드 행이
    옵션값 조합 수만큼 동적 생성되고 일괄입력 모달 구조를 아직 조사 안 함
  - 이미지 업로드, 배송정보, 상세설명 등 나머지 필수 섹션
  - "저장하기" 제출 — 위 항목들이 없어 실제 저장은 항상 실패한다

즉 이 클래스는 "카테고리+상품명+옵션속성 입력까지"만 자동화한다. 그 뒤는
사용자가 수동으로 이어서 완성하거나, 후속 개발로 채운다.

사용법:
    from scripts.browser.cdp.cdp_helper import CDP
    from scripts.naver.smartstore.group_product_register import GroupProductRegister

    cdp = CDP(port=9222)
    reg = GroupProductRegister(cdp)
    reg.open()
    reg.select_category(["가구/인테리어", "베개", "계절베개"])
    if not reg.is_category_applied():
        raise RuntimeError("카테고리 선택 실패 — 재시도 또는 원인 조사 필요")
    reg.set_group_name("여름 냉감 베개")
    reg.set_option_attribute(0, ["블랙", "화이트", "레드"])
    reg.set_option_attribute(1, ["40x40cm", "45x45cm", "50x50cm"])
    reg.apply_option_list()
    # 이후 그리드 가격/재고 입력, 저장은 미구현 — 수동으로 이어서 진행
"""

import json
import time

from scripts.browser.cdp.cdp_helper import CDP

CREATE_URL = "https://sell.smartstore.naver.com/#/products/standard-group-product/create"


class GroupProductRegister:
    """그룹상품 등록 자동화 (카테고리~옵션속성 입력까지, raw CDP)."""

    def __init__(self, cdp: CDP):
        self.cdp = cdp

    def open(self, wait: float = 3.0) -> str:
        """그룹상품 등록 화면으로 이동.

        hash만 바꾸면 Angular 앱이 재부팅되지 않아 이전에 입력했던 판매옵션
        상태가 남아 "카테고리를 변경하시겠습니까?" 확인 모달이 뜬다(2026-08-23
        실측). 항상 완전히 새로 고쳐서 진짜 빈 폼으로 시작한다.
        """
        self.cdp.js(f"location.hash = '{CREATE_URL.split('#')[1]}';")
        time.sleep(0.5)
        self.cdp.send("Page.reload", {"ignoreCache": True})
        time.sleep(wait)
        return self.cdp.js("location.href")

    def select_category(self, path: list[str], click_wait: float = 1.2) -> str:
        """카테고리 트리를 위→아래 순서로 클릭해 최종 카테고리를 선택한다.

        path 예: ["가구/인테리어", "베개", "계절베개"]. 동일 텍스트가 여러 열에
        겹칠 수 있으나(2026-08-23 실사에선 미발생), 필요시 열 순서를 보장하려면
        각 클릭 사이 대기시간을 늘린다.

        **호출 후 `is_category_applied()`로 반드시 성공 여부를 확인할 것** —
        위 모듈 docstring의 "알려진 한계" 참고, 클릭이 조용히 실패할 수 있다.
        """
        for label in path:
            js = f"""(function(){{
              var all = Array.from(document.querySelectorAll('*'));
              var el = all.find(e => e.children.length===0 && e.textContent.trim()==={json.dumps(label, ensure_ascii=False)});
              if (!el) return 'not found: {label}';
              el.click();
              return 'clicked';
            }})()"""
            result = self.cdp.js(js)
            if result != "clicked":
                return result
            time.sleep(click_wait)

        return "clicked all" if self.is_category_applied() else "clicked but not applied — see is_category_applied()"

    def is_category_applied(self) -> bool:
        """카테고리 선택이 실제로 반영됐는지 확인 (그룹상품명 필드 렌더링 여부로 판정).

        select_category() 호출의 최종 신뢰 지표. "선택한 카테고리 :" 요약
        텍스트는 페이지 안의 다른 고정 문구와 충돌해 신뢰할 수 없다
        (2026-08-23 실측 — `textContent.indexOf('선택한 카테고리')`가
        무관한 안내문 "선택한 카테고리는 리뷰 '노출'만 설정 가능합니다."에도
        매칭됨).
        """
        n = self.cdp.js("""(function(){
          var all = Array.from(document.querySelectorAll('*'));
          return all.filter(e => e.children.length===0 && e.textContent.trim()==='그룹상품명').length;
        })()""")
        try:
            return int(n) > 0
        except (TypeError, ValueError):
            return False

    def set_group_name(self, name: str) -> str:
        """그룹상품명 입력 (0/40자 제한 필드, placeholder 없음 — 라벨 텍스트로 위치 특정)."""
        js = f"""(function(){{
          var all = Array.from(document.querySelectorAll('*'));
          var label = all.find(e => e.children.length===0 && e.textContent.trim()==='그룹상품명');
          if (!label) return 'label not found';
          var section = label.closest('div');
          for (var i=0;i<6 && section;i++) {{
            var input = section.querySelector('input[type=text]');
            if (input) {{
              var setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
              setter.call(input, {json.dumps(name, ensure_ascii=False)});
              input.dispatchEvent(new Event('input', {{bubbles:true}}));
              input.dispatchEvent(new Event('change', {{bubbles:true}}));
              return 'ok len=' + input.value.length;
            }}
            section = section.parentElement;
          }}
          return 'input not found near label';
        }})()"""
        return self.cdp.js(js)

    def _angular_apply(self) -> str:
        """Angular digest 강제 실행 — selectize로 값을 바꾼 뒤 ng-disabled 등
        바인딩을 갱신시키려면 필수(2026-08-23 실측, 위 모듈 docstring 참고)."""
        return self.cdp.js("""(function(){
          try {
            window.angular.element(document.body).injector().get('$rootScope').$apply();
            return 'applied';
          } catch (e) { return 'error: ' + e.message; }
        })()""")

    def set_option_attribute(self, attr_index: int, values: list[str]) -> str:
        """판매옵션 속성(색상/사이즈 등, 카테고리별로 다름)에 값을 채운다.

        attr_index: 화면에 위에서부터 나열된 속성 순서(0-based). 카테고리에
        따라 속성 개수·이름이 다르므로 라벨 문자열 대신 인덱스로 지정한다 —
        selectize가 만드는 실제 `<select id="standardPurchaseOptionsSelectize{N}">`
        의 N과 대응된다.
        values: 옵션값 리스트 (예: ["블랙", "화이트", "레드"]). 네이버가 제공하는
        기성 옵션값이면 그 값을, 없으면 "직접입력"으로 새로 생성된다.
        selectize.createItem() 호출 후 Angular digest를 강제 실행해 폼 상태에
        반영한다 — 이 순서를 지키지 않으면 "목록으로 적용" 버튼이 계속
        비활성 상태로 남는다.
        """
        js = f"""(function(){{
          var sel = document.getElementById('standardPurchaseOptionsSelectize{attr_index}');
          if (!sel) return 'select not found: index {attr_index}';
          var inst = window.$(sel)[0].selectize;
          if (!inst) return 'selectize instance not found';
          ({json.dumps(values, ensure_ascii=False)}).forEach(function(v){{ inst.createItem(v); }});
          return 'items: ' + JSON.stringify(inst.items);
        }})()"""
        result = self.cdp.js(js)
        self._angular_apply()
        return result

    def apply_option_list(self, wait: float = 1.0) -> str:
        """ "목록으로 적용" 버튼을 클릭해 옵션 조합을 그리드에 생성한다."""
        js = """(function(){
          var btns = Array.from(document.querySelectorAll('button'));
          var btn = btns.find(b => b.textContent.trim() === '목록으로 적용');
          if (!btn) return 'not found';
          btn.click();
          return 'clicked';
        })()"""
        result = self.cdp.js(js)
        time.sleep(wait)
        return result
