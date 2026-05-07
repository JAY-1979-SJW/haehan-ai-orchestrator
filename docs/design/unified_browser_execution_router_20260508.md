# 통합 브라우저 실행 라우터 설계 문서

작성일: 2026-05-08

## 개요

사이트별 전용 도구를 만들지 않는다.
모든 사이트(나라장터/홈택스/은행/카드/보험/일반 웹)는 공통 실행 엔진을 사용한다.
사이트별 차이는 domain profile과 security signal로만 관리한다.

## 실행 흐름

```
task 입력 검증
  → domain profile 조회
  → execution location 1차 분류
  → BLOCKED → 차단 사유 반환
  → USER_DIRECT_ONLY → 사용자 직접 수행 안내
  → LOCAL_REQUIRED → local_agent_handoff 생성
  → SERVER_ONLY / SERVER_FIRST (dry-run) → safe result 반환
  → server_result 있는 경우:
      → security signal 감지
      → fallback 판정 (COMPLETE / RETRY / HANDOFF / USER_DIRECT / BLOCK)
      → safe result 안전성 검증 후 반환
```

## 모듈 목록

| 모듈 | 역할 |
|------|------|
| `execution_location_policy.py` | action/site_category 기반 실행 위치 1차 분류 |
| `domain_profile_registry.py` | 도메인별 정책 프로필 (데이터, 코드 아님) |
| `security_signal_detector.py` | 페이지 text/URL/HTTP status에서 보안 신호 감지 |
| `fallback_decision_engine.py` | 서버 결과 + 신호 → 다음 실행 위치 판정 |
| `local_agent_handoff.py` | 로컬 에이전트 전달 패키지 생성 (민감 데이터 없음) |
| `unified_browser_safe_result.py` | 결과 스키마 (고정 안전 필드 포함) |
| `unified_browser_task_schema.py` | 입력 검증 및 안전 task 빌드 |
| `unified_execution_router.py` | 메인 라우터 (위 모듈 조합) |

## 실행 위치 상수

- `SERVER_FIRST`: 서버 우선, 실패 시 fallback 가능
- `SERVER_ONLY`: 서버 전용 (내부 처리)
- `LOCAL_REQUIRED`: 처음부터 로컬 에이전트
- `SERVER_TO_LOCAL_FALLBACK`: 서버 시도 후 로컬 전환
- `USER_DIRECT_ONLY`: 사용자가 직접 수행
- `BLOCKED`: 자동화 전면 금지

## 보안 고정 원칙

- 쿠키/session/password/OTP/인증서 수집 없음
- 투찰/서명/결제/제출 자동화 없음
- wildcard domain 등록 불가
- local_agent_handoff는 항상 `readonly=True`
- safe result에 민감 필드 고정 False

## 도메인 프로필

등록된 도메인만 특성 적용. 미등록 도메인은 conservative 기본값.

| 도메인 | 카테고리 | 기본 실행 | 로그인 실행 | fallback |
|--------|----------|-----------|------------|---------|
| g2b.go.kr | government_procurement | SERVER_FIRST | LOCAL_REQUIRED | 가능 |
| www.g2b.go.kr | government_procurement | SERVER_FIRST | LOCAL_REQUIRED | 가능 |
| hometax.go.kr | government_tax | LOCAL_REQUIRED | LOCAL_REQUIRED | 불가 |
| www.hometax.go.kr | government_tax | LOCAL_REQUIRED | LOCAL_REQUIRED | 불가 |
| (미등록) | unknown | SERVER_FIRST | LOCAL_REQUIRED | 가능 |

## 테스트 현황

- `test_execution_location_policy_20260508.py`: 17 테스트
- `test_domain_profile_registry_20260508.py`: 14 테스트
- `test_security_signal_detector_20260508.py`: 15 테스트
- `test_fallback_decision_engine_20260508.py`: 17 테스트
- `test_local_agent_handoff_20260508.py`: 16 테스트
- `test_unified_browser_safe_result_20260508.py`: 14 테스트
- `test_unified_execution_router_20260508.py`: 16 테스트

총 112 테스트, 전체 통과.
