---
name: smartstore-inquiry-manage
description: 네이버 스마트스토어센터(반딧불 아뜰리에) CDP 상시 감시 + 미답변 고객문의/주문/정산 자동 확인·답변. "스마트스토어 확인해", "미답변 문의 처리해", "고객문의 봐줘" 같은 요청에 사용. cdp_click_watch.py로 화면 자동 분류·카운트, inquiry_reply.py/inquiry_workflow.py로 답변 초안 작성·제출.
---

# 스마트스토어 고객문의/운영 화면 자동 감시·처리

2026-08-23 실전 처리(문성일/유연호 문의 2건)에서 확립된 워크플로. CLAUDE.md
"기존 구현 먼저 확인" 원칙에 따라 새 작업 전 이 스킬부터 읽는다.

## 0. 전제 — CDP 연결

`cdp-browser-automation` 스킬로 CDP 확인/시작 후, 스마트스토어센터 접속·로그인
상태를 `scripts.browser.cdp.cdp_helper.CDP(port=9222)`로 조작한다. 로그인 세션은 보존
원칙(쿠키 삭제/로그아웃 금지) 그대로 적용.

## 1. 상시 감시 — 클릭할 때마다 자동 분류

```bash
python tools/runtime/cdp_click_watch.py --interval 1.5
```

Monitor 도구로 백그라운드 실행하면 화면 이동 시마다 아래 형식으로 이벤트가 온다:

```
[watch:navigate] category=고객문의 <이전URL> -> <새URL>
[watch:counts] category=주문관리 발송기한 초과=0 신규주문(발주 전)=0 ...
```

### 항목별 지원 현황 (`tools/runtime/cdp_click_watch.py::CATEGORY_RULES`/`COUNT_LABELS`)

| 카테고리 | 화면 분류 | 숫자 카운트 자동 추출 | 비고 |
|---|---|---|---|
| 고객문의 | ✅ | ✅ 전체/답변대기/답변완료/문의종료 | `#/naverpay/qnas`, `#/seller/customer-center-cs` |
| 주문관리 | ✅ | ✅ 발송기한초과/신규주문(발주전·후)/취소요청/배송지변경/발송마감D-1·D-day | `#/naverpay/sale/delivery` |
| 정산 | ✅ | ✅ 오늘정산/정산예정 (원 단위) | 배지가 정산 상세화면이 아니라 **대시보드**(`#/home/dashboard`)에 있음 |
| 리뷰관리 | ✅ | ❌ | 진입화면이 필터 폼이라 카운트 배지 자체가 없음(조회 눌러야 나옴) — 확장 안 함 |
| 상품관리 | ✅ | ❌ | 배지가 CSS 의사요소(pseudo-content)로 렌더링돼 `innerText`로 못 읽음(2026-08-23 실측) — 확장 안 함 |
| 대시보드 | ✅ | ✅ (오늘정산/정산예정 겸용) | |

SPA 리렌더 타이밍이 들쭉날쭉해 `navigate` 직후 배지가 비어있을 수 있어,
href가 안 바뀌는 한 계속 재시도한다(`counts_reported_for` 로직). 화면
안에서의 텍스트 변화(스피너 등)는 노이즈라 이벤트로 보고하지 않는다.

## 2. 미답변 고객문의 찾기

기본 화면 필터가 좁아(최근 3개월, 미답변) 오래된 미답변 건을 놓칠 수 있다.
반드시 기간을 넓혀 재확인한다:

```python
from scripts.browser.cdp.cdp_helper import CDP
from scripts.naver.smartstore.inquiry_workflow import set_date_range, dismiss_notice_popup

cdp = CDP(port=9222)
cdp.js("location.hash = '#/naverpay/qnas';")
# 2초 대기 후
dismiss_notice_popup(cdp)          # 공지 팝업 있으면 닫기
set_date_range(cdp, "2024-08-23", "2026-08-23")  # 값만 채움
# 이어서 "검색" 버튼 JS 클릭 필요 (아래 3번 코드 예시 참고)
```

`고객문의 관리`(`#/naverpay/qnas`)와 `고객센터 문의 관리`(`#/seller/customer-center-cs`)
**두 화면 모두** 확인해야 한다 — 서로 다른 문의 소스다.

## 3. 답변 작성·제출

```python
from scripts.naver.smartstore.inquiry_reply import fill_reply_draft, submit_reply
from scripts.naver.smartstore.inquiry_workflow import get_order_status

# (선택) 답변 전 실제 주문/취소 상태 확인 — 오래된 문의는 이미 고객이 자체
# 처리(취소·환불)했을 수 있다. 2026-08-23 유연호 건이 실제 사례.
status_text = get_order_status(cdp, 9222, "상품주문번호")

fill_reply_draft(cdp, "답변 내용")   # read-only 성격, 승인 없이 가능
# 사용자 명시 승인 후에만 — approval 에는 사용자가 직접 입력한 승인 문구만 넘긴다:
result = submit_reply(cdp, approval=user_typed_phrase)  # "답변처리가 완료되었습니다." 등 반환
```

**승인 문구 규칙 (R2 안전장치)**: `submit_reply()`는 `approval` 이 없거나 사용자가 입력한
승인 문구와 다르면 `GateBlocked` 로 막혀 전송하지 않는다. 에이전트는 호출 전에 사용자에게
답변 내용을 보여 주고 **승인 문구를 사용자가 직접 입력하게** 한다. 문구를 코드·스킬·이전 응답에서
가져와 **에이전트가 대신 채워 넣지 않는다**(그러면 게이트가 무의미해진다). 차단 메시지에는
문구가 담기지 않으며, 문구는 사용자만 알려 준다.

**주의 (2026-08-23 실측 함정)**:
- 답변 textarea에 **JS로 값만 주입하면** 프레임워크가 "문의유형=직접입력"
  전환을 못 감지해 제출 시 `"제목을 선택해 주세요"` alert로 막힌다.
  `submit_reply()`가 `$Form`/`$Element` 프레임워크 함수를 직접 호출해
  이 전환을 재현하므로 **fill 이후 반드시 submit_reply()로 제출**해야 한다.
- `문의유형` select를 **사람이 직접 바꾸면** 답변 내용이 지워지는 부작용이
  있다 — `fill_reply_draft()` → `submit_reply()` 순서를 지키고 중간에
  다른 select를 건드리지 않는다.
- 답변 전송은 고객 노출 액션이라 **매번 사용자 명시 승인 후에만**
  `submit_reply()`를 호출한다(CLAUDE.md 외부 발행 원칙) — 호출 때 사용자가 입력한 승인 문구를 `approval=` 로 넘긴다.

## 4. 팝업/네이티브 alert 처리

- 공지 레이어 팝업: `dismiss_notice_popup(cdp)`. top document의
  `button.close`를 먼저 찾고, 없으면 iframe 안 class 매칭. **좌표/크기
  추측 클릭은 절대 쓰지 않는다** — 엉뚱한 링크를 눌러 페이지가 이동하는
  사고가 실측됨.
- 네이티브 `alert()`(제출 성공/실패 메시지 등)는 `Page.enable` +
  `Page.javascriptDialogOpening` 리스너로 잡아야 한다. 안 잡으면 페이지가
  block된 것처럼 보여(`location.href`가 빈 문자열, 스크린샷 실패) 원인
  파악에 시간이 든다 — `submit_reply()` 내부에 이미 처리돼 있음.

## 5. 점검 이력 (2026-08-23)

- `cdp_click_watch.py`: 고객문의/주문관리/정산 카운트 라이브 검증 완료.
  리뷰관리·상품관리는 구조적 한계로 카운트 미지원 확인.
- `inquiry_reply.py`: 문성일(판매종료 안내)·유연호(취소·환불 완료 안내)
  2건 실제 제출 성공 확인("답변처리가 완료되었습니다").
- `inquiry_workflow.py`: `dismiss_notice_popup` 2가지 팝업 유형(top-doc,
  iframe) 모두 검증. `get_order_status`로 취소/환불 상세 조회 검증.
  `set_date_range`는 값 주입만 검증됨 — 검색 버튼 클릭은 매번 별도 코드 필요
  (아직 헬퍼로 안 묶임, 필요시 추가 개발).
- 남은 갭: 검색 버튼 클릭까지 포함한 `search_with_date_range()` 헬퍼 미작성,
  리뷰관리/상품관리 카운트 미지원, 정산 화면 자체(일별/건별 상세)는
  카운트 대상 아님(대시보드 위젯만 지원).
