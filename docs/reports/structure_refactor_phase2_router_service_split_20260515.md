# Structure Refactor Phase 2 - Router Service Split - 2026-05-15

## 1. 시작 기준

- branch: master
- 시작 HEAD: 06ba822
- server status: clean

## 2. 목표

FAT_SITE_ROUTER 1건 해소: scripts/hiworks/router.py 크기 12000바이트 미만으로 감소.

## 3. 변경 내용

| 파일 | 변경 내용 |
|---|---|
| scripts/hiworks/utils.py | 신규 생성: option_value(), HELP_TEXT 추출 |
| scripts/hiworks/router.py | _option_value 삭제, _print_help 본문 교체, utils import 추가 |

## 4. 결과

| 항목 | 이전 | 이후 | 판정 |
|---|---:|---:|---|
| router.py 크기 | 12026 bytes | 10836 bytes | PASS ✓ |
| FAT_SITE_ROUTER | 1 | 0 | PASS ✓ |
| hiworks 테스트 | 19 pass | 19 pass | PASS ✓ |
| import smoke | OK | OK | PASS ✓ |
| quality gate errors | 0 | 0 | PASS ✓ |
| import cycles | 0 | 0 | PASS ✓ |

## 5. 영향 범위

- API response key 변경: 없음
- DB/schema 변경: 없음
- 기능 변경: 없음
- CLI 명령 이름 변경: 없음
- 서버 재시작: 없음
- 배포: 없음

## 6. 커밋

- 1186f41: refactor(hiworks): extract option_value and HELP_TEXT to utils.py

## 7. 남은 tracked_residuals

| 항목 | 등급 | 다음 단계 |
|---|---|---|
| ROOT_PY_SCRIPT 24건 | P3 | Phase 3: root 파일 정리 |

## 8. 다음 단계 권장

```
STRUCTURE_REFACTOR_PHASE3_ROOT_PY_SCRIPT_01
```

Phase 3 목표: root 레벨 .py 파일 24건 정리 (재배치 또는 archive).
