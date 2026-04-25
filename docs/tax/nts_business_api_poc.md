# 국세청 사업자등록정보 API PoC (TAX-API-1)

> **상태**: PoC (실제 운영 채택 전 점검 단계)
> **선행 문서**: [`docs/design/hometax_automation_strategy.md`](../design/hometax_automation_strategy.md)
> **본 PoC 의 위치**: 전략 문서의 1순위 — 공식 공공데이터 API 우선

---

## 1. 목적

전략 문서(`hometax_automation_strategy.md`)에서 1순위로 정한 “공식 공공데이터 API 로 대체 가능한 자료부터 API 화” 의 첫 구현 PoC. 본 PoC 는:

- 홈택스 화면 자동화 / 브라우저 / 쿠키 / 인증서 / 보안프로그램 을 **건드리지 않는다**.
- 대표님에게 수동 실행을 요구하지 않는다 (CLI 는 운영자/Claude 가 호출).
- 실제 API 키가 없어도 **흐름 점검**(입력 정규화, 100건 가드, 빈 입력 차단)이 가능하다.

## 2. 지원 범위

본 PoC 는 두 가지 호출만 지원한다.

| 기능              | path        | 입력                                       | 비고                     |
| ----------------- | ----------- | ------------------------------------------ | ------------------------ |
| 사업자등록 상태조회 | `/status`   | `b_no` (사업자번호 10자리)                  | 휴/폐업/계속사업자 구분 |
| 사업자등록 진위확인 | `/validate` | `b_no` + `start_dt` + `p_nm` (+ 옵션 필드) | 입력값과 등록정보 일치 여부 |

base URL 기본값:

```
https://api.odcloud.kr/api/nts-businessman/v1
```

본 PoC 는 위 base URL 의 두 path 만 호출한다. 한 호출당 최대 100건(`MAX_BATCH_SIZE`).

## 3. 홈택스 브라우저 자동화와의 차이

| 항목                       | 본 PoC (TAX-API-1)               | 홈택스 브라우저 자동화 (F-4G-3)    |
| -------------------------- | -------------------------------- | ---------------------------------- |
| 인증 방식                  | API 키 (사업자/공공데이터포털)   | 사용자 본인 인증서 + 보안프로그램 |
| 사용자 본인 개입 여부      | 없음                              | 매 세션 본인 로그인                |
| 자동화 가능 여부           | 완전 자동화 가능                  | read-only observe 까지만           |
| 약관 / 보안 위험           | 매우 낮음                        | 보안프로그램/약관 의존성 큼        |
| 적용 대상 자료             | 사업자등록 상태 / 진위확인        | 홈택스 화면 안의 자료 일반         |
| 추천 우선순위              | 1순위                             | 4순위 (폴백)                       |

## 4. 환경변수 설정

| 환경변수                          | 우선순위 | 용도                              | 기본값                                            |
| --------------------------------- | -------- | --------------------------------- | ------------------------------------------------- |
| `NTS_BUSINESS_API_SERVICE_KEY`    | 1순위    | 본 PoC 전용 service_key            | (없음)                                            |
| `PUBLICDATA_SERVICE_KEY`          | 2순위    | 프로젝트 공용 공공데이터 키        | (없음)                                            |
| `NTS_BUSINESS_API_BASE_URL`       | 옵션     | base URL 오버라이드                | `https://api.odcloud.kr/api/nts-businessman/v1` |
| `NTS_BUSINESS_API_TIMEOUT_SECONDS`| 옵션     | HTTP timeout (1.0~60.0)            | `10.0`                                            |

설정 예 (`.env` — **실제 키는 git 에 커밋하지 말 것**):

```dotenv
NTS_BUSINESS_API_SERVICE_KEY=<공공데이터포털에서 발급받은 키 원문>
NTS_BUSINESS_API_TIMEOUT_SECONDS=10.0
```

키 로드 우선순위는 `NTS_BUSINESS_API_SERVICE_KEY` → `PUBLICDATA_SERVICE_KEY` 순이다.

## 5. live 키가 없을 때 동작

- `load_nts_business_api_config()` 는 `live_enabled=False` 인 config 를 반환한다 (예외 없음).
- `check_status(...)` / `validate_businesses(...)` 는 HTTP 호출 없이 다음 형태를 반환한다:

```jsonc
{
  "success": true,
  "mode": "mock_or_disabled",
  "kind": "status",
  "count": 1,
  "items": [],
  "warnings": ["live_disabled_or_no_service_key"]
}
```

- CLI `scripts/check_business_registration.py` 는 `--live` 옵션을 줘도 키가 없으면 **WARN** 으로 종료한다 (FAIL 아님).
- 키 원문은 `redacted()` / 로그 / 출력 어디에도 노출되지 않는다 (`service_key_present` / `service_key_length` 만 노출).

## 6. CLI 사용 예시

```bash
# (1) dry-run — 입력 정규화 / 100건 가드만 점검
python scripts/check_business_registration.py --status 1234567890 --json

# (2) 사업자번호 목록 파일 + live 호출 + JSON 출력
python scripts/check_business_registration.py \
    --status-file samples/business_numbers.txt \
    --live --json

# (3) 진위확인 (validate)
python scripts/check_business_registration.py \
    --validate-json samples/validate_items.json --live --json
```

`--status-file` 형식: 한 줄에 사업자번호 하나 (`#` 로 시작하는 줄은 주석으로 무시).

`--validate-json` 형식 (둘 다 허용):

```json
[
  {"b_no": "123-45-67890", "start_dt": "20200101", "p_nm": "홍길동"}
]
```

또는

```json
{
  "businesses": [
    {"b_no": "1234567890", "start_dt": "20200101", "p_nm": "홍길동",
     "p_nm2": "Hong Gildong", "b_nm": "예시상사", "corp_no": "1101110000000"}
  ]
}
```

CLI 약식 verdict:

- **PASS**: live 모드 + items 1건 이상.
- **WARN**: disabled 모드 또는 live 인데 items=0 (운영 점검 단계에서 정상).
- **FAIL**: success=False (HTTP 오류 등).

## 7. 운영 반영 전 확인사항

본 PoC 가 운영 코드/배포 흐름에 반영되기 전 다음을 확인할 것.

- [ ] 공공데이터포털에서 본 사업자번호 진위확인/상태조회 API 활용 신청이 승인됨.
- [ ] 활용 신청 시점/제공 범위/일일 호출 한도가 운영 부하와 정합함.
- [ ] `service_key` 가 운영 secret store(또는 적절한 .env 보호 채널)에 등록됨 — git/이미지/로그에 평문 노출 금지.
- [ ] 사업자번호 / 대표자명 등 입력값이 회사 내부 데이터의 적법한 처리 범위 안에 있음.
- [ ] 본 API 의 응답을 캐시할 경우, 캐시 TTL / 만료 정책이 정해져 있음 (사업자 상태는 휴/폐업으로 바뀐다).

## 8. 향후 확장

본 PoC 가 안정화되면 같은 패턴(공공데이터/공식 API 우선) 으로 다음을 차례로 검토한다.

- **거래처 DB 검증** — 회사 거래처 마스터에 들어있는 사업자번호 일괄 상태조회.
- **입찰/계약 거래처 상태 리스크 체크** — 계약 직전 진위확인 + 휴/폐업 여부 조회.
- **세금계산서 / 회계자료** — 본 API 범위 밖. ASP / ERP 연동을 별도로 검토 (전략 문서 9.1 의 2순위).
- **세무대리 권한 위임 자료** — 전략 문서 9.1 의 3순위. 법적 위임이 정합한 자료에 한정.

본 PoC 는 “자료 회수” 가 아니라 “거래처 / 사업자 상태 확인” 이 본질이다. 따라서 회계 마감 / 부가세 신고 자료 자동화는 본 PoC 가 아닌 ASP/ERP 검토(2순위)로 분리한다.
