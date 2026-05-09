# LOCAL_BROWSER_POLICY_SAFE_EXPANSION_A1 보고서 (2026-05-09)

## 1. 작업 목적

기존 보안 정책을 완화하지 않고, AI가 로컬 브라우저를 더 넓게 조작할 수 있도록 **정책 내 자유 확장** 구조를 구축한다.

핵심 원칙:
- 자유자재 ≠ 아무거나 허용
- 자유자재 = 후보 발견 → 정책 통과 항목만 자동 등록 → 점진 확대

## 2. browser.free_mode를 만들지 않은 이유

- raw URL/raw selector/raw text 직접 실행 시 보안 우회 위험
- credential/session/cookie 자동 추출 가능성 증대
- 기존 approval_gate, evidence_policy, business_profile_policy 정책과 충돌
- 대신 site/value/discovery registry + preflight로 동일한 자유도 확보 가능

## 3. site registry 구조

`ai_orchestrator/local_agent/browser_site_registry.py`

`SitePolicy` (frozen dataclass):
- site_id, label, allowed_hosts, allowed_paths, blocked_paths
- allowed_purposes
- execution_location = `LOCAL_AGENT_REQUIRED` (서버 실행 영구 차단)
- login_mode = `PUBLIC_READONLY` / `USER_PRESENT_ONLY` / `USER_PRESENT_AFTER_LOGIN`
- credential_policy = `NO_CREDENTIAL_CAPTURE`
- capture_policy = `NO_SCREENSHOT_NO_HAR`
- allowed_actions / blocked_actions (기본 blocked: submit/save/sign/delete/payment/bid/transfer)
- risk_level, requires_approval, notes

함수:
- `register_site`, `get_site`, `resolve_url(site_id, path_key)`, `validate_raw_url`
- raw URL 직접 실행 시 등록된 host에 한해서만 통과

## 4. discovery candidate 구조

`ai_orchestrator/local_agent/browser_discovery_candidates.py`

9개 candidate 타입: menu / page_title / field / table_header / button / file_input / download_link / submit_button / destructive_button

`DiscoveryCandidate` (frozen dataclass):
- visible_label, role, normalized_text
- selector_fingerprint (sha256 16자) — raw selector 저장 금지
- confidence, risk_hint
- source_site_id, source_path_key

금지 필드 자동 차단: raw_html, raw_selector, screenshot, har, cookie, session, storage_state, localStorage, password, otp, private_key, cert_password, outer_html, inner_html

라벨 차단: password/비밀번호/otp/인증번호/주민번호/계좌번호 등은 후보 생성 자체 차단.

## 5. selector resolver 정책

기존 `selector_pack_registry.py` + `generic_selector_discovery.py`를 확장 없이 재사용.
신규 `browser_discovery_candidates.py`가 `selector_fingerprint`를 통해 raw selector를 차단.

- save / submit / sign / delete / payment / bid / transfer 후보 → HIGH risk → 자동 등록 불가
- read-only menu / page_title / table_header / download_link 후보 → LOW risk → 자동 등록 가능
- confidence LOW → REVIEW_REQUIRED

## 6. value registry 정책

`ai_orchestrator/local_agent/browser_value_registry.py`

`ValuePolicy` (frozen dataclass):
- value_key, label, value_type, sample_safe_value
- allowed_profiles, allowed_fields
- risk_level, source, redaction_policy

value_type 6종: sample_text / sample_number / sample_date / sample_email / safe_masked / user_approved_nonsensitive

차단 (등록/입력 모두):
- password, otp, cert_password, private_key
- cookie, session, storage_state, localStorage, sessionStorage
- access_token, refresh_token, npki
- 주민번호 패턴 `\d{6}-\d{7}`
- 계좌번호 패턴 `\d{3,6}-\d{2,6}-\d{4,8}`

`validate_raw_input()`: raw text 직접 입력 영구 차단 (value_key 사용 강제).

## 7. allowlist expansion preflight 기준

`ai_orchestrator/local_agent/browser_allowlist_expansion_preflight.py`

`preflight_expansion(site_candidate, selector_candidate, value_candidate, action_candidate, business_profile, intended_purpose, raw_url_attempt, raw_selector_attempt, server_external_browser_attempt)` →

verdict:
- `ALLOW_REGISTER` : 자동 등록 가능
- `REVIEW_REQUIRED` : 사용자 검토 필요
- `BLOCKED` : 영구 차단

응답 필드: verdict, reason, blocked_reason, risk_level, required_approval, registry_patch, warnings.

## 8. 자동 승인 가능 조건 (STEP 7)

- read-only page metadata discovery
- 메뉴명 / 버튼명 / table header / file input / download link 후보 수집
- safe registry 후보 생성

조건: `ALLOW_REGISTER` + `risk_level == LOW` + `required_approval == False`

## 9. 자동 승인 불가 조건

- 저장 / 제출 / 상신 / 전자서명 / 투찰 / 결제 / 송금 / 삭제
- 개인정보 입력 / 금액 확정 / 파일 실제 업로드 / 외부 기관 제출

## 10. 차단된 위험 동작

- 서버에서 외부 브라우저 실행
- raw URL 직접 실행 (등록되지 않은 host)
- raw selector 직접 실행
- raw text 직접 입력 (value_key 미사용)
- credential 관련 후보 (password, otp, cert_password, private_key)
- cookie / session / storage_state / localStorage / sessionStorage
- 주민번호 / 계좌번호 원문
- 민감 라벨 후보 (비밀번호, OTP, 주민번호 등)
- screenshot / HAR 저장
- 금지 목적 (cookie_capture, login_automation, certificate, screenshot 등)

## 11. 테스트 결과

신규 5개 파일, 65개 테스트:

| 파일 | 테스트 | 결과 |
|---|---|---|
| test_browser_site_registry_policy_20260509.py | 11 | ✅ |
| test_browser_discovery_candidates_20260509.py | 18 | ✅ |
| test_browser_selector_resolver_policy_20260509.py | 8 | ✅ |
| test_browser_value_registry_policy_20260509.py | 14 | ✅ |
| test_browser_allowlist_expansion_preflight_20260509.py | 14 | ✅ |
| **신규 합계** | **65** | **65/65 ✅** |

전체 회귀: **5108 passed, 7 skipped** (이전 5032 → +76).

추가 검증:
- `git diff --check` 통과
- 신규 모듈에 외부 브라우저 실행 코드 없음 (playwright/chromium 호출 0건)
- DB schema 변경 없음 (in-memory dict)
- 운영 데이터 write 없음
- 민감 키워드는 차단 리스트로만 사용

## 12. 남은 작업

- STEP 9 점진 통합: 기존 `browser_*` 액션이 신규 registry/preflight를 호출하도록 옵트인 통합
- site registry에 실제 업무 사이트 점진 등록 (G2B, ERP 등)
- value registry에 enum sample 점진 등록
- preflight를 거친 selector_pack의 자동 promotion (selector_pack_registry로 전환)
- approval_gate에 `can_auto_approve` 자동 통합 (현재는 helper 함수만 제공)

---

**작업명**: LOCAL_BROWSER_POLICY_SAFE_EXPANSION_A1
**작성일**: 2026-05-09
**상태**: ✅ 완료
