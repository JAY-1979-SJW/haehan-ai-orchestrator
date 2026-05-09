# BROWSER_ACTION_SAFE_EXPANSION_OPTIN_INTEGRATION_1 보고서 (2026-05-09)

## 1. 작업 목적

LOCAL_BROWSER_POLICY_SAFE_EXPANSION_A1에서 구현한 site/discovery/value/preflight registry를 기존 browser_* 액션과 opt-in 방식으로 연결한다. 기존 동작은 보존하되 `use_policy_registry=True`일 때만 신규 정책 경로 적용.

## 2. opt-in 통합 방식

**Wrapper helper** 방식 채택:
- 기존 4개 액션 파일(browser_prepare_submit, browser_submit_with_user_approval, browser_download_file, browser_attach_file)은 **변경 0건**
- 신규 helper 모듈 `browser_policy_integration.py` 추가
- 5개 wrapper 함수 (open / type / submit / download / attach)
- `use_policy_registry` 키워드 인자가 단일 분기점 (기본 False = LEGACY_BYPASS)

이로써 기존 action_registry / approval_gate / handoff / FastAPI router 모든 코드 변경 없음.

## 3. browser.open 결과

`open_with_policy(site_id, path_key, raw_url, intended_purpose, use_policy_registry)`
- 기본: LEGACY_BYPASS
- opt-in: site_id 또는 등록된 raw_url의 host만 허용
- blocked_paths / 미등록 host / 금지 purpose / execution_location 위반 시 BLOCKED
- 검증 통과 시 `execution_location=LOCAL_AGENT_REQUIRED` 반환

## 4. browser.type 결과

`type_with_policy(selector_key, value_key, raw_text, field_id, business_profile, use_policy_registry)`
- raw_text 또는 raw selector 직접 입력 시 BLOCKED
- value_key + selector_key + field_id 조합만 허용
- password/otp/cookie/session/주민번호/계좌번호 패턴 차단
- value registry의 `allowed_fields` / `allowed_profiles` 강제

## 5. browser.submit 결과

`submit_with_policy(selector_key, selector_label, candidate_type, approval_token, business_profile, use_policy_registry)`
- submit/save/sign/delete/payment/bid/transfer 라벨 = HIGH risk
- approval_token 없으면 차단
- approval 보유 시 `handoff_required=True` 반환 (자동 실행 X)
- raw selector 사용 차단

## 6. browser.download_file 결과

`download_with_policy(source_url, site_id, path_key, candidate_type, selector_label, expected_extension, intended_purpose, use_policy_registry)`
- read-only download_link_candidate는 LOW risk → `auto_approve=True`
- 미등록 host 차단
- 민감 라벨(비밀번호/OTP) 다운로드 차단
- cookie_capture 등 금지 purpose 차단

## 7. browser.attach_file 결과

`attach_with_policy(site_id, file_basename, selector_label, approval_token, submit_after_attach, use_policy_registry)`
- approval_token 없이 attach 차단 (HIGH risk + required_approval=True)
- file_basename에 `/`, `\`, `..` 포함 시 path traversal로 차단
- `submit_after_attach=True`는 분리 승인 정책상 영구 차단
- 미등록 site_id 차단

## 8. preflight 공통 helper 구조

`browser_policy_integration.py`:
- `_normalize_kwargs()` → opt-in flag 추출
- `_verdict()` → 일관된 응답 dict (`ok`, `policy_verdict`, `policy_reason`, ...)
- `_is_destructive_label()` → 라벨 기반 위험 분류
- 5개 wrapper 함수 모두 내부에서 `preflight_expansion()` 호출 → ALLOW/REVIEW/BLOCKED 변환

## 9. 기존 호환성 보존 결과

- 기존 액션 파일 4개 변경 없음
- 기존 action_registry / approval_gate / handoff API 변경 없음
- 기존 FastAPI router 변경 없음
- 전체 회귀 5108 → 5150 (+42 신규 only, 기존 5108 모두 보존)

## 10. 차단된 위험 동작

- raw URL 직접 실행 (미등록 host)
- raw selector 직접 실행
- raw text 직접 입력
- credential / cookie / session / storage_state 입력
- 주민번호 / 계좌번호 원문
- destructive selector(submit/save/sign/delete/payment/bid) 자동 실행
- file path traversal
- attach 후 자동 submit
- 서버에서 외부 브라우저 실행 (helper에 playwright/chromium 호출 0건)
- 금지 purpose (cookie_capture, login_automation, certificate, screenshot)

## 11. 테스트 결과

| 파일 | 테스트 | 결과 |
|---|---|---|
| test_browser_action_policy_registry_optin_20260509.py | 6 | ✅ |
| test_browser_open_policy_optin_20260509.py | 8 | ✅ |
| test_browser_type_policy_optin_20260509.py | 7 | ✅ |
| test_browser_submit_policy_optin_20260509.py | 7 | ✅ |
| test_browser_download_attach_policy_optin_20260509.py | 14 | ✅ |
| **신규 합계** | **42** | **42/42 ✅** |

전체 회귀: **5150 passed, 7 skipped** (이전 5108 → +42).

추가 검증:
- `git diff --check` 통과
- 신규 helper에 playwright/chromium 호출 0건
- DB schema 변경 없음
- 기존 액션 코드 변경 0건

## 12. 남은 작업

- 실제 사이트 (G2B, ERP 등) site registry 등록 + value enum 등록
- 기존 액션 함수 시그니처에 `use_policy_registry` 키워드 직접 추가 (현재는 wrapper만)
- approval_gate 자동 결합 (현재는 token 보유 여부만 확인)
- handoff_payload에 `policy_verdict` 결과 자동 첨부

---

**작업명**: BROWSER_ACTION_SAFE_EXPANSION_OPTIN_INTEGRATION_1
**작성일**: 2026-05-09
**상태**: ✅ 완료
