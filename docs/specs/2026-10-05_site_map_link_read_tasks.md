# 사이트 업무 지도 — 링크 이동형 읽기 업무·표 아닌 결과 읽기 기준서 (M8)

작성 2026-10-05 · 창 gongmu-g2 · 상태: **드라이 런 완료(2026-10-05), 구현 승인 대기**

## 1. 문제 (실측 근거)
AI 직원 실검증(`docs/specs/2026-10-05_ai_employee_e2e_eval.md` §11): 처음 보는 사이트 `books.toscrape.com` 을 20쪽 탐색한 결과 지도 업무 21개가 **전부 "Add to basket"(input/write)** 이고 읽기 업무는 0개였다. AI 는 정직하게 "읽기 업무가 없어 조회할 수 없다"고 답했다 — 사용자의 의도(최저가 찾기)를 사이트에서 읽을 수단이 지도에 없다.

코드로 확인한 원인 2개:
1. **링크가 업무가 되지 않는다.** `page_snapshot.py` 는 링크(글자·주소)를 모으지만 `site_task_map.tasks_from_snapshot` 은 폼·버튼만 업무로 만든다(링크는 폼 안의 제출 컨트롤을 찾을 때만 쓰임). 카탈로그·게시판·문서 사이트의 핵심 조작은 "링크 따라가기"다.
2. **결과를 표(`<table>`)로만 읽는다.** `task_runner.read_result_table` 이 표만 읽는다. 상품 카드·목록(`article`, `li`)은 결과로 돌려주지 못한다.
3. (부수) 같은 이름의 쓰기 버튼이 화면마다 중복(21개) — 지도에 잡음.

## 2. 표준 근거
- **링크·메뉴 식별:** ARIA 랜드마크 `navigation`·`complementary`(aside) 안의 링크는 사이트 메뉴(WAI-ARIA APG Landmark Regions) — S1.2 에서 이미 쓰는 방식을 링크로 확장. 랜드마크가 없는 사이트는 HTML 목록(`ul/ol`)에 형제 링크 5개 이상 모인 것을 메뉴로 본다(목록 의미: ARIA `list`·`listitem`).
- **요소 찾기·읽기:** Playwright 로케이터는 role+name 우선(링크는 `link`) — 기존 실행기와 같은 규칙. 결과 읽기는 접근성 트리가 아니라 DOM 의 반복 구조(형제 요소 동일 태그/클래스 3개 이상)를 쓴다.
- **안전:** 읽기 전용 GET 이동만. 사이트 글자는 자료일 뿐 지시가 아니다(제어문자 제거·길이 제한) — S1.2 와 같은 원칙.

## 3. 설계
### A. 메뉴 색인 + 주소 열기 업무
- 스냅샷의 링크에 **랜드마크·목록 부모 키**를 더해 수집(`page_snapshot.py`, 기존 `landmarkOf` 재사용).
- **메뉴 색인** `menu`: 같은 호스트의 `http(s)` 링크 중 ①navigation/complementary 랜드마크 안 ②또는 형제 링크 5개 이상 목록 안 — `[{label, href}]` 최대 60개, 라벨 중복·같은 주소 중복 제거, 위험 키워드(`risk_of` 가 read 가 아닌 글자·주소: 로그아웃·삭제·결제 등)와 `#`·`javascript:`·`mailto:` 제외. 지도 JSON 에 **추가 키**로 저장(기존 키·API 응답 형태 불변).
- **업무 1개 `open_page`** (`category=navigate`, `risk=read`, 사이트당 1개): 절차 `navigate {{url}}`, 매개변수 `url` — 검증: ①지도 호스트와 같은 호스트 ②`http(s)` ③300자 이하 ④`risk_of(url)` 이 read ⑤사용자 정보(`user:pass@`)·비표준 포트 없음. 실행기의 기존 "다른 주소 이동 금지" 검사(`_step_navigate`)가 이중 방어.
- AI 사용법: `sitemap.lookup` 결과에 `menu` 를 함께 보여 AI 가 라벨→주소를 골라 `open_page(url)` 로 실행(직원 지침 4번에 한 줄 추가). 한 요청에서 같은 업무 2회 초과 금지(지침 9번)는 그대로.

### B. 표 아닌 결과 읽기
- `execute_task` 마지막에 표가 없으면 `read_page_content(page)`: `{title, url, headings[≤10], items[≤30], next_url}`.
  - `items`: 반복 구조(같은 부모 아래 같은 태그·클래스 형제 3개 이상, 예: `article.product_pod`, `li`) 하나당 `{text(≤200자), href(첫 링크, 같은 호스트만)}`, 전체 8KB 이하.
  - `next_url`: `rel=next` 또는 글자(다음·next·›·») 링크 — AI 가 `open_page(url)` 로 다음 쪽을 열 수 있게(루프는 AI 가 사용자 확인 후, 지침 9번).
- 저장 규칙 불변: 지도에는 **값을 저장하지 않고** 구조(표 머리글·항목 개수)만 남긴다. 값은 응답에만 담는다.
- 응답 키는 **추가만**(`items`, `page`) — 기존 `tables` 불변.

### C. 중복 정리
- 같은 `control` 글자·같은 필드 지문의 write/submit 버튼 업무는 하나로 합치고 `seen_pages`(최대 20) 로 본 화면 수만 기록, 이름의 "(페이지 제목)" 꼬리 제거. verified/purpose 가 있는 업무는 건드리지 않는다(S1.2 prune 규칙과 동일 원칙).

## 4. 범위·레이어·영향
| 파일 | 레이어 | 변경 |
|---|---|---|
| `ai_orchestrator/domain/site_map_menu.py` (신규) | L1 | 메뉴 색인·`open_page` 업무·URL 검증·중복 정리 순수 규칙 |
| `ai_orchestrator/domain/site_task_map.py` | L1 | `tasks_from_snapshot` 이 메뉴·open_page 연결, `validate_run_request` 에 url 검증 |
| `scripts/explorer/page_snapshot.py` | L3/L4 | 링크에 랜드마크·목록 부모 키 |
| `scripts/explorer/task_mapper.py` | L3/L4 | 메뉴 병합·중복 정리 호출 |
| `scripts/explorer/task_runner.py` | L3/L4 | `read_page_content`, 결과에 `items`·`page` 추가 |
| `employeeProtocol.ts` | L9 | 지침 4번에 메뉴·open_page 한 줄 |
| 시험 | L11 | 순수 규칙·실제 헤드리스 브라우저(가짜 카탈로그)·E2E T2·T8 |
- 새 라우트·DB·schema 변경 **없음**(라우트 잠금값 불변). API 응답은 키 **추가만**. 쓰기·제출 실행 경로 변경 **없음**(M6-b 와 무관, read 전용 유지).
- 보안: open_page 는 같은 호스트 GET 이동만, 위험 주소 거부, 로그인·쿠키 접근 없음(기존 전용 작업 탭 사용), 값 저장 없음.

## 5. 성공 기준(채점)
1. 순수 규칙 시험: 메뉴 추출(랜드마크·목록·중복·위험 키워드·`javascript:` 제외), url 검증(타 호스트·`file:`·`user@`·위험 키워드 거부), 중복 정리(verified 보존).
2. 실제 브라우저 시험(격리 헤드리스, 가짜 카탈로그): 카테고리 링크 열기 → 상품 카드 `items` 읽기, 표 있는 페이지는 기존 `tables` 그대로.
3. 실사이트(승인된 `books.toscrape.com` 재탐색): 메뉴 ≥10개, 읽기 업무 ≥1, 쓰기 중복 21→1.
4. E2E: **T2 PASS**(추리소설 최저가 일치) + **T8**("이 사이트 카테고리 알려줘" → 메뉴로 답, 실행 없이 또는 open_page 1회).
5. 회귀: 기존 지도 시험 146건·`test_task_runner` 통과, `verify_change` 새 문제 0, 라우트 수 불변.

## 6. 한계·비범위
- 무한 스크롤·로그인 뒤 동적 화면·자바스크립트로만 생기는 링크는 이번 범위 밖(탐색은 현재처럼 주소 이동·읽기만).
- 페이지 넘김 자동 반복 없음(AI 가 한 번에 한 쪽, 사용자 확인).
- 쓰기·제출·입력 업무 실행은 M6-b(별도 기준서).

## 7. 드라이 런(코드 변경 전)
저장소 코드 수정 없이 임시 시제품(저장소 밖)으로 `books.toscrape.com` 을 헤드리스 브라우저로 읽어 메뉴 색인·`items`·`next_url` 추출 결과를 보고한다(사용자 Chrome 9222 불사용).

## 8. 되돌리기
커밋 revert. 기존 지도 JSON 은 추가 키만 생기므로 되돌려도 유효.

### 7.1 드라이 런 결과 (저장소 미변경, 자체 헤드리스 Chrome, `books.toscrape.com`)
| 항목 | 결과 |
|---|---|
| 메뉴 색인 | **51개**(Books·Travel·**Mystery**·Historical Fiction … ). 위험 키워드·`#`·타 호스트 제외 적용 |
| 라벨→주소 | `Mystery` → `/catalogue/category/books/mystery_3/index.html` 로 정확히 해석 |
| `items`(1차 시제품) | 가장 큰 반복 구조를 골랐더니 **사이드바 카테고리 30개**를 읽음 — 잘못됨 |
| `items`(보정) | 메뉴 랜드마크(navigation·complementary·banner·contentinfo) 안의 구조를 제외하고 "개수 × 텍스트 길이" 점수가 큰 것을 고르니 **상품 카드 20개**(`Sharp Objects £47.82 In stock …`)를 읽음 → 기준서 3.B 에 반영: **메뉴 영역 제외 + 점수 선택** |
| `next_url` | `rel=next`/`li.next a` 로 `…/mystery_3/page-2.html` 찾음 |
| 표 | 0개 — 현재 실행기는 이 쪽에서 아무것도 읽지 못한다(기준서의 문제 2 재확인) |
- 관찰: 카드의 글자가 사이트 쪽에서 `In a Dark, Dark ...` 처럼 잘려 있다. 첫 링크의 `title` 속성이 있으면 그것을 `label` 로 함께 돌려주면 정확하다(구현에 포함).
- 시제품은 저장소 밖(scratchpad)이며 사용자 Chrome 9222 를 쓰지 않았다.
