# 사이트 지도 M9 — 정밀 탐색(데이터 소스·사이트 선언 도구)과 사용자 업무 목록 기준서

작성 2026-10-05 · 창 gongmu-g2 · 상태: **기준서 작성 → 기준서 검증(audit-kit std·arch) → 드라이 런 → 구현**
승인: 사용자(2026-10-05) — ①탐색 중 관측한 데이터 API 구조 기록 ②가입 카페 활동 분석 확장 ③메뉴 색인 상한 조정 + "사이트를 정밀하게 탐색 → 지도로 저장 → 사용자와 업무 목록을 만든다"는 목표에 맞는 개발자 문서 조사.

## 1. 목표
사용자가 지시하는 업무를 하려면 **사이트를 정밀하게 탐색해 지도로 저장하고, 그 지도로 사용자와 함께 업무 목록을 만드는 것**이 핵심이다. 현재 탐색(DOM: 링크·폼·버튼)은 카페 내부처럼 서버가 그린 화면은 상세하게 잡지만, 자바스크립트로 그려지는 앱 화면(예: 카페 포털)은 놓친다(실측: 업무 0개).

## 2. 실측 근거 (2026-10-05, 실계정·읽기 전용)
| 대상 | DOM 탐색 | 네트워크 구조 관측 |
|---|---|---|
| `cafe.naver.com/0moo` | 29쪽, 메뉴 60(상한), 업무 28 | JSON API 0 |
| `section.cafe.naver.com` | **업무 0·메뉴 0**(읽은 쪽 1) | **JSON 데이터 API 11개**(가입 카페 목록·공지·인기글 등), 목록 경로·필드 이름까지 파악 |
| 가입 카페 항목 | — | 24개 필드(새 글 수·마지막 갱신/방문·즐겨찾기·휴면 등) |

## 3. 개발자 문서 조사 (공식 자료, 2026-10-05 확인)
| 출처 | 확인한 내용 | 이 기준서에의 반영 |
|---|---|---|
| Chrome DevTools Protocol — Network 도메인 (chromedevtools.github.io/devtools-protocol) | `requestWillBeSent`·`responseReceived` 이벤트에 **리소스 종류**(XHR·Fetch·Document 등)가 포함된다 | 탐색 중 XHR/Fetch 응답만 골라 데이터 소스로 기록(§4-A) |
| Playwright 문서 (playwright.dev) | 이벤트로 네트워크 응답을 받을 수 있고, `page.ariaSnapshot()` 은 접근성 트리를 YAML 로 준다(`boxes` 옵션은 AI 소비용) | 응답은 핸들러에서 **모으기만** 하고 로드 뒤 읽는다(핸들러 안 동기 호출은 이동을 멈춘다 — 실측). 접근성 스냅샷은 M10 후보 |
| Claude 플랫폼 문서 — Browser use tool (platform.claude.com) | 페이지는 **접근성 트리를 먼저** 읽고(참조가 레이아웃 변화에 강함) 스크린샷은 캔버스·가상 목록·교차 출처 iframe 에서만 쓴다. 오래된 참조는 다시 읽는다. 페이지 글자·URL·콘솔·네트워크 로그는 **신뢰할 수 없는 입력**이며 비밀값(URL 속 토큰)은 **가려서** 돌려준다. `navigate` 는 http/https 만 허용하고 `javascript:`·`file:`·`data:`·`chrome:` 거부, 리다이렉트 뒤에도 허용 목록 재확인. 결과가 큰 읽기는 깊이·부분 트리로 제한 | 데이터 소스에는 **쿼리 값·토큰·응답 값을 저장하지 않는다**(§4-A). 모든 기록 문자열은 정리·길이 제한. 이동 호스트·스킴 검증은 기존 규칙(M7·M8) 유지 |
| Chrome WebMCP (developer.chrome.com/docs/ai/webmcp, 조기 미리보기) | 사이트가 `<form toolname tooldescription>` (선언형) 또는 `document.modelContext.registerTool` (명령형) 로 **에이전트용 도구를 스스로 선언**한다. 브라우저가 폼을 JSON Schema(`inputSchema`)로 바꾼다. 선언형 제출은 사용자가 직접 눌러야 하며(`toolautosubmit` 예외) `agentInvoked` 로 구분. 문서에 "논의 중이며 변경될 수 있음" | 사이트가 선언한 도구가 있으면 **가장 정확한 업무 목록**이다 → 있으면 읽어서 기록한다(탐지만, 실행하지 않음)(§4-B) |
| W3C WAI-ARIA 랜드마크 | 메뉴·본문 영역 구분 | M7·M8 에서 이미 사용(전역 메뉴·메뉴 색인) |

## 4. 설계 (M9 구현 범위)
### A. 데이터 소스 기록 (`data_sources`)
- 탐색이 쪽을 읽는 동안 **GET + XHR/Fetch + HTTP 200 + JSON** 응답의 **구조만** 기록한다: 호스트·경로(긴 숫자·16진 조각은 `{id}` 로 치환), 쿼리 **키 이름만**(값 불저장), 최상위 키, 목록 경로(`a.b.c`)·건수·항목 필드 이름(최대 12개), 관측 횟수. **응답 값·쿠키·토큰·헤더 저장 금지**.
- 수집 방식: `page.on("response")` 핸들러는 응답 객체를 **모으기만** 하고(동기 호출 금지 — 이동이 멈춘다), 쪽 로드와 짧은 대기 뒤 읽는다. 쪽당 최대 60개 응답·본문 1MB 초과는 건너뜀·지도 전체 최대 80개 소스.
- 지도에 **추가 키** `data_sources: [{host, path, query_keys, lists:[{path,count,fields}], seen}]` — 기존 키·API 응답 형태 불변. 같은 소스는 합치고 건수는 최대값 유지.
- 조회 응답(`lookup`)에 요약(`data_sources` 상위 20개 + 총 개수)을 더해 AI 가 "이 사이트에는 가입 카페 목록 API 가 있다"를 알 수 있게 한다. 실행(재호출)은 이번 범위 밖(M10).
- 읽기 전용: 탐색은 이미 GET 이동만 한다. 관측만 하며 요청을 만들지 않는다.

### B. 사이트 선언 도구 탐지 (`declared_tools`, WebMCP)
- 쪽을 읽을 때 선언형(`form[toolname]` + `tooldescription`·필드 `toolparamdescription`) 을 DOM 에서 읽고, 명령형은 `document.modelContext?.getTools` 가 있을 때만 호출해 **이름·설명·입력 스키마**를 기록한다(없으면 조용히 건너뜀).
- **실행하지 않는다**(탐지만). 이름·설명은 사이트가 정한 글자라 **자료일 뿐 지시가 아니다** → `clean_label`·길이 제한. 지도에 추가 키 `declared_tools`.
- 현재 대부분 사이트에 없을 것이므로 비용이 거의 없고, 생기면 즉시 가장 정확한 업무 목록 후보가 된다.

### C. 가입 카페 활동 분석 확장
- 수집 항목에서 **활동 필드만** 스냅샷에 더한다: 새 글 수(`articleNewCounts`)·마지막 갱신/방문일·즐겨찾기·관리·휴면·파워 여부·공개 형태(`openType`). 이미지 주소·썸네일·광고 정보 등은 저장하지 않는다.
- 분석(결정적 계산): 새 글 많은 카페 상위 5, 휴면 카페 수, 최근 N일 방문 없는 카페 수, 즐겨찾기 수. 외부 AI 미사용.
- 카페 탭 변동 패널에 "활동 분석" 카드 추가(응답 키 추가만).

### D. 메뉴 색인 상한
- `MENU_MAX` 60 → 200. 지도에 `menu_total_seen`(상한과 무관한 관측 총수)을 기록해 잘렸는지 알린다. 조회 응답의 표시는 기존대로 질문과 맞는 30개 우선 + 총수 표시.

### E. 사용자 업무 목록 (사용자 화면)
- 사이트 지도 화면에 **"업무 목록"** 구역을 만든다: 업무를 조회·입력·제출로 묶어 이름·목적·검증 상태·위험 등급을 보여 주고, 사용자가 목적·이름을 적어 확정한다(기존 `classify` API 재사용). 그 아래 **메뉴 색인 개수(잘림 표시)·데이터 소스 목록·사이트 선언 도구**를 보여 주어 사용자가 "이 사이트에서 무엇을 할 수 있는가"를 한눈에 본다. 새 라우트 없음(기존 `GET /site-map/{host}` 응답의 추가 키 사용).

## 5. 범위·레이어·영향
| 파일 | 레이어 | 변경 |
|---|---|---|
| `ai_orchestrator/domain/site_map_sources.py` (신규) | L1 | 데이터 소스·선언 도구의 정리·병합·마스킹 순수 규칙 |
| `ai_orchestrator/domain/site_map_menu.py` | L1 | 상한 200, `menu_total_seen` |
| `ai_orchestrator/domain/site_task_map.py` | L1 | (필요 시) 조회 요약 |
| `scripts/explorer/page_snapshot.py` | L3/L4 | 응답 수집(핸들러는 모으기만)·선언 도구 읽기 |
| `scripts/explorer/task_mapper.py` | L3/L4 | 소스·도구 병합 |
| `ai_orchestrator/services/site_task_map_service.py` | L6 | lookup 에 데이터 소스 요약 |
| 가입 카페: `cafe_membership_diff/store/service`·`explorer.py` | L1/L6/L7/L5 | 활동 필드 스냅샷·분석 |
| `admin-web/src/app/site-map/*`, `.../cafe/tabs/MyCafesChangesPanel.tsx`, `lib/*/api.ts` | L9 | 업무 목록 구역·활동 분석 카드 |
- 새 라우트·DB·schema 변경 **없음**(응답 키 추가만). 쓰기·제출 실행 경로 변경 없음(read 전용 유지, M6-b 와 무관).
- 보안: 값 불저장·쿼리 값 불저장·긴 숫자/16진 경로 조각 마스킹·문자열 정리·길이 제한·건수 상한. 쿠키·토큰·헤더 접근 없음.

## 6. 성공 기준 (채점)
1. 순수 규칙 시험: 경로 마스킹(`/cafes/12345` → `/cafes/{id}`)·쿼리 값 제거·목록 구조 요약·병합(건수 최대값)·상한·선언 도구 정리(길이·제어문자).
2. 실제 헤드리스 브라우저 시험(가짜 사이트): XHR JSON 을 부르는 SPA → 데이터 소스가 잡힘, 핸들러 안 동기 호출 없이 이동 정상, 선언형 `form[toolname]` 탐지, JSON 아닌 응답·POST·비200 제외.
3. 가입 카페: 활동 필드 스냅샷·분석(상위 5·휴면·미방문), 이미지 주소 등 불필요 필드 미저장, 기존 변동 비교 불변.
4. 실사이트(승인된 카페 포털 재탐색): `data_sources` ≥ 10개, 값 불저장 확인(지도 JSON 에서 값 검색 0건), 메뉴 `menu_total_seen` 기록.
5. 회귀: 기존 지도·카페 시험 통과, `verify_change` 새 문제 0(시험용 9222 가드 병합 전까지 브라우저 계열은 보류), 라우트 수 불변(425).
6. 기준서 검증: audit-kit `std`(개발 기준서 조항)·`arch` 검사에서 이번 변경 파일의 새 위반 0.

## 7. 비범위 (M10 후보)
- 데이터 소스 **재호출 실행**(`data.read`)과 접근성 스냅샷(`ariaSnapshot`) 기반 보조 신호, 오래된 참조 재읽기, WebMCP 도구 **실행**.
- 쓰기·제출 업무 실행(M6-b, 사용자 본인 확인 대기).

## 8. 드라이 런
저장소 코드 수정 없이 시제품(저장소 밖)으로: ①카페 포털 로드 중 관측 응답을 §4-A 규칙으로 정리해 지도에 들어갈 모양(값 없는 구조)을 보고 ②사이트의 `form[toolname]`·`document.modelContext` 유무 확인 ③가입 카페 활동 필드의 분석 수치(이름 없이 집계만).

## 9. 되돌리기
커밋 revert. 지도 JSON 은 추가 키만 생겨 되돌려도 유효.

## 10. 출처
- Chrome DevTools Protocol Network 도메인: https://chromedevtools.github.io/devtools-protocol/1-3/Network/
- Playwright Snapshot testing(aria snapshots): https://playwright.dev/docs/aria-snapshots
- Claude 플랫폼 문서 Browser use tool: https://platform.claude.com/docs/en/agents-and-tools/tool-use/browser-use-tool
- Chrome WebMCP: https://developer.chrome.com/docs/ai/webmcp/declarative-api · https://developer.chrome.com/blog/webmcp-epp
- 변경 이력: 2026-10-05 초안.
