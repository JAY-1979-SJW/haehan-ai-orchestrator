# 하이웍스 완료 보고

작성일: 2026-05-13  
site_id: `hiworks`  
완료 판정: `complete_baseline`

## 완료 Workflow

| workflow | 상태 | 증적 |
| --- | --- | --- |
| `dashboard` | 완료 | `scripts/hiworks/explorer.py`, `scripts/hiworks/router.py` |
| `apps` | 완료 | `data/hiworks_apps_latest.json` 저장 경로 |
| `mail` | 완료 | read-only 메일 화면 동작 목록 |
| `compose` | 완료 | `data/hiworks_compose_page_latest.json` 저장 경로 |
| `service_scan` | 완료 | `data/hiworks_service_surfaces_latest.json`, 17개 업무 서비스 표면 구조 |
| `action_catalog` | 완료 | `data/hiworks_action_catalog_latest.json`, 17개 섹션 입력/버튼 분류 |
| `prepare_section` | 완료 | `data/hiworks_section_prepare_plan_latest.json`, 모든 섹션 prepare 계획 |
| `submit_section` | 완료 | 승인+확인문구 후 1회 실행 경로, `data/hiworks_submit_section_latest.json` 증적 |
| `prepare_sales_mail` | 완료 | fill-only, `sent=False` 저장 |
| `send_batch_plan` | 완료 | dry-run 계획, `send_status=not_sent` |

## 승인 대기

- 실제 메일 발송은 미구현이며 승인 게이트 대상이다.
- batch send는 반드시 dry-run 계획을 먼저 생성해야 한다.
- 결재 상신, 일정 등록, 게시글 작성, 주소록 추가, 예약 신청, 근무/경비 신청, 파일 업로드, 업무 생성, SMS/쪽지 발송 등 상태 변경 버튼은 `submit_section` 승인 게이트 뒤에서만 실행한다.
- 승인 실행에는 `--approved --confirm=HIWORKS_APPROVED_SUBMIT`가 모두 필요하다.
- 공식 Hiworks API 연동은 별도 트랙으로 남긴다.

## 검증

검증 명령과 결과:

```powershell
python -m pytest tests\test_hiworks_actions.py tests\test_hiworks_service_explorer.py tests\test_hiworks_mail_batch.py tests\test_hiworks_workflows.py tests\test_hiworks_run_log.py tests\test_login_detector_realtime.py -q
python -m py_compile scripts\hiworks\actions.py scripts\hiworks\service_explorer.py scripts\hiworks\router.py scripts\hiworks\schemas.py scripts\login_detector.py scripts\cdp_client.py
python scripts\cdp_client.py hiworks actions all
python scripts\cdp_client.py hiworks prepare-section all --dry-run
python scripts\cdp_client.py hiworks submit-section approval approval:button:4 --approved --confirm=HIWORKS_APPROVED_SUBMIT --dry-run --approved-by=codex-check
python -c "import json; json.load(open('configs/site_automation_status_index.json', encoding='utf-8')); print('json ok')"
python scripts\deploy_dry_run.py -- python -B scripts\quality_gate.py --staged --enforce
python scripts\quality_gate.py --staged --enforce
python scripts\ops\worktree_change_index.py
```

- Hiworks action/service/workflow/login targeted tests: `21 passed`
- Hiworks action/service/login modules: `py_compile` 통과
- Hiworks action catalog CLI: 17개 섹션 처리 완료
- Hiworks prepare-section CLI: 17개 섹션 dry-run 계획 저장 완료
- Hiworks submit-section approved dry-run: `approval:button:4` matched `작성하기`, clicked `False`, submit_executed `False`
- JSON config: `configs/site_automation_status_index.json` 파싱 통과
- Deploy dry-run evidence: `data/logs/deploy_dry_run_latest.json`, status `ok`
- Staged quality gate: errors `0`, warnings `0`
- Worktree change index: `data/worktree_change_index_latest.json` 갱신

## 공통 인덱스 반영

- `configs/site_automation_status_index.json`
- `docs/site_automation_status_index.md`
- `docs/site_automation_reference_index.md`
- `docs/hiworks_logic_reference_20260513.md`
