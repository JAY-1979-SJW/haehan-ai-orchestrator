# G2B 기존 OpenAPI 앱 Bridge 보고서

실행일시: 2026-05-08

---

## OpenAPI 직접 호출 미구현 확인

- 현재 앱(haehan-ai-orchestrator)에 G2B OpenAPI 직접 호출 코드 없음
- `data.go.kr` API client 신규 구현 없음
- API key/env/secret 접근 없음
- 기존 OpenAPI 앱 수정 없음
- 기존 앱 DB 직접 접근 없음

## 기존 앱 Endpoint 확인 상태

| 항목 | 상태 |
|------|------|
| 공고 목록 API | **미확정** |
| 공고 상세 API | **미확정** |
| 파일 산출물 경로 | **미확정** |

endpoint 미확정으로 실제 probe 미수행. contract + fixture + test 완료.

## Bridge Adapter 결과 (synthetic sample 기준)

- source_mode: exported_json
- item_count: 5
- normalized_candidates: 5
- safe_detail_url_candidates: 2
- blocked_detail_url_candidates: 1 (downloadFile.do)
- needs_verification_candidates: 0
- detail_url_missing_count: 2
- missing_required_fields_count: 1 (notice_name 누락 케이스)
- verdict: WARN_MISSING_FIELDS
- bridge_verdict: BRIDGE_HAS_SAFE_CANDIDATES
- CONTENT_VALID_PASS 임의 생성: 없음

## 정책 준수

- api_key_used_by_current_app: False (고정)
- api_key_value_exposed: False (고정)
- db_read_direct: False (고정)
- db_write: False (고정)
- wildcard_domain_allowed: False (고정)
- download_auto_allowed: False (고정)
- click_type_fill_submit_blocked: True (고정)

## 테스트 결과

- 신규 bridge 테스트: 27 PASS
- 신규 contract 테스트: 14 PASS
- content validator 테스트: 29 PASS
- valid URL discovery 테스트: 20 PASS
- actual live mode 테스트: 20 PASS
- live execution 테스트: 50 PASS
- host proof 테스트: PASS (포함)
- import contamination regression 테스트: 12 PASS
- workflow/domain policy 테스트: 128 PASS
- 총계: 전체 PASS

## 다음 단계

- 기존 OpenAPI 앱의 read-only HTTP endpoint 확정 후 실제 probe 수행
- endpoint 확정 시 `tests/fixtures/g2b_public_notice_existing_source_candidates_20260508.json` 업데이트
- safe detail URL 확보 후 local-agent actual-live read + content validator 검증
