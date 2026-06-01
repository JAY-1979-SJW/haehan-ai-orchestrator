# 기준서 — P1(신): 사이트 카탈로그 + 로컬 설정

Status: DRAFT (승인 대기 — 코드 전 설계)
작성일: 2026-06-02
근거: 코드 실측 (`external_work_registry.py`, `sites/router.py`, `sites/registry.py`, `electron/lib/config.js`)
확정 전제: 순수 로컬 per-user (서버 멀티테넌트 폐기) — `TARGET_PRODUCT_ARCHITECTURE.md`

---

## 1. 목표

각 사용자가 **카탈로그에서 자기가 쓸 사이트를 골라 자기 PC에 설정**한다.
서버는 "어떤 사이트를 쓸 수 있는지(카탈로그)"만 제공하고, **선택·설정·자격증명·데이터는 전부 로컬**.

```
서버: 사이트 카탈로그 제공 (읽기)
 PC : 카탈로그에서 선택 → 로컬 config.json 에 저장 → local-agent가 선택된 것만 실행
```

---

## 2. 기존 활용 자산 (새로 안 만듦)

| 자산 | 역할 | P1에서 |
|------|------|--------|
| `ai_orchestrator/external_work_registry.py` | 작업/사이트 분류 카탈로그(ExternalWorkEntry, classification) | **카탈로그 데이터 원천** |
| `ai_orchestrator/sites/router.py` (`/connectors`, `/site-health`) | 사이트 라우터(admin) | 카탈로그 엔드포인트 추가 위치 |
| `ai_orchestrator/sites/registry.py` | 커넥터 등록소(현재 dummy/example만) | 추후 실모듈 연결(선택) |
| `electron/lib/config.js` (`loadConfig/saveConfig/patchConfig`) | 로컬 config.json IO | **로컬 설정 저장소** |
| `scripts/{naver,eum,gabia,youtube,...}` | 실제 사이트 모듈 | 카탈로그 항목의 실체 |

---

## 3. 설계

### 3-1. 서버 — 사이트 카탈로그 엔드포인트 (읽기 전용)
- 신규: `GET /api/v1/sites/catalog`
- 응답: 사용 가능한 사이트 목록 (id, 이름, 설명, 분류, 필요권한, local-agent 필요 여부)
- 출처: `external_work_registry` 의 항목을 사이트 단위로 그룹핑(또는 별도 카탈로그 상수)
- 인증: 로그인 사용자(JWT) — 승인된 사용자만 카탈로그 조회
- 서버는 **사용자가 뭘 골랐는지 저장하지 않음** (순수 로컬 원칙)

예시 응답:
```json
{ "sites": [
  {"id":"naver_smartstore","name":"네이버 스마트스토어","needs_local_agent":true,"category":"commerce"},
  {"id":"eum","name":"건설근로자공제회(EUM)","needs_local_agent":true,"category":"gov"},
  {"id":"gabia","name":"가비아 DNS","needs_local_agent":true,"category":"infra"},
  {"id":"youtube","name":"YouTube","needs_local_agent":false,"category":"content"}
]}
```

### 3-2. 클라이언트 — 사이트 선택·설정 (로컬 저장)
- 화면: 카탈로그 목록 → 토글로 "내가 쓸 사이트" 선택 + 사이트별 설정값 입력
- 저장: Electron `config.json` 에 `enabled_sites`, `site_settings` 키 추가 (patchConfig 사용)
```json
{
  "enabled_sites": ["naver_smartstore", "eum"],
  "site_settings": {
    "naver_smartstore": { "store_url": "...", "...": "..." }
  }
}
```
- **자격증명·세션은 기존 로컬 위치 유지** (`data/cdp_profile`, OS 자격증명 저장소) — config.json에 비밀번호 평문 저장 금지.

### 3-3. local-agent — 선택된 사이트만 실행
- 에이전트 시작 시 로컬 `enabled_sites` 읽어 그 사이트 모듈만 활성화
- 미선택 사이트 모듈은 로드/노출 안 함

---

## 4. 영향 / 보안

| 항목 | 내용 |
|------|------|
| 서버 | 카탈로그 GET 1개 추가. 사용자 선택/데이터 미보관 |
| 로컬 | config.json에 선택·비민감 설정만. 비밀번호 평문 금지(OS 자격증명/기존 위치) |
| 레이어 | sites(L5/L8 라우터) + config(L10) — 위반 없음 |
| 보안 | 카탈로그는 로그인 사용자만. 자격증명 서버 전송 없음(로컬 원칙) |
| DB | 서버 스키마 변경 없음 (카탈로그는 코드 상수/기존 레지스트리) |

---

## 5. 단계별 구현 순서 (승인 후, 각 단계 게이트)

1. ✅ **완료** 서버: `GET /sites/catalog` + 카탈로그 데이터(external_work_registry 그룹핑) + 테스트 (커밋 08b0e19)
2. ✅ **완료** 클라이언트(로컬): `config.js`에 `getEnabledSites/setEnabledSites/getSiteSettings/setSiteSettings`
   - `enabled_sites`(문자열 배열, 중복제거) / `site_settings`(사이트별 병합 저장)
   - 민감 키(`pass|pwd|secret|token|cookie|credential|otp|apikey|private`) 저장 자동 차단(`_stripSensitive`)
   - 기능검증: round-trip·병합·민감키 차단·config.json 평문 미저장 모두 통과
3. 화면: 사이트 선택·설정 UI (카탈로그 fetch → 토글 → 로컬 저장)
4. local-agent: enabled_sites 반영(선택 사이트만 활성)
5. E2E: 카탈로그 조회 → 선택 → 로컬 저장 → 재시작 후 유지 확인

---

## 6. 드라이런 계획

- 카탈로그 엔드포인트: external_work_registry 항목 수 → 사이트 그룹 수 매핑 시뮬레이션
- 로컬 저장: config.json에 enabled_sites 쓰기/읽기 단위 테스트(임시 경로)
- 비밀번호 평문 미저장 검증

---

## 7. 범위 밖 (다음 Phase)
- 설정의 서버 동기화(v2) — 지금은 순수 로컬
- 사용자별 UI 접근(P2), 경량 배포(P4)
