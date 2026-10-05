# 네이버 카페 가입 카페 변동(신규 가입·탈퇴) 반영·분석 기준서

작성 2026-10-05 · 창 gongmu-g2 · 상태: **드라이 런 완료(로그인 만료로 중단), 구현은 로그인 복구 후 승인 대기**

## 1. 요청
"네이버 카페 목록을 반영해서 업데이트 — 신규 가입건·탈퇴건을 카페 탭 목록에 반영하고 분석."

## 2. 기존 구현 확인 (`capability_check cafe`, `vendor_api_registry`)
- **공식 API:** 벤더 목록에 "카페 읽기/쓰기 — 이 앱에 미등록" → CDP 읽기가 정당한 경로(기존 방침 그대로).
- **있는 것:** `POST /naver-cafe/collect-my-cafes`(가입 카페 전용 API `cafe-home/v3/homepc?myCafeCount=500` 우선, 실패 시 화면 읽기로 대신) → `data/cafe/my_cafes.json`, `GET /naver-cafe/my-cafes`, 카페 탭 `MyCafesTab`(목록·수집 버튼), `ai-analyze`(수집한 게시글 분석).
- **없는 것(문제):**
  1. `save_my_cafes` 가 매번 `my_cafes.json` 을 **통째로 덮어써 이력이 없다.**
  2. 신규 가입·탈퇴 **비교가 없다.**
  3. **빈 결과도 그대로 덮어쓴다** — 로그인이 풀려 API 가 빈 목록을 주면(드라이 런에서 실제 발생) 저장본이 비고, 화면 읽기 대신 결과는 추천·최근 방문 카페가 섞일 수 있다(코드 주석에 "최후수단"). 비교를 얹으면 전부 "탈퇴"로 잘못 기록될 위험.
  4. 수집 항목 `member_count` 는 API 응답에 없어 0 으로 채워진다(회원 수 변화는 이 API 로 못 본다).

## 3. 드라이 런 결과 (2026-10-05, 저장소 미변경, 전용 작업 탭 1개·읽기만)
| 항목 | 결과 |
|---|---|
| 목록 API(v3 homepc) | HTTP 200, `result.myCafe.cafes` 키 구조 확인(`cafes`·`pageInfo`·`viewType`). **항목 0개** |
| 원인 | 9222 Chrome 에 네이버 로그인 쿠키 `NID_AUT`·`NID_SES` **없음**(이름 존재 여부만 확인, 값은 읽지 않음) → 세션 만료/소멸 |
| 부수 확인 | 임시 작업 탭이 정리되지 않고 남음(`keep_page`) → 구현 시 탭을 닫는 정리 필요. 시험 중 만든 탭 1개는 수동으로 닫음 |
| 결론 | 이 상태로 구현하면 "빈 목록 = 전부 탈퇴"로 오판하기 쉽다 → **빈·불완전 결과 보호 규칙이 필수**. 실데이터 검증은 사용자가 네이버에 다시 로그인한 뒤(OTP·캡차는 사용자만 가능) |

## 4. 설계
### 4.1 이력 저장 (L7, 신규 `ai_orchestrator/persistence/cafe_membership_store.py`)
- 정상 수집이 끝날 때마다 스냅샷 `data/cafe/my_cafes_history/<UTC 시각>.json`(카페 id·이름·clubid만, 값·쿠키 없음)을 남기고 `my_cafes.json` 은 기존 형식 그대로 갱신(호환).
- 이력은 최근 90건까지 유지.

### 4.2 변동 계산 (L1, 신규 `ai_orchestrator/domain/cafe_membership_diff.py`, 순수 함수)
- 기준 키 `cafe_id`(= cafeUrl slug). `new`(이번에만 있음) / `left`(이전에만 있음) / `renamed`(같은 id, 이름 변경) / `unchanged` 개수.
- **보호 규칙(비교하지 않고 경고만, 이력·저장본을 덮어쓰지 않음):**
  ① 이번 결과가 비었는데 이전엔 있었다(로그인 만료 의심) ② 결과가 화면 읽기(`source=dom`)로 대신한 것(추천·최근 방문 혼입 가능) ③ 이전 대비 **절반 이상 감소**(대량 탈퇴 단정 금지 — 사용자 확인 후에만 반영) ④ 중복 id.
- 첫 수집(이전 없음)은 "기준선 생성"으로 기록하고 신규·탈퇴를 만들지 않는다.

### 4.3 API (응답 키 추가만, 새 라우트 1개)
- `POST /naver-cafe/collect-my-cafes` 응답에 `changes: {baseline, new[], left[], renamed[], total, previous_total, warning}` 추가(기존 `ok/count/cafes` 불변).
- `GET /naver-cafe/my-cafes/changes?limit=` 신규(읽기): 최근 변동 이력. 라우트 잠금값(424)에 +1.
- 수집은 기존 `run_on_browser_thread` + **작업 탭 1개를 쓰고 끝나면 닫음**(공유 탭·다른 탭 불간섭). 감사 로그에 `new/left` 개수만.

### 4.4 카페 탭 반영 (L9)
- `MyCafesTab` 에 "변동" 패널: 신규 가입·탈퇴·이름 변경 표, 마지막 수집 시각, 경고 배너(로그인 만료 의심·화면 읽기 대체·대량 감소 시 "확인 후 반영" 버튼). 숫자 요약 카드(총 가입, 이번 신규, 이번 탈퇴, 기준선 이후 순증감).

### 4.5 분석
- 1차(결정적): 총 가입 수 추이(이력), 기간별 신규·탈퇴 개수, 최근 변동 카페 목록 — 이 앱의 코드만으로 계산, **외부 유료 AI API 미사용**.
- 2차(후속, 별도 승인): 변동 카페의 게시글 활동(`new_articles`·`last_update_date` 는 `list_collector` API 에 있음)과 기존 `ai-analyze` 연결.

### 4.6 하지 않는 것
- 카페 **가입·탈퇴 자체의 실행**은 하지 않는다(읽고 기록만). 실제 가입·탈퇴는 사용자가 네이버에서 한 결과를 반영한다.
- 로그인·로그아웃·쿠키 값 접근 없음(세션 보존 원칙).

## 5. 범위·레이어·영향
| 파일 | 레이어 | 변경 |
|---|---|---|
| `ai_orchestrator/domain/cafe_membership_diff.py` | L1 | 신규(순수) |
| `ai_orchestrator/persistence/cafe_membership_store.py` | L7 | 신규(이력 파일) |
| `ai_orchestrator/connectors/naver_cafe_router.py` | L8 | 수집 응답에 `changes`, `/my-cafes/changes` 1개, 빈 결과 덮어쓰기 방지 |
| `scripts/naver/cafe/collection/explorer.py` | L3/L5 | 결과 출처(`source`) 표시, 빈·불완전 시 저장 안 함 |
| `admin-web/.../MyCafesTab.tsx`, `lib/assistant/api.ts` | L9 | 변동 패널 |
| 시험 | L11 | 순수 규칙·저장소·라우터 보호 규칙·UI 타입 |
- DB schema 변경 없음. 기존 응답 키 불변(추가만). 새 .py 는 `registry_sync`.

## 6. 성공 기준
1. 순수 규칙 시험: 신규·탈퇴·이름 변경·기준선·4개 보호 규칙·중복 id.
2. 라우터 시험(가짜 수집기): 빈 결과가 저장본을 덮어쓰지 않음, 이력 90건 제한, 응답 키 호환.
3. 실데이터 드라이 런(로그인 복구 후): 현재 가입 카페 N개 읽기 → 기준선 생성 → 같은 수집 재실행 시 변동 0(안정성).
4. 가입·탈퇴가 실제로 일어난 뒤 재수집하면 해당 카페가 신규/탈퇴로 잡힘(사용자와 함께 확인).
5. `verify_change` 새 문제 0, 라우트 잠금값 +1 반영.

## 7. 선행 조건(사용자)
네이버 재로그인(OTP·캡차는 사용자만 가능). 로그인은 사용자가 9222 Chrome 에서 한 번만 하면 이후 기준선·변동 검증은 AI 가 진행한다. (`로그인 필요 시 파기·재시도 금지` 원칙에 따라 AI 는 로그인 동작을 하지 않는다.)

## 8. 되돌리기
커밋 revert. 이력 폴더는 추가 파일뿐이라 지워도 기존 기능에 영향 없음.
