# LOCAL-FILE-MAP-AUTO-CONTROL-2 운영 감사 보고서

**생성 일시**: 2026-05-03 15:28:27
**종합 판정**: WARN

---

## 감사 결과

| 항목 | 상태 |
|------|------|
| 모듈화 | PASS |
| 보안 | PASS |
| Component | PASS |
| Smoke (dry_run) | PASS |
| Audit/Rollback | WARN |
| Ops 모니터링 | PASS |

---

## Smoke 테스트 결과

**상태**: PASS

**상세**: {"fixtures_created": true, "fixtures_preserved": true, "dry_run_enforced": true, "file_moves": 0, "deletions": 0, "api_calls": {"dry_run_true": 1, "dry_run_false": 0}, "checks": {"no_actual_moves": true, "no_deletions": true, "dry_run_only": true, "fixtures_safe": true}}

---

## Audit/Rollback 검증

**상태**: WARN

- Audit JSONL: False
- Rollback Manifest: False
- 자동 Rollback: 0

---

## Ops 모니터링

**건강성**: PASS

- 총 실행: 0
- dry_run=true: 0
- dry_run=false: 0
- HTTP 500: 0

---

**최종 판정**: WARN
**검증 시점**: 2026-05-03T15:28:27.781836
