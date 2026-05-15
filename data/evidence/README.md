# Evidence Warehouse (W4)
경로: data/evidence/{domain}/{task_id}/
정책: READ_ONLY_AFTER_CREATION, 불변
역할: 실행 증거, 화면 스냅샷, 결과 첨부파일 해시
금지: 임시 파일 evidence 승격, session/cookie/token 저장, manual_visit 재사용
참조: docs/architecture/shared_warehouse_model.md#W4
