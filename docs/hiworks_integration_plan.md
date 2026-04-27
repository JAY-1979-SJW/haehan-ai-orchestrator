# Hiworks 공식 API 연동 — 1단계 골격 계획

> 본 문서는 Hiworks(하이웍스, 가비아) 그룹웨어와의 연동 1단계 골격을 기술한다.
> 비공식 스크래핑/자동 로그인 방식은 채택하지 않는다.
> 모든 호출은 공식 OpenAPI / OAuth 절차를 거친 뒤에만 활성화된다.

---

## 1. 원칙

- **공식 API 우선** — Hiworks 공식 개발자 포털(`https://developers.hiworks.com` 추정,
  실제 URL 은 앱 등록 시점에 확정)에서 발급된 자격증명/엔드포인트만 사용한다.
- **비공식 스크래핑 금지** — Playwright/Selenium 으로 사용자 화면을 자동
  조작하는 방식은 1단계 범위에서 제외. 약관·보안정책·CSRF 토큰 회전 이슈
  때문에 장기적으로 위험하다.
- **자격증명 하드코딩 금지** — 모든 시크릿은 환경변수(`.env`) 로만 주입.
  소스/문서/로그/테스트 데이터에 평문으로 저장하지 않는다.
- **읽기 전용** — 1단계는 조회 API 만 사용. 메일 발송, 전자결재 기안, 스케줄
  변경 등 상태 변경 호출은 전부 차단(`HiworksClient.request` 가 `GET` 만 허용).
- **dry_run 기본값** — `HIWORKS_DRY_RUN=true` 가 기본. 실제 외부 호출은 공식
  앱 승인 + 토큰 발급 + 권한 부여가 모두 끝난 뒤에 단계적으로 허용한다.

---

## 2. 앱 등록 / 사전 검수 필요 사항

| 단계 | 필요 작업 | 책임 | 비고 |
|------|----------|------|------|
| 1 | Hiworks 개발자 포털 계정 생성 | 운영자(skyjwshin@gmail.com) | 회사 도메인 관리자 권한 필요 |
| 2 | 앱 등록 (OAuth 클라이언트) | 운영자 | redirect URI / scope 사전 정의 |
| 3 | 오피스 단위 권한 동의 | 오피스 관리자 | 조직/구성원/근태 등 scope 별 동의 |
| 4 | 검수/심사 (있을 경우) | 가비아 측 | 일부 scope 는 심사 대상 |
| 5 | 토큰 발급 | 운영자 | 만료/갱신 정책 확인 |
| 6 | 운영 시크릿 보관 | 운영자 | `.env` 또는 시크릿 매니저 (커밋 금지) |

**개인용 vs 오피스 단위 API 구분**
- *개인용 API* — 개인 사용자가 자신의 데이터(내 메일/일정)에 접근할 때.
  보통 OAuth 2.0 user-consent 흐름.
- *오피스 단위 API* — 회사 전체 조직/구성원/근태 등 통합 데이터에 접근.
  오피스 관리자 동의 + 별도 토큰 (`HIWORKS_OFFICE_TOKEN`) 필요.

본 1단계는 **오피스 단위 조회** 가 주 목적 (`collect_org_units` 등).

---

## 3. 환경변수

`.env.example` 참조. 실제 값은 절대 커밋하지 않는다.

| 키 | 용도 | 예시(형식만) |
|----|------|-------------|
| `HIWORKS_BASE_URL` | API base URL | `https://api.hiworks.com` |
| `HIWORKS_CLIENT_ID` | OAuth 클라이언트 ID | (앱 등록 후 발급) |
| `HIWORKS_CLIENT_SECRET` | OAuth 클라이언트 시크릿 | (앱 등록 후 발급) |
| `HIWORKS_OFFICE_TOKEN` | 오피스 단위 액세스 토큰 | (관리자 동의 후 발급) |
| `HIWORKS_DRY_RUN` | true=네트워크 차단(기본) | `true` / `false` |

검증: `HiworksConfig.has_credentials()` / `require_live(cfg)`.

---

## 4. 1차 수집 범위 (read-only)

| collector | 목적 | 예상 endpoint(placeholder) |
|-----------|------|---------------------------|
| `collect_my_profile` | 토큰 보유자 본인 정보 검증 | `GET /v1/me` |
| `collect_org_units` | 부서/팀 트리 | `GET /v1/org/units` |
| `collect_org_members` | 조직 구성원 목록 | `GET /v1/org/members?unit_id=` |
| `collect_attendance_summary` | 근태 요약 | `GET /v1/attendance/summary?user_id=&period=` |

엔드포인트는 공식 문서 확인 후 `hiworks_collectors.ENDPOINTS` 만 갱신한다.
호출자(상위 모듈/라우터)는 시그니처를 바꾸지 않아도 된다.

---

## 5. Postman / HTTP 테스트 흐름

1. `.env` 에 발급된 자격증명 주입.
2. `HIWORKS_DRY_RUN=true` 상태에서 collector 호출 → 요청 요약(헤더 키/파라미터 키)만 검증.
3. `HIWORKS_DRY_RUN=false` + 단일 endpoint 만 화이트리스트로 풀고 Postman 으로 동등 호출 비교.
4. 응답 스키마가 `CollectorResult.items` 매핑과 일치하는지 확인.
5. 차이가 발견되면 `_from_response` 의 매핑 한 곳만 수정.

테스트에서는 `HiworksClient(transport=fake_transport)` 로 의존성 주입,
실제 네트워크 미사용.

---

## 6. 추후 확장 범위 (단계 정의)

| 단계 | 범위 | 추가 보호 장치 |
|------|------|---------------|
| 2단계 | 메일 헤더/메타 조회 (본문 제외) | scope 최소화, 본문 다운로드 별도 승인 |
| 3단계 | 일정/예약 조회 | 개인정보 마스킹 후 캐시 |
| 4단계 | 전자결재 — 진행상태 조회 (기안/수정/반려 금지) | approval gate + audit log |
| 5단계 | 메신저 알림 발송 (단방향) | 발송 대상/문구 화이트리스트 + dry_run 우선 |

각 단계 진입 시 본 문서에 `## N단계 — 활성 일자 / 승인자 / scope` 항목을 추가한다.

---

## 7. 보안/감사 정책

- 응답 본문 / 토큰 / 헤더 원문은 **로그 금지**. `request_summary` 는 헤더 *키*
  와 파라미터 *키* 만 남긴다.
- 토큰은 `HiworksConfig.redacted()` 로만 렌더링.
- 모든 collector 결과는 추후 `audit_logger` 로 흘려보내되, items 내부의 PII 는
  필요 최소한으로 축약(설계 단계).
- 운영 환경에서 `HIWORKS_DRY_RUN=false` 로 전환할 때는 운영자가 의도적으로
  플래그를 내리는 것 외 자동 전환 경로를 두지 않는다.
