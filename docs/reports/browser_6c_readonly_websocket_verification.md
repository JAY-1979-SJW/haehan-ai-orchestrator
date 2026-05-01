# BROWSER-6C: 운영 WebSocket read-only 연결 검증 성공

**Date**: 2026-05-01  
**Status**: ✓ PASS  
**Scope**: WebSocket read-only probe 검증, in-memory agent registry 확인

## 목표

운영 API의 WebSocket 엔드포인트에 probe agent를 통해 read-only 방식으로 연결하여:
- 실제 WebSocket 통신 가능성 확인
- agent registration이 in-memory registry에 정상 반영되는지 검증
- task 실행 없이 auth/heartbeat/clean close 검증

## 진행 순서

### 1. BROWSER-6C-PREP-1: Probe agent in-memory 등록
- 별도 Python process에서 register_agent() 호출 (임시 방식)
- agent_id: la-016b39a36de6, la-45c70951ce4d (재호출)
- device_token 원문 보호
- **결론**: 별도 process는 running API와 격리됨 → 방식 변경 필요

### 2. BROWSER-6C-PREP-2: Running API process 인식 여부 검증
- PREP-1 방식의 한계 발견: 별도 process의 메모리는 running API process와 분리됨
- docker exec python import 확인 결과 _agents dict empty
- **결론**: HTTP registration endpoint로 다시 진행

### 3. BROWSER-6C-AUTH-1: HTTP Basic Auth 준비
- http_users.json 생성 (probe-admin-browser-6c / admin role)
- 경로: ./secrets/api/http_users.json
- 권한: 600 (read-only mounted to /run/secrets/api)
- docker-compose 설정: 
- _load_users()는 매 요청마다 파일 read → 컨테이너 재시작 불필요

### 4. BROWSER-6C-PREP-3-RETRY: Running API registration endpoint
- HTTP POST /api/v1/local-agents/register
- Basic Auth: probe-admin-browser-6c (HTTP 200)
- **등록 결과**: agent_id=la-2e2bae490e1b
- device_token 원문은 ~/.secrets/haehan-ai-orchestrator/probe_ws.env에만 저장
- **결론**: HTTP 200 응답으로 등록 성공

### 5. BROWSER-6C-RETRY-2: WebSocket read-only 실제 연결
- Endpoint: ws://127.0.0.1:8400/api/v1/local-agents/ws
- Probe script: scripts/probe_local_agent_ws_readonly.py
- 환경변수: PROBE_WS_URL, PROBE_AGENT_ID, PROBE_DEVICE_TOKEN (원문 비노출)

## 최종 검증 결과



**판정**: ✓ PASS

## 보안 준수 결과

| 항목 | 상태 | 비고 |
|------|------|------|
| Secret 원문 출력 | ✓ none | device_token, password 미출력 |
| DB write | ✓ none | in-memory 등록만 수행 |
| Browser 실행 | ✓ none | probe read-only 모드 |
| Task 생성 | ✓ none | task_received=False |
| Result 전송 | ✓ none | result_sent=False |
| Approval 변경 | ✓ none | read-only 연결 |
| WebSocket 재연결 | ✓ none | 1회만 수행 |
| 컨테이너 재시작 | ✓ none | 불필요 (파일 read 방식) |

## 남은 주의사항

1. **In-memory registry 휘발성**
   - 컨테이너 재시작 시 등록된 agent 정보 소실
   - 실운영 환경에서는 DB persistence 필수

2. **Probe 계정/Secret 관리**
   - probe-admin-browser-6c 계정은 임시 테스트 용도
   - 실운영 환경에서는 TTL/만료 정책 수립 필요
   - 현재 device_token은 ~/.secrets에만 저장 (local machine 기준)

3. **Multi-worker 환경 검증**
   - 현재 single worker로 테스트 (Uvicorn 1 instance)
   - multi-worker 환경에서는 worker별 메모리 분리로 인한 불일치 가능

4. **Probe script 권한**
   - scripts/probe_local_agent_ws_readonly.py는 repo 내부
   - 다음 단계에서 실행 환경 (local machine vs server) 확정 필요

## 다음 단계

### BROWSER-6D: AUTO_EXECUTE_VIA_AGENT 정합성 수정
- browser.* actions 추가 후 schema 버전 업데이트 필요
- LOCAL_AGENT_TASK schema 확인 및 capability 검증
- PREP-3 방식으로 agent 재등록 후 실제 task 실행 검증

### 실운영 전 요구사항
1. Agent registry DB persistence (migration 필요)
2. Probe 계정 lifecycle 관리 (생성/만료/재생성)
3. WebSocket heartbeat interval 모니터링
4. Multi-worker 환경에서의 registry 동기화 방식
5. Docker compose 단일화 (edge/haehan-app 통합)

## 참고

- Repo: /home/ubuntu/apps/haehan-ai-orchestrator
- Branch: master (HEAD b19869d)
- Verified: 2026-05-01 14:35 UTC+9

