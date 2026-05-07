# G2B 기존 OpenAPI 앱 Bridge Contract

작성일: 2026-05-08

---

## 원칙

### 현재 앱(haehan-ai-orchestrator)의 역할

- 현재 앱은 G2B 공개 공고 데이터의 **소비자/검증자**다.
- 현재 앱은 G2B OpenAPI를 **직접 호출하지 않는다**.
- 현재 앱은 `data.go.kr` API key를 읽거나 저장하지 않는다.
- 현재 앱은 기존 OpenAPI 앱의 DB에 직접 접근하지 않는다.
- 현재 앱은 기존 OpenAPI 앱을 수정하지 않는다.

### 기존 OpenAPI 앱의 역할

- 기존 OpenAPI 앱은 G2B 공개 공고 데이터의 **source of truth**다.
- 기존 OpenAPI 앱이 API key를 소유하고 G2B OpenAPI를 호출한다.
- 기존 OpenAPI 앱이 수집한 결과를 HTTP GET endpoint 또는 파일 산출물로 현재 앱에 제공한다.

### 연결 방식

- 현재 앱은 기존 앱의 **read-only HTTP GET** 또는 **파일 산출물(JSON/CSV)** 만 입력으로 받는다.
- API key 값은 현재 앱 코드에 절대 포함되지 않는다.
- DB write 없음.
- DB direct read 없음.

---

## 현재 endpoint 확인 상태

| 항목 | 상태 |
|------|------|
| 기존 앱 공고 목록 API | **미확정** |
| 기존 앱 공고 상세 API | **미확정** |
| 기존 앱 파일 산출물 경로 | **미확정** |

endpoint가 미확정이므로 이번 단계는 **contract + adapter + fixture + test**까지만 완료한다.  
실제 endpoint probe는 endpoint가 확정된 이후 별도 단계에서 수행한다.

---

## 현재 앱이 요구하는 최소 입력 schema

```json
{
  "source": "existing_g2b_openapi_app",
  "source_mode": "http_get_or_exported_json",
  "api_key_used_by_current_app": false,
  "api_key_value_exposed": false,
  "db_read_direct": false,
  "db_write": false,
  "items": [
    {
      "bid_notice_no": "string",
      "bid_notice_order": "string",
      "notice_name": "string",
      "demand_org": "string",
      "notice_org": "string",
      "posted_at": "string (ISO8601 또는 YYYY-MM-DD HH:MM)",
      "business_type": "string",
      "detail_url": "string | null",
      "raw_detail_url_candidates": ["string"]
    }
  ]
}
```

### 필드 설명

| 필드 | 필수 | 설명 |
|------|------|------|
| bid_notice_no | ✓ | 공고번호 |
| bid_notice_order | ✓ | 공고차수 |
| notice_name | ✓ | 공고명 |
| demand_org | 권장 | 수요기관 |
| notice_org | 권장 | 공고기관 |
| posted_at | 권장 | 게시일시 |
| business_type | 선택 | 업무구분 |
| detail_url | 선택 | 기존 앱이 제공하는 공고 상세 URL |
| raw_detail_url_candidates | 선택 | 기존 앱이 제공하는 URL 후보 목록 |

---

## 기존 앱 응답 → 현재 앱 candidate mapping

```
기존 앱 필드          →  현재 앱 candidate 필드
-------------------------------------------------------
bidNtceNo            →  bid_notice_no
bidNtceOrd           →  bid_notice_order
bidNtceNm            →  notice_name
demandOrgNm          →  demand_org
ntceInsttNm          →  notice_org
bidBeginDt / rgstDt  →  posted_at
bsnsDivNm            →  business_type
ntceDtlUrl           →  detail_url
(없으면)             →  detail_url = null, detail_url_missing = true
```

---

## detail_url 처리 규칙

### detail_url이 있는 경우
1. g2b_domain_policy로 도메인 확인
2. g2b_public_notice_execution_gate로 gate 판정
3. safe: `g2b.go.kr` 또는 `www.g2b.go.kr` 경로 중 read-only 허용 경로
4. blocked: login/cert/bid submit/contract/payment/download 경로
5. needs_verification: shop.g2b.go.kr 등 기타 서브도메인

### detail_url이 없는 경우
- URL을 임의로 생성하지 않는다.
- bid_notice_no + bid_notice_order 기반 URL 패턴 생성은 **공식 확인 후**에만 허용.
- 현재는 `detail_url_missing = true`로 기록한다.

### 절대 금지
- downloadFile.do 경로 자동 실행
- wildcard subdomain 자동 허용
- login/cert/payment/contract URL 생성 및 접속

---

## 오류/미확정 처리

| 상황 | 처리 |
|------|------|
| endpoint 미확정 | contract + test까지 완료, probe 미수행, 최종 판정 WARN |
| 필수 필드 누락 | missing_required_fields에 기록, verdict = WARN |
| detail_url 없음 | detail_url_missing = true, safe_detail_url_candidates = [] |
| detail_url blocked | blocked_detail_url_candidates에 기록, 실행 금지 |
| API key 노출 시도 | 즉시 FAIL, 커밋 금지 |
| DB write 시도 | 즉시 FAIL, 커밋 금지 |

---

## 보안 정책 고정값

- `api_key_used_by_current_app` = `false` (고정)
- `api_key_value_exposed` = `false` (고정)
- `db_read_direct` = `false` (고정)
- `db_write` = `false` (고정)
- `wildcard_domain_allowed` = `false` (고정)
- `download_auto_allowed` = `false` (고정)
- `click_type_fill_submit_blocked` = `true` (고정)
