---
name: smartstore-detail-page-publish
description: 네이버 스마트스토어(반딧불 아뜰리에) 신규 상품 등록 + SmartEditor ONE 상세페이지를 이미지+HTML 블록으로 작성. "상품 등록해", "상세페이지 만들어줘", "스마트스토어에 올려줘" 같은 요청에 사용. 카테고리 트리 선택 함정, 차단 모달 해제, HTML 삽입 셀렉터 버그 수정 등 2026-08-26 루씨에어 코타라 CTC 실링팬 등록으로 실전 검증 완료.
---

# 스마트스토어 상품 등록 + 상세페이지(SmartEditor ONE) 작성

네이버 스마트스토어(반딧불 아뜰리에)에 신규 상품을 등록하고, SmartEditor ONE
상세페이지를 이미지+HTML 블록으로 채우는 CDP/Playwright 자동화 절차.
2026-08-26 루씨에어 코타라 CTC 실링팬 등록으로 실전 검증 완료.

기존 구현: `scripts/naver/smartstore/product/general_product.py`(기본정보 등록),
`scripts/naver/smartstore/product/description_editor.py`(SmartEditor ONE 조작).
**새로 만들지 말고 이 두 모듈을 그대로 재사용한다.**

## 0. 카테고리 API 등록 불가 — CDP만 유일한 경로

[[smartstore-commerce-api-blocked]] 참조. 메인 사업자 계정 보호조치로 커머스API
신청 자체가 막혀 있어, 상품 등록은 CDP(Playwright `connect_over_cdp`)로만 가능하다.

## 1. 사전 준비 — 로그인 + 로그인 상태 재확인

```python
from scripts.naver.smartstore.cli.blog_publish_manual import ... # (예시 아님)
```
스마트스토어 판매자센터는 로그아웃 상태에서 자동 재로그인을 시도하지 않는다
(OTP/캡차는 사용자만 처리 가능, CLAUDE.md 로그인 세션 보존 원칙). 매 작업 전:

```python
from scripts.browser.cdp.cdp_helper import CDP
cdp = CDP(port=9222)
cdp.navigate("https://sell.smartstore.naver.com/#/home/dashboard", wait=3)
txt = cdp.js("document.body.innerText")
# "로그인하기" 뜨면 로그아웃 상태 — 사용자에게 재로그인 요청, 절대 자동 로그인 시도 안 함
```

## 2. 상품 등록 폼 진입 + 팝업 처리 + 카테고리 선택

`GeneralProductRegister(page).open()` 으로 진입(URL 직접 이동 실패 시 사이드바
클릭으로 자동 폴백). 진입 직후 **반드시 공지 팝업부터 닫는다** — 안 닫으면 이후
클릭이 전부 가로채인다:

```python
from scripts.naver.smartstore.navigation.popup_handler import dismiss_all_popups
dismiss_all_popups(page)  # 2026-08-26 재검증: closed=6, 공지 레이어 포함 정상 처리
```

**카테고리는 검색창에 후보명을 넣어도 실제 리프 카테고리명과 다르면 "카테고리가
없습니다"가 뜬다** — 예: "서큘레이터/실링팬"으로 검색하면 없고, 실제로는 4단
트리를 펼쳐 **"디지털/가전 > 계절가전 > 선풍기 > 천장형선풍기"**를 선택해야
한다. 검색 드롭다운(자동완성 결과)은 자동클릭이 잘 안 먹으니 **"카테고리명 선택"
탭의 4단 캐스케이드 트리를 클릭**한다.

**클릭 방식 중요 (2026-08-26 실측 확정)**: raw CDP `Input.dispatchMouseEvent`나
JS `element.click()`은 이 Angular 트리에서 반응하지 않는다(ng-click이 무시함).
**Playwright의 `page.get_by_text(text, exact=True).first.click()`(trusted 이벤트)
만 안정적으로 동작한다**:

```python
for label in ["카테고리명 선택", "디지털/가전", "계절가전", "선풍기", "천장형선풍기"]:
    page.get_by_text(label, exact=True).first.click()
    time.sleep(1)
# 검증
txt = page.evaluate("document.body.innerText")
assert "선택한 카테고리 : 디지털/가전>계절가전>선풍기>천장형선풍기" in txt
```

카테고리 트리 3번째 열이 **가상 스크롤이 아니라 실제 DOM에 있지만 페이지 자체가
큰 음수 y좌표(예: y=-3280)로 스크롤되어 화면 밖에 있는 경우**가 있다 — Playwright
클릭은 자동 `scrollIntoView`를 하므로 보통 문제없지만, raw CDP로 좌표를 직접
계산해야 할 상황이면 `el.getBoundingClientRect()`로 좌표를 확인하고 y가 비정상이면
`window.scrollTo(0, window.scrollY - (필요만큼))`으로 페이지를 먼저 맞춘다.

## 3. 기본 정보 입력 (name/price/stock/main_image)

```python
from scripts.naver.smartstore.product.general_product import GeneralProductRegister
reg = GeneralProductRegister(page)
reg._opened = True  # 이미 폼이 열려있고 카테고리도 선택된 상태라면 open() 재호출 불필요
reg.set_product_name("...")
reg.set_price(649000)
reg.set_stock(20)
reg.upload_main_image(r"C:\...\main_image.png")
```

**함정**: `upload_main_image()`가 `{"ok": False, "error": "image_modal_not_opened"}`로
실패할 수 있다 — 카테고리 선택 직후 뜬 안내 모달(예: "그룹상품으로 등록하세요" 배너,
KC인증 안내 등)이 화면에 남아 클릭을 가로챈다("intercepts pointer events"). 실패 시
바로 재시도하지 말고 `reg._dismiss_blocking_modals()`를 먼저 호출한 뒤 재시도한다.

메인 이미지는 정사각형(1000x1000 권장)이 안전하다. 마케팅용 세로형 히어로 이미지를
그대로 쓰지 않는다 — 대표이미지 슬롯은 정사각형 크롭이 맞다.

## 4. 상세페이지(SmartEditor ONE) — 이미지+HTML 블록 조합

`SmartEditorSession(page)` 로 진입:

```python
from scripts.naver.smartstore.product.description_editor import SmartEditorSession
ed = SmartEditorSession(page)
ed.open()  # 등록 폼의 "스마트 에디터 ONE 으로 작성" 버튼 클릭 → #/editor 로 전환
```

**함정 1 (2026-08-26 근본 원인 확정, 코드 수정 완료) — "스마트 에디터 ONE" 버튼은
같은 탭에서 라우트 전환되는 게 아니라 새 탭(팝업)을 연다.** 예전 코드는
`self.page.url`이 `#/editor`로 바뀌길 폴링했는데, 실제 전환은 새로 열린 탭에서
일어나서 원래 탭은 계속 `#/products/create`인 채로 남아있었다. 그 결과 원본 폼
탭과 에디터 탭이 서로 다른 무관한 탭으로 쪼개지고, 나중에 에디터에서 "등록"을
눌러도 "저장하려는 상품 등록 화면이 종료되어 등록할 수 없습니다" 에러가 났다
(콘텐츠 25블록을 다 채운 뒤에 이 사고가 나서 전부 유실된 적 있음).

**고침**: `_click_editor_btn()`이 이제 `self.page.context.expect_page()`로 새 탭을
확실히 캡처하고, `SmartEditorSession`의 `self.page`/`text`/`block`/`tool`/`ai`를
**새 탭으로 자동 교체**한다. 호출부는 그냥 `ed.open()`만 부르면 되고, 이후
`ed.block.insert_html(...)` 등은 자동으로 올바른(새) 탭에서 실행된다. 검증:
`ed.open()` 후 `ed.page is 원래page` → `False`, `ed.page.url` → `#/editor`.

이 원리(브라우저 레벨 CDP `Target.setDiscoverTargets`로 새 타겟 생성을 실시간
캡처하는 것과 동일한 메커니즘)가 다른 사이트에서도 "버튼 눌렀는데 새 탭이 열려서
꼬이는" 문제에 재사용 가능하다 — `context.expect_page()`가 Playwright에서 그
역할을 대신해준다.

**함정 2 — 여러 스크립트를 동시에/연달아 백그라운드로 띄우면 서로 경합한다.**
Playwright는 매번 `connect_over_cdp`로 같은 페이지에 새로 연결하는데, 이전
백그라운드 프로세스가 안 끝난 채로 새 스크립트를 또 띄우면 두 스크립트가 같은
DOM을 동시에 조작해 "HTML 입력창 없음" 같은 오류가 무더기로 난다. **한 번에
스크립트 하나만 실행**하고, 끝난 걸 `TaskOutput`으로 확인한 뒤 다음 것을 띄운다.

**함정 3 (2026-08-26 실제 코드 버그, 수정 완료) — HTML 삽입 셀렉터가 실제 화면과
달랐다.** `description_editor.py`의 원래 값:
```python
HTML_TEXTAREA = "textarea[placeholder*='HTML']"   # 틀림 — 실제 placeholder는 "내용을 입력해주세요."
HTML_CONFIRM = "button:has-text('확인')"           # 틀림 — 실제 버튼 텍스트는 "변환"
```
고친 값(현재 코드에 반영됨):
```python
HTML_TEXTAREA = "textarea[placeholder*='입력해주세요']"
HTML_CONFIRM = "button:has-text('변환')"
```
이 버그 때문에 `insert_html()`이 항상 실패하고, 실패한 채로 열린 "HTML 변환"
모달이 그 다음 모든 클릭을 가로채 전체 파이프라인이 도미노로 실패했었다.
**이 셀렉터가 다시 어긋나면(네이버가 UI를 바꾸면) 먼저 스크린샷으로 실제
placeholder/버튼 텍스트를 확인하고 고친다** — 억지로 재시도 루프를 늘리지 않는다.

**패턴**: 이미지와 텍스트를 번갈아 삽입할 때는 텍스트를 매번 `write_paragraph()`
(키보드 타이핑)로 넣지 않고 **`insert_html()`로 인라인 스타일 있는 `<p>`/`<table>`
HTML을 통째로 붙여넣는 편이 훨씬 안정적**이다(타이핑은 포커스 유실에 취약, HTML
삽입은 모달 텍스트박스에 `fill()` 한 번이라 안정적). 표(SPEC, 가격비교)도 마찬가지로
`<table>` HTML을 만들어 `insert_html()`로 한 번에 넣는다.

```python
def do(label, fn, *a):
    r = fn(*a)
    if not r.get("ok", False):
        print("STOP at", label, r)
        return False
    time.sleep(1.0)
    return True

ok = True
if ok: ok = do("hero", ed.block.insert_image_file, "hero.png")
if ok: ok = do("title", ed.block.insert_html, "<p>...</p>")
# ... 이후 단계는 이전 단계가 실패하면 자동으로 건너뛴다(도미노 실패 방지)
```

## 5. 콘텐츠 순서 (실전 검증된 카피 구조)

블로그 판매글과 같은 원칙([[blog-product-selling-strategy]]) — 스펙 나열이 아니라
"공간 확인 → 신뢰 → 제품" 순서로 배치한다. 2026-08-26 코타라 CTC 등록에서 쓴
실제 순서:

1. 히어로 이미지(제품 메인 컬러, 헤드카피 오버레이 — 별도 PIL로 사전 제작)
2. Before/After 비교 이미지 2장 + "예시 이미지·배치 시안" 라벨
3. 고민 자극 텍스트
4. 핵심 서비스 흐름(사진→검토→시안→선택→상담)
5. 제품 소개 이미지 6장 (공급사 허가 이미지: 설치컷→정면→IoT→모터→보증→소음시험)
6. SPEC 표 (HTML table)
7. 가격 비교표 (HTML table)
8. 설치 전 체크리스트
9. 조명 조합 비교 이미지 3장
10. CTA (전화번호)

**AI 생성 이미지(GPT 렌더)에는 반드시 "예시 이미지 · 배치 시안" 표기** —
[[apartment-lighting-plan]] 정책과 동일 이유(정밀 3D 아님, 클레임 방지).

## 6. 상품 주요정보 — 원산지 (`set_origin`)

`GeneralProductRegister.set_origin(origin_type, continent=None, country=None)`
(2026-08-26 신규 구현·검증 완료). **기본값이 항상 "국산"으로 미리 선택돼 있어서**
수입산 제품인데 그대로 등록하면 원산지 오표기가 된다 — 실물 SPEC과 대조해서
반드시 명시적으로 채운다.

```python
reg.set_origin("수입산", continent="아시아", country="중국")
# 국산이면: reg.set_origin("국산")
```

**함정 1 — 드롭다운이 여러 개 섞여있다.** "인증선택", "인증정보", 원산지의
대륙/국가까지 전부 텍스트가 "선택"이라 **원산지 라벨과 같은 가로줄(±20px)에
있는 것만 후보로 걸러야** 한다. 그냥 "화면에서 첫 번째 '선택'"을 클릭하면
엉뚱한 필드(인증선택 등)가 열린다.

**함정 2 — "상품 주요정보" 섹션 헤더는 토글이다.** 펼쳐져 있는지 안 보고
무조건 클릭하면 오히려 접어버린다. 클릭 전에 "원산지" 레이블이 실제로 DOM에
있는지(`document.querySelectorAll('label,div,span')`에서 innerText 완전일치)
먼저 확인하고, **없을 때만** 헤더를 클릭한다.

**함정 3 — 라벨 요소는 `children.length === 0`이 아니다.** 필수표시 점(●) 때문에
자식 노드가 1개 있다. leaf 노드만 찾는 셀렉터를 쓰면 라벨 자체를 못 찾는다 —
태그 종류(label/div/span)로 필터링하고 자식 유무는 보지 않는다.

**함정 4 — 원산지 대륙/국가 드롭다운 좌표를 한 번만 계산해서 재사용하면 안 된다.**
대륙 옵션을 클릭하면(`scrollIntoView` 부작용으로) 페이지 스크롤 위치가 바뀌어서
"원산지" 라벨의 화면상 y좌표도 같이 바뀐다. 국가 드롭다운을 찾을 때 예전 y좌표를
쓰면 못 찾는다 — **매번 라벨 위치를 새로 조회**해야 한다(`set_origin` 내부
`_find_row_select_coords()`가 매 호출마다 재계산하도록 구현됨).

**함정 5 — 국가처럼 목록이 긴 드롭다운은 `get_by_text(value, exact=True)`가
위험하다.** 검색 자동완성이 `<strong>중국</strong>`처럼 하이라이트용 숨겨진
엘리먼트를 먼저 만들어서, exact-text 매칭이 이 보이지 않는 요소를 잡아
`element is not visible` 타임아웃이 난다. **`div.option` 클래스로 실제 리스트
항목만 좁히고**, 목록이 길어 항목이 뷰포트 밖에 있을 수 있으니 클릭 전
`scrollIntoView({block:'center'})`를 반드시 호출한다(`set_origin` 내부
`_click_dropdown_option()` 참조 — 재사용 가능한 패턴).

**함정 6 — "상품 주요정보" 등 아코디언 섹션은 최초 1회만 펼치면 된다.** 헤더
클릭은 토글이라, 값이 채워졌는지 재확인할 때 무심코 또 클릭하면 접혀버려서
그 다음 필드 탐색이 전부 실패한다.

### 예약구매 — 기본값이 켜져 있을 수 있다 (postflight로 반드시 확인)

`postflight(page)`를 등록 직전에 실행하면 `vm.isPreOrderOn=true` 경고가 뜰 수
있다(2026-08-26 실측, 원인 불명 — 카테고리 특성이거나 이전 조작의 부작용).
이 상태로 저장하면 일반 판매가 아니라 **예약구매 상품**으로 등록된다. 반드시:

```python
from scripts.naver.smartstore.product.postflight import postflight
report = postflight(page)
if any("예약구매" in w for w in report.warnings):
    page.get_by_text("설정안함", exact=True).first.click()  # 예약구매 섹션의 토글
```

### 상품 주요정보 필수 항목 전체 확인 — `postflight()`로 조회

수동으로 필수(●) 항목을 화면에서 찾지 말고 `postflight(page).actionable_missing`을
쓴다 — 정확한 필드명(`vm.viewData.originAreaInfo.importer` 등)과 라벨을 바로 준다.
2026-08-26 코타라 CTC 등록 실측: `set_origin()` + 예약구매 해제만으로 필수미입력이
7건 → 1건(KC 인증, 의도적으로 제외)까지 줄었다.

## 7. 등록 전 안전장치

`reg.save()` / `ed.submit()` 모두 기본값이 `require_confirm=True`라 터미널
`input()`으로 확인을 받는다 — **비대화형 스크립트(백그라운드 실행)에서는 이 확인이
막혀버리므로 절대 `require_confirm=False`로 자동 등록하지 않는다.** 외부 공개
발행은 매번 사용자 재확인이 원칙(CLAUDE.md) — 폼을 다 채운 뒤 스크린샷으로 보여주고
채팅으로 명시적 승인을 받은 다음에만 등록 버튼을 누른다.

## 8. 제조자(사) / A/S 전화번호 / 옵션 / 최종 등록 (2026-08-26 완전 재현 검증)

`general_product.py`에 `set_manufacturer()`, `set_customer_service_phone()` 재사용
메서드로 구현됨.

### 8-1. 제조자(사) — selectize 자동완성, fill()로는 절대 안 붙는다
`input[placeholder='제조자(사)를 입력해주세요.']`에 `fill()`만 하면 값이 안
붙는다(selectize가 실제 폼 상태를 별도 hidden 값으로 관리). 반드시:
클릭 → 키보드 타이핑 → **Enter**(옵션 리스트에 `div.create.active`
"직접입력: {값}" 생성) → 그 옵션을 좌표 클릭. "선택된 제조자(사) : {값}"
문구로 반영 확인. **주의**: 이 필드에 이전 등록에서 남은 엉뚱한 값
("(주)청연엠엔에스" 등)이 기본 표시돼 있을 수 있다 — 등록 전 반드시 실제
제조사명과 일치하는지 확인.

### 8-2. A/S 책임자/소비자상담 전화번호
라디오 2개("A/S 책임자"/"소비자 상담 관련 전화번호") 중 하나가 기본 선택돼
있고, 그 아래 텍스트 입력창 하나를 공유한다. 라디오는 건드릴 필요 없이
입력창에 바로 타이핑하면 된다. 검증 시 `page.evaluate("document.body.innerText")`
로는 "×"(클리어 아이콘)만 보여 헷갈릴 수 있음 — 실제 확인은 input의
`.value`로 해야 한다.

### 8-3. 옵션(선택형) — "설정함"인데 값이 비어있으면 저장이 막힌다
카테고리에 따라 옵션(선택형) 섹션이 기본 "설정함"으로 켜져 있는데, 옵션값을
안 채우면 최종 저장 시 조용히 막힌다(에러 모달 없이 그냥 같은 페이지에
머무름 — **postflight()에도 안 잡힘**, `body.innerText`에서 "옵션을
입력해주세요"로만 확인 가능). **주의**: 이 "선택형" 라디오(설정함/설정안함)를
클릭/체크해도 — 심지어 Playwright `.check(force=True)`로 실제 `checked`
상태가 바뀌어도 — 화면이 갱신되지 않는다(Angular 재렌더 트리거 안 됨,
원인 미상). 단일 색상 상품이라도 이 토글을 끄려 하지 말고, 대신
**실제 옵션 하나를 채워 넣는 게 훨씬 빠르고 확실하다**:
1. "옵션입력"의 옵션명(`placeholder="예시:컬러"`)/옵션값(`placeholder="예시 : 빨강,노랑 ( , 로 구분 )"`)
   입력창에 각각 타이핑 (예: "색상" / "화이트")
2. "옵션목록으로 적용" 버튼 클릭 → ag-Grid 표에 옵션 행 1개 생성됨
3. **새로 생긴 옵션 행은 재고수량 0으로 시작해 "품절" 상태다** — ag-Grid
   `div.ag-cell[col-id=stockQuantity]`를 **더블클릭**해 인라인 편집 모드
   진입 → `Ctrl+A` → 재고수량 타이핑 → `Tab`. `status` 컬럼이 "판매중"으로
   바뀌는지 확인.

### 8-4. KC인증 — "있음/없음" 토글은 실제 법적 신고이므로 AI가 임의 선택 금지
"상품 주요정보 > KC인증" 섹션은 **두 개의 별개 필드**로 구성된다. 혼동하지 말 것:
- **"법에 의한 인증, 허가 등을 받았음을 확인할 수 있는 경우 그에 대한 사항"**
  (상품정보제공고시 섹션) — 라디오 "직접입력"/"해당사항 없음". 실물 인증
  정보가 없으면 "해당사항 없음" 클릭으로 그 아래 필수 textarea 자체가 사라짐.
  이건 KC 인증 여부와 무관한 정보고시용 텍스트라 AI가 판단해도 무방.
- **"KC인증 있음 / KC인증 없음"** 토글 + 없음일 때 "인증선택"(구매대행/
  병행수입/안전기준 준수/KC 안전관리대상 아님 등, 카테고리마다 옵션 다름) —
  이건 **실제 통관·유통 방식에 대한 법적 신고**(허위 시 "3년 이하의 징역
  또는 3천만원 이하의 벌금형" 문구가 화면에 명시됨). **AI가 임의로 선택하지
  않는다.** 사용자가 직접 처리하도록 안내하거나, 사용자가 이미 골라놓은
  값을 그대로 두고 다음 단계로 넘어간다. "KC인증 있음"을 고르면 별도
  "인증정보"(인증 유형 드롭다운, 예: `[전기용품]안전인증_국가인증`) 선택도
  추가로 필요해진다.

### 8-5. 최종 저장 버튼 — "저장하기" 버튼이 페이지에 최소 2~3개 있다
`button.btn-primary.progress-button:has-text("저장하기")`가 폼 최상단
플로팅 바(`y≈661`, width 110)와 폼 맨 아래 실제 제출 버튼(width 180) 등
여러 개 매칭된다. **`querySelector`(첫 매치)나 좌표 계산으로 고른 것이
실제로 클릭 가능한 버튼이 아닐 수 있다** — 이 경우 클릭은 "성공"한 것처럼
보여도(예외 없음, URL 안 바뀜) 실제로는 아무 반응이 없다. 반드시
Playwright `page.locator(...).click()`(자동 스크롤+가시성 확인 포함)을
쓴다 — 이게 안전한 이유는, 저장 후 뜨는 **완료 확인 모달**
(`div.seller-layer-modal.in`, 텍스트 "상품저장이 완료되었습니다")이 화면을
덮고 있으면 Playwright가 "intercepts pointer events" 에러로 명확히
알려주기 때문(raw `page.mouse.click()`은 이런 가림 상태를 감지 못하고
그냥 허공을 클릭한 것처럼 조용히 넘어간다). 저장 완료 확인은 모달 텍스트로
1차 확인 + `#/products/origin-list`(상품 조회/수정, **주의: `/products/list`
아님** — 존재하지 않는 라우트라 대시보드로 리다이렉트됨) 페이지에서
상품명으로 검색해 실제 등록된 상품번호를 최종 확인한다.

## 9. 화면 확인은 스크린샷보다 `body.innerText`/좌표 조회를 우선한다
이 폼은 매우 긴 단일 페이지라 Playwright `page.screenshot()`이 스크롤
위치에 따라 **완전히 빈 회색 화면**을 반환하는 경우가 잦다(가상 스크롤/
레이아웃 이슈로 추정, 원인 미상 — [[cdp-browser-automation]]의 "font
로딩 타임아웃" 문제와는 다른 증상). 스크린샷이 안 나온다고 페이지가
깨졌다고 판단하지 말고, `page.evaluate("document.body.innerText")`와
좌표 기반 `page.evaluate()` 탐색으로 상태를 확인하는 게 훨씬 안정적이다.

## 10. 등록 후 상품 수정(옵션 추가 등) — 등록 폼과 다른 함정들 (2026-08-26)

이미 등록된 상품에 색상 옵션을 추가하는 등 "수정" 흐름은 등록 흐름과 URL/DOM
구조가 다르다. 실전 검증: 화이트 단일색으로 등록한 상품에 화이트티크/
블랙다크코코아 옵션을 추가.

### 10-1. 상품 목록의 "상품번호"(예: `13734878775`) ≠ 편집 라우트 ID
`#/products/origin-list`에서 보이는 상품번호로 `#/products/edit/{그번호}`를
직접 열면 **다른 페이지로 리다이렉트되거나 예상치 못한 상품이 열릴 수 있다.**
반드시 목록 화면의 실제 "수정" 링크를 클릭해서(같은 탭에서 라우트 전환,
새 탭 안 열림 — `context.pages`에서 URL로 다시 찾아야 함) 사이트가 생성한
진짜 편집 URL(`#/products/edit/{내부ID}`, 상품번호와 다른 숫자)을 얻는다.
편집 후에는 반드시 `textarea[maxlength="100"]`(상품명) 값으로 올바른
상품을 열었는지 재확인한다.

### 10-2. 편집 모드에서는 "옵션" 섹션이 기본 접혀 있다 (등록 모드와 다름)
등록(create) 폼에서는 옵션 섹션이 펼쳐진 채로 보이지만, 수정(edit) 폼은
`ng-show="vm.isMenuOpen"`로 기본 collapse돼 있다. 섹션 헤더의
"옵션 \n도움말\n설정함\n메뉴토글"만 보이고 `옵션목록`/입력창이 전혀
안 잡히면 접힌 것이다. 펼치는 토글은 `<button>`이 아니라
**`<a class="btn btn-default"><span class="sr-only">메뉴토글</span></a>`**
— `querySelector('button')`로 찾으면 못 찾는다. JS로 직접
`opt.querySelector('div.set-option a.btn').click()` 해야 한다.

### 10-3. 옵션명/옵션값 입력창은 selectize — 좌표 재사용 절대 금지, 반드시 placeholder로 재조회
좌표를 한 번 구해서 재사용하면 **엉뚱한 필드(브랜드 selectize 등)를 클릭하게
된다** — 스크롤/레이아웃 변화로 같은 좌표가 다른 필드를 가리키게 되기 때문.
반드시 매번 `page.locator('input[placeholder="예시:컬러"]')` /
`input[placeholder*="빨강"]`로 다시 찾아 클릭한다. **편집 모드에서는 이 두
입력창에 기존 옵션값이 미리 채워져 있다** (`색상`, `화이트` 등) — `fill()`을
쓰지 않고 `type()`만 하면 기존 값 뒤에 이어붙는다(`색상색상` 같은 사고).
반드시 `locator.fill(새값)`으로 덮어쓴다. 값 입력 후 **"옵션목록으로 적용"
클릭 → 확인 모달("입력된 옵션 정보를 옵션목록으로 적용하시겠습니까?")의
"확인" 버튼까지 눌러야** 실제 목록에 반영된다(등록 폼에서는 이 확인 모달이
없었다 — 수정 폼에만 있음). **옵션값에 쉼표로 여러 개를 한 번에 넣으면
기존 옵션값을 포함해 전체가 새로 생성된다** — 예: 기존 "화이트" 하나만
있는 상태에서 "화이트,화이트티크,블랙다크코코아"로 적용하면 3행이 생기고
기존 화이트 행의 재고/가격은 0으로 리셋된다(재입력 필요).

### 10-4. 하단 고정 네비게이션 바가 ag-Grid 옵션 행 클릭을 가로챈다
화면 하단에 `div.pc-fixed-area.navbar-fixed-bottom`(노출설정/미리보기/
저장하기/삭제/취소 버튼 바)가 항상 떠 있다. 옵션목록 표가 스크롤 위치상
화면 하단쪽에 걸리면, 그 행의 좌표를 `document.elementFromPoint()`로
찍었을 때 **표 셀이 아니라 이 고정바가 잡힌다** — 더블클릭이 조용히
무시되고(에러 없음) `document.activeElement`가 `BODY`로 남아 재고입력이
안 먹힌다. 증상: 첫 번째 옵션 행(화면 위쪽)은 성공하는데 아래쪽 행들만
계속 실패. 해결: 목표 셀 좌표를 구하기 전에
`document.elementFromPoint(x,y)`로 실제 무엇이 잡히는지 확인하거나,
`.pc-fixed-area.navbar-fixed-bottom`의 `getBoundingClientRect().top`보다
위에 오도록 `document.documentElement.scrollTop`을 조정한 뒤 좌표를
다시 조회한다.

## 11. 컬러 배리언트 정식 명칭은 원본 자료(블로그 이미지 등)에서 확인
루씨에어 코타라 CTC의 정식 컬러명(화이트/화이트티크/블랙다크코코아, 영문
#White, #White/Teak, #Black/Koa)은 임의로 "우드"/"다크"로 부르지 말고
`data/naver_blog_images/gonobi_224362505769/22.png` 같은 원본 공급사 자료의
"Color" 스와치 이미지에서 실제 표기를 확인해서 써야 한다. 같은 폴더
`24.png`에는 실제 KC 전기용품안전인증번호(`JU072055-25001`)와 방송통신기자재
등록번호(`R-R-mDc-KOTARA`)도 있다 — KC인증 관련 필드를 나중에 정확히
채워야 할 때 이 출처를 먼저 확인한다(임의 값 입력 금지 원칙은 유지).

관련: [[smartstore-commerce-api-blocked]], [[smartstore-group-product]],
[[apartment-lighting-plan]], [[blog-product-selling-strategy]], [[cdp-browser-automation]]
