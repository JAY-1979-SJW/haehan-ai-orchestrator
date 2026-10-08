# EUM 로직 참조 설계

**사이트**: 건설근로자공제회 EUM (`https://eum.cw.or.kr`)  
**작성일**: 2026-05-13  
**상태**: 완료(`complete_baseline`)  
**참조 목적**: EUM에서 확정한 자동화 로직을 저장하고, 다른 사이트 작업 시 재사용할 기준을 남긴다.

---

## 1. 핵심 결정

EUM은 조회 업무와 상태 변경 업무를 분리한다.

| 업무 | WEBMAN | 위험 등급 | 실행 정책 |
|------|--------|-----------|-----------|
| 신규 현장/설치 대상 조회 | WEBMAN380M00 | read | 자동 실행 가능 |
| 단말기 신규 등록 | WEBMAN381M00 | approval | 기본은 prepare, submit은 승인 후 |
| 단말기 철거/말소 | WEBMAN382M00 | approval | 기본은 prepare, submit은 승인 후 |
| 단말기 설치현황 추출 | WEBMAN390M00 | read | 자동 실행 가능 |
| 단말기 이력 조회 | WEBMAN400M00 | read | 자동 실행 가능 |

등록/말소 모듈은 기본적으로 제출하지 않는다. `submit=True` 또는 승인 workflow를 통해서만 최종 버튼 클릭을 허용한다.

완료 보고:

- `docs/reports/eum_completion_report_20260513.md`
- 공통 상태 인덱스: `docs/site_automation_status_index.md`
- 기계 판독용 인덱스: `configs/site_automation_status_index.json`

---

## 2. 현재 구현 저장 위치

| 역할 | 파일 |
|------|------|
| EUM 명령 라우터 | `scripts/eum/router.py` |
| workflow 인덱스 | `scripts/eum/workspace.py` |
| 승인/준비 계획 | `scripts/eum/work_plan.py` |
| 실행 로그 | `scripts/eum/run_log.py` |
| 실시간 감사 | `scripts/common/realtime_audit.py`, `data/logs/realtime_audit.jsonl` |
| 신규 등록 prepare/submit | `scripts/eum/registration.py` |
| 철거/말소 prepare/submit | `scripts/eum/deregistration.py` |
| 폼 분석 | `scripts/eum/form_analyzer.py` |
| 분석 결과 | `data/form_analysis.json` |
| 단위 테스트 | `tests/test_eum_action_prepare.py`, `tests/test_eum_router_work.py`, `tests/test_eum_work_plan.py` |

---

## 3. 실행 흐름

```
사용자 명령
  -> scripts/entry/cdp_cli.py eum <workflow>
  -> scripts/eum/router.py
  -> gate.check()
  -> get_page()로 기존 브라우저/탭 재사용
  -> ensure_logged_in()
  -> WEBMAN 페이지 이동
  -> form_analysis.json 후보 selector 로드
  -> 정적 selector + semantic fill 폴백
  -> prepare 결과 반환
  -> 승인된 submit인 경우에만 최종 버튼 클릭
```

---

## 4. 등록/말소 폼 처리 방식

### 4.1 selector 후보 결합

`registration.py`와 `deregistration.py`는 다음 순서로 입력 필드를 찾는다.

1. `data/form_analysis.json`에서 해당 WEBMAN 코드와 일치하는 분석 결과를 로드한다.
2. 메뉴 검색창, 즐겨찾기 검색창 등 전역 UI selector를 제외한다.
3. field id/name/placeholder/label/type 텍스트가 업무 키워드와 맞는지 확인한다.
4. 분석 selector를 정적 selector 앞에 붙여 우선 시도한다.
5. 실패하면 라벨/부모 텍스트 기반 semantic fill을 시도한다.

### 4.2 버튼 필터링

분석 파일에 버튼이 있어도 다음 버튼은 제출 후보에서 제외한다.

- `닫기`
- `close`
- 전역 모달 닫기 버튼

실제 제출 버튼은 분석 selector와 정적 submit selector를 병합해 찾지만, 기본 prepare 모드에서는 클릭하지 않는다.

### 4.3 실패 처리

필수 필드를 채우지 못하면 다음 형태로 반환한다.

```json
{
  "success": false,
  "prepared": false,
  "submitted": false,
  "fill_errors": ["device_id"],
  "error": "required field fill failed: device_id"
}
```

---

## 5. 승인 workflow

직접 명령:

```bash
python scripts/entry/cdp_cli.py eum registration <project_code> <device_id> [location]
python scripts/entry/cdp_cli.py eum deregistration <device_id> [date]
```

공통 work 명령:

```bash
python scripts/entry/cdp_cli.py eum work registration <project_code> <device_id> <location> --dry-run
python scripts/entry/cdp_cli.py eum work registration <project_code> <device_id> <location> --prepare
python scripts/entry/cdp_cli.py eum work registration <project_code> <device_id> <location> --submit

python scripts/entry/cdp_cli.py eum work deregistration <device_id> [date] --dry-run
python scripts/entry/cdp_cli.py eum work deregistration <device_id> [date] --prepare
python scripts/entry/cdp_cli.py eum work deregistration <device_id> [date] --submit
```

정책:

- `--dry-run`: 계획만 저장하고 사이트 조작 없음
- `--prepare`: 폼 입력까지, 최종 제출 없음
- `--submit`: 계획 검증 후 승인 게이트 안에서만 실행

---

## 6. 다른 사이트에 재사용할 패턴

### 6.1 workflow index

`scripts/<site>/workspace.py`에는 workflow 목록을 둔다.

필수 필드:

```python
{
    "key": "workflow_key",
    "aliases": ["alias", "PAGECODE"],
    "title": "Human readable title",
    "code": "PAGECODE",
    "risk": "read" | "approval",
    "command": "python scripts/entry/cdp_cli.py <site> ...",
    "auto_execute": True | False,
}
```

### 6.2 approval work plan

상태 변경 workflow는 `scripts/<site>/work_plan.py`에서 입력값을 검증하고 JSON 계획을 저장한다.

공통 반환 필드:

```json
{
  "workflow_key": "...",
  "risk": "approval",
  "valid": true,
  "errors": [],
  "inputs": {},
  "steps": [],
  "will_submit": false
}
```

### 6.3 prepare/submit 함수 계약

상태 변경 함수는 다음 결과 계약을 따른다.

```python
{
    "success": True | False,
    "prepared": True | False,
    "submitted": True | False,
    "filled": {},
    "fill_errors": [],
    "error": "",
}
```

기본값은 `submit=False`여야 한다.

### 6.4 테스트 계약

다른 사이트에도 최소 테스트를 둔다.

- 기본 호출은 제출 버튼을 클릭하지 않는다.
- `submit=True`에서만 제출 버튼을 클릭한다.
- 분석 selector가 정적 selector보다 먼저 사용된다.
- 전역 메뉴 검색창과 닫기 버튼은 후보에서 제외된다.
- invalid plan은 실행 로그를 만들지 않는다.

---

## 7. 검증 상태

2026-05-13 기준 통과:

```bash
python -m pytest tests\test_eum_action_prepare.py tests\test_eum_router_work.py tests\test_eum_work_plan.py tests\test_eum_run_log.py -q
python -m pytest tests -k eum -q
```

실제 제출 E2E는 공사코드/단말기ID 실값과 사용자 승인이 필요하므로 문서 작성 시점에는 실행하지 않았다.

실시간 감사/로그 검증:

```bash
python -m pytest tests\test_realtime_audit.py tests\test_eum_run_log.py -q
python scripts/common/realtime_audit.py recent --site eum
python scripts/common/realtime_audit.py tail --text
```
