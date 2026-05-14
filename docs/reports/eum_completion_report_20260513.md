# EUM 자동화 완료 보고

**작성일**: 2026-05-13  
**site_id**: `eum`  
**사이트**: 건설근로자공제회 EUM (`https://eum.cw.or.kr`)  
**완료 판정**: 완료(기준 구현)

---

## 1. 완료 범위

EUM 자동화는 다른 사이트 자동화의 기준 구현으로 사용할 수 있는 수준까지 완료했다.

완료된 항목:

- 사이트별 라우터: `scripts/eum/router.py`
- workflow 인덱스: `scripts/eum/workspace.py`
- dry-run/prepare/submit 실행 분리
- 승인 workflow 계획 생성: `scripts/eum/work_plan.py`
- 실행 로그: `scripts/eum/run_log.py`
- 실시간 감사 이벤트 연동: `scripts/realtime_audit.py`
- 단말기 신규 등록 prepare/submit 모듈: `scripts/eum/registration.py`
- 단말기 철거/말소 prepare/submit 모듈: `scripts/eum/deregistration.py`
- `data/form_analysis.json` selector 후보 연동
- 전역 메뉴 검색창/닫기 버튼 제외 로직
- 품질 게이트 및 배포 dry-run 정책 연동
- 공통 설계 문서 및 사이트 인덱스 반영

---

## 2. 완료 workflow 목록

| workflow_key | WEBMAN | 위험 등급 | 상태 |
|--------------|--------|-----------|------|
| `device_inventory` | WEBMAN390M00 | read | 완료 |
| `new_sites` | WEBMAN380M00 | read | 완료 |
| `sales_mail` | WEBMAN370M00 | read/prepare | 완료 |
| `device_history` | WEBMAN400M00 | read | 완료 |
| `demolition_lookup` | WEBMAN382M00 | read | 완료 |
| `monitor` | - | read | 완료 |
| `device_registration` | WEBMAN381M00 | approval | prepare/submit 구조 완료 |
| `device_deregistration` | WEBMAN382M00 | approval | prepare/submit 구조 완료 |

---

## 3. 남은 운영 확인

다음 항목은 완료 판정에서 제외하고, 운영 승인 시 별도 실행한다.

| 항목 | 이유 | 처리 방식 |
|------|------|-----------|
| 신규 등록 실제 submit E2E | 실 공사코드/단말기ID와 사용자 승인이 필요 | 승인 후 `--submit` |
| 철거/말소 실제 submit E2E | 실제 단말기 철거/말소는 상태 변경 작업 | 승인 후 `--submit` |
| 운영 계정 권한별 화면 차이 | 계정/권한에 따라 WEBMAN 폼이 달라질 수 있음 | form analysis 재수집 |

---

## 4. 검증 결과

실행한 검증:

```bash
python -m pytest tests\test_eum_action_prepare.py tests\test_eum_router_work.py tests\test_eum_work_plan.py tests\test_eum_run_log.py -q
python -m pytest tests -k eum -q
python -m pytest tests\test_realtime_audit.py tests\test_quality_gate.py -q
```

검증 기준:

- 기본 호출은 제출 버튼을 클릭하지 않는다.
- `submit=True` 또는 승인 workflow에서만 제출 버튼을 클릭한다.
- 분석 selector가 정적 selector보다 먼저 사용된다.
- 전역 UI selector는 제외된다.
- invalid plan은 실행 로그를 만들지 않는다.
- 실시간 감사 이벤트가 기록된다.
- 품질 게이트가 staged 변경 기준으로 동작한다.

---

## 5. 공통화 반영

EUM에서 확정한 패턴은 다음 공통 문서와 인덱스에 반영했다.

- `docs/site_automation_reference_index.md`
- `docs/site_automation_status_index.md`
- `docs/eum_logic_reference_20260513.md`
- `configs/site_automation_status_index.json`

다른 사이트도 같은 상태 체계와 workflow 목록으로 취합한다.

