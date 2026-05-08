# Action Registry & User Approval Gate — Phase 1

작성일: 2026-05-08

## 정책 변경

`제출/투찰/전자서명 기능 자체는 개발한다`로 정책 변경. 단, 사용자 승인 게이트 + 사전 요약 + 사후 evidence를 강제한다.

## 액션 등록표

| 액션 | 위험 등급 | 사용자 승인 | 사전 요약 | 1차 구현 |
|------|-----------|-------------|-----------|----------|
| `browser.download_file` | AUTO_ALLOWED | ❌ | ❌ | ✅ |
| `browser.attach_file` | USER_DELEGATED | ✅ | ✅ | ✅ |
| `browser.prepare_submit` | AUTO_ALLOWED | ❌ | ❌ | ⏳ |
| `browser.submit_with_user_approval` | USER_DIRECT | ✅ | ✅ | ⏳ |
| `bid.prepare_bid` | AUTO_ALLOWED | ❌ | ❌ | ⏳ |
| `bid.submit_with_user_approval` | USER_DIRECT | ✅ | ✅ | ⏳ |
| `esign.prepare_signature` | AUTO_ALLOWED | ❌ | ❌ | ⏳ |
| `esign.execute_with_user_approval` | USER_DIRECT | ✅ | ✅ | ⏳ |

✅ = 1차 구현 / ⏳ = 등록만, 미구현(향후 작업)

## 모듈 구조

```
ai_orchestrator/local_agent/
  action_schemas.py             ActionSpec dataclass + 8개 액션 정의
  action_registry.py            register/get_handler + helpers
  user_approval_gate.py         1회용 + 만료 + scope-bound 승인
  action_summary_builder.py     사전 review 요약 (URL/path/cert sanitize)
  action_evidence_collector.py  사후 evidence + redaction
  actions/
    __init__.py
    browser_download_file.py    1차 구현 (AUTO_ALLOWED)
    browser_attach_file.py      1차 구현 (USER_DELEGATED + 토큰 검증)
    future_action_stubs.py      6개 향후 액션 stub
```

## User Approval Gate 핵심 보장

| 보장 | 메커니즘 |
|------|----------|
| 1회 사용 | `verify_and_consume_token`이 즉시 EXHAUSTED 처리 |
| 만료 시간 | `expires_at`(default 5분, max 30분) 검증 |
| Scope 이탈 차단 | `params_hash`(SHA256) 검증 — 다른 params로 같은 토큰 사용 불가 |
| 액션 이탈 차단 | `action_name` 일치 검증 — 다른 액션으로 토큰 재사용 불가 |
| 민감 키 차단 | password/otp/cert_password/cookie/session/storage_state 자동 sanitize |

## Summary/Evidence 정책

**사전 요약 (사용자 review용):**
- URL은 `host+path`만 (query token 제거)
- 파일 경로는 `basename`만 (full path 제거)
- 인증서 정보는 `subject_name`만 (serial/private_key 제거)
- 비밀번호/OTP는 절대 포함 안 됨

**사후 evidence:**
- `saved_safe_path`, `screenshot_path_safe` 등 `_safe` 접미사로 표시
- 7개 safe field 강제 False (`server_browser_used` 등)
- raw HTML/원문 저장 금지

## 테스트

| 파일 | 케이스 | 결과 |
|------|--------|------|
| test_action_registry_and_schemas_20260508 | 19 | PASS |
| test_user_approval_gate_20260508 | 15 | PASS |
| test_action_summary_and_evidence_20260508 | 17 | PASS |
| test_phase1_actions_20260508 | 15 | PASS |

**합계 66/66 PASS, 전체 회귀 4842 passed, 0 failed.**

## 향후 작업 (미구현 6개 액션)

각 액션의 핸들러는 `actions/` 아래 별도 모듈로 추가 + `register_handler` + `ActionSpec.implemented=True`로 변경. registry는 미구현 액션의 핸들러 등록을 거부하므로 안전하게 분기 가능.
