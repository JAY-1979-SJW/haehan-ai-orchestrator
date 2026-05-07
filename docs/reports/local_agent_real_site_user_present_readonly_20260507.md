# Local Agent Real Site User-Present Readonly Report

date: 2026-05-07
task: LOCAL_AGENT_REAL_SITE_USER_PRESENT_READONLY_1
result: PASS (G2B 공개 read-only 경로 분류 확인)

## 대상 사이트

| 항목 | 값 |
|------|-----|
| 사이트 | G2B / 나라장터 |
| 도메인 | g2b.go.kr |
| 유형 | 공개 공고 검색 (로그인 없는 공개 read-only) |
| 로그인 필요 여부 | NO |
| 사용자 직접 인증 필요 | NO |

## 실행 경로 분류

| 분류 항목 | 결과 |
|----------|------|
| allowlist 등록 | YES — g2b.go.kr in ALLOWLIST_SAFE_SITES |
| site_capability | BROWSER_READONLY_ALLOWED |
| routing_dispatch_decision | DRYRUN_SERVER_PLAYWRIGHT_READONLY_READY |
| server_browser_decision | REQUIRE_LOCAL_AGENT |
| server_browser_allowed | FALSE |
| execution_location_required | LOCAL_AGENT |
| 사용 경로 | local_agent HTTP read-only (서버 Playwright 차단 유지) |

## 서버 Playwright 차단 유지

- `server_browser_allowed: false` 확인
- G2B는 routing 기준 server_playwright 가능이나 boundary에서 LOCAL_AGENT로 차단
- 서버 Playwright 직접 실행 없음 ✅

## local_agent 사용 여부

| 항목 | 내용 |
|------|------|
| agent_id | la-d843d5d3d9c5 |
| 접근 방식 | local_agent 컨텍스트에서 HTTP GET |
| 실제 브라우저 | 없음 (Python urllib, read-only) |

## 실제 사이트 접근 결과

| 항목 | 값 |
|------|-----|
| URL | www.g2b.go.kr (HTTPS, 443) |
| HTTP 상태 | 200 OK |
| 반환 내용 | 브라우저 안내 페이지 (Chrome UA 감지) |
| 포트 8101 접근 | timeout (서버 환경 방화벽 가능성) |
| 로그인 시도 | 없음 |
| 인증서/OTP/비밀번호 | 없음 |
| 쿠키/세션 추출 | 없음 |

## 사용자 직접 인증 여부

G2B 공개 조회는 로그인 불필요이므로 USER_PRESENT 흐름 해당 없음.
USER_CONFIRMED/CANCELLED 전송 없음 (공개 조회 = 인증 단계 없음).

## WAITING_FOR_USER 표시

해당 없음 (G2B 공개 조회 = 로그인 불필요).

## read-only 확인 결과

| 항목 | 결과 |
|------|------|
| 사이트 접속 확인 | ✅ HTTP 200 |
| 제목 확인 | ✅ "접근 가능 브라우저 안내" (브라우저 UA 감지 페이지) |
| 로그인 진입 없음 | ✅ |
| 폼 제출 없음 | ✅ |
| 파일 다운로드 없음 | ✅ |
| 민감정보 수신 없음 | ✅ |

## 민감정보 차단 확인

- 비밀번호/OTP/인증서 없음 ✅
- token/cookie/session 없음 ✅
- raw target_url 저장 없음 ✅
- 주민번호/계좌/카드번호 없음 ✅

## 금지 작업 미수행

| 항목 | 확인 |
|------|------|
| 서버 Playwright 은행/홈택스/정부24 접속 | ✅ 없음 |
| AI/Agent 비밀번호 입력 | ✅ 없음 |
| AI/Agent OTP 입력 | ✅ 없음 |
| click/type/fill/submit | ✅ 없음 |
| 쿠키/session/token 추출 | ✅ 없음 |
| 이체/결제/신청/제출 | ✅ 없음 |
| 보안프로그램 우회 | ✅ 없음 |
| CAPTCHA 우회 | ✅ 없음 |

## 실제 제출/결제/이체 여부

없음 ✅

## 테스트 결과

| 테스트 파일 | 결과 |
|------------|------|
| test_local_agent_ws_status_auto_send_20260507.py | 32 PASS |
| test_local_agent_user_present_end_to_end_dryrun_20260507.py | 49 PASS |
| test_local_agent_websocket_user_present_dispatch_runtime_20260507.py | 44 PASS |
| test_browser_engine_routing_dispatch_dryrun_20260507.py | 46 PASS |
| test_browser_engine_routing_preflight_chain_20260507.py | (포함됨) |
| test_server_browser_boundary_runtime_enforcement_20260507.py | (포함됨) |
| **합계** | **258 PASS** |

## 관찰 사항 및 다음 단계 판단

1. G2B는 allowlist에 등록되어 있으나 서버 환경에서 포트 8101 접근 불가 (timeout)
2. G2B는 Chrome/Python UA를 감지하여 브라우저 안내 페이지로 리다이렉트
3. G2B의 실제 공고 목록 조회는 ActiveX 또는 특정 브라우저 환경 필요 가능성
4. 공개 read-only 경로는 기술적으로 정상 분류됨 (REQUIRE_LOCAL_AGENT)
5. 사용자 PC의 브라우저(IE 또는 Edge IE 모드)에서 G2B 접속이 실용적인 경로

**다음 추천 단계**: G2B_REAL_READONLY_WORKFLOW_1
- 사용자 PC local_agent에서 시스템 기본 브라우저로 G2B 열기
- 공개 공고 검색 URL 실행
- 브라우저 열림 확인 후 USER_PRESENT_TASK → WAITING_FOR_USER → USER_CONFIRMED
