# G2B 공개 공고 Read-Only Full Live Execution 설계 문서

작성일: 2026-05-07

---

## 목적

G2B 공개 공고 read-only 흐름을 mock/dry-run 단계를 넘어,
사용자 PC local-agent 브라우저에서 실제 open/read/navigate까지 실행한다.

---

## mock 생략 사유

- 이전 단계(G2B_PUBLIC_NOTICE_WORKFLOW_IMPLEMENTATION_1)에서 domain policy, workflow, dry-run adapter가 완성됨
- 정책 판정이 충분히 검증됨
- mock 없이 실제 공개 URL에 대한 read-only live 실행 단계로 직진

---

## 전체 실행 흐름

```
fixture URL + operation
    ↓
execution gate (build_g2b_readonly_execution_candidate)
    ↓ dry-run adapter 호출
    ↓ policy verdict 확인
    ↓ gate_verdict 판정
        → READONLY_EXECUTION_CANDIDATE: live runner 입력
        → GATE_BLOCKED: 브라우저 실행 없음
        → GATE_NEEDS_VERIFICATION: 브라우저 실행 없음
    ↓
local-agent live runner (run_g2b_public_notice_readonly_live)
    ↓ 서버 환경 체크 (IS_SERVER_ENV → FAIL)
    ↓ gate 결과 재검증
    ↓ playwright open/read
    ↓ final_url 도메인 확인
    ↓ download 이벤트 감지
    ↓ body_text_sample 최대 1000자 truncate
    → verdict: LIVE_PASS / LIVE_WARN / LIVE_FAIL / LIVE_BLOCK
```

---

## local-agent 전용 실행 원칙

- **이번 단계는 mock이 아니다.**
- **공개 read-only URL에 대해 실제 local-agent 브라우저 실행을 수행했다.**
- **서버 브라우저에서 G2B에 접속하지 않았다.**
- `IS_SERVER_ENV=true` 환경에서는 즉시 LIVE_FAIL 반환
- playwright는 사용자 PC에서만 실행됨

---

## 서버 브라우저 금지 원칙

- 서버에서 G2B 브라우저 접속 코드 없음
- 서버는 git pull, 테스트, 배포 상태 확인만 담당
- `server_browser_used` 항상 False

---

## 허용 operation

| operation | 설명 |
|-----------|------|
| read | 페이지 열기 + 내용 읽기 |
| open_url | URL 열기 |
| navigate | 페이지 이동 |

---

## 차단 operation

- click, type, fill, submit, click_submit
- download, upload, post, write, delete
- login, cert, payment, contract, bid_submit, auto_login

---

## gate → live runner 연결 구조

```
build_g2b_readonly_execution_candidate(url, operation)
    → evaluate_g2b_public_notice_dryrun()  # adapter
    → evaluate_g2b_public_notice_execution_gate()  # gate
    → returns candidate dict

run_g2b_public_notice_readonly_live(candidate)
    → IS_SERVER_ENV 체크
    → validate_g2b_execution_gate_result()
    → gate_verdict == READONLY_EXECUTION_CANDIDATE 확인
    → _try_playwright_open_read()
    → final_url 도메인 확인
    → returns live result dict
```

---

## fixture 전체 실행 방식

| fixture verdict | 실행 방식 |
|-----------------|-----------|
| ALLOWED | local-agent 브라우저 live 실행 |
| BLOCKED | gate BLOCK 확인만, 브라우저 실행 없음 |
| NEEDS_VERIFICATION | live 실행 제외, 검증 필요 판정 유지 |

---

## 결과 schema

live runner 결과 필수 필드:

| 필드 | 설명 |
|------|------|
| input_url | 입력 URL |
| canonical_url | 정규화 URL |
| final_url | 실제 브라우저 최종 URL |
| operation | 실행된 operation |
| gate_verdict | gate 판정 |
| execution_allowed | gate 통과 여부 |
| execution_dispatched | 실제 실행 여부 |
| local_agent_required | 항상 True |
| local_agent_used | local-agent 브라우저 사용 여부 |
| server_browser_used | 항상 False |
| download_auto_allowed | 항상 False |
| title | 페이지 제목 |
| body_text_sample | 본문 최대 1000자 |
| body_text_length | 원본 본문 길이 |
| blocked_reason | 차단 사유 |
| error | 오류 메시지 |
| verdict | LIVE_PASS / LIVE_WARN / LIVE_FAIL / LIVE_BLOCK |

---

## 정책 유지

- **login/cert/bid/contract/payment는 계속 BLOCK이다.**
- **click/type/fill/submit/download는 계속 BLOCK이다.**
- **쿠키/session/token/password/otp는 저장하지 않았다.**
- **다운로드는 수행하지 않았다.**
- wildcard *.g2b.go.kr 허용 없음
- DB write 없음

---

## 제한 사항

- playwright 미설치 환경에서는 LIVE_WARN 반환 (local_agent_used=False)
- 서버 환경에서는 항상 LIVE_FAIL

---

## 다음 단계 후보

- ACTION_REGISTRY_PREFLIGHT 연동
- local-agent WebSocket을 통한 dispatch 자동화
- 실제 fixture 전체 live smoke 실행 결과 리포트 축적
