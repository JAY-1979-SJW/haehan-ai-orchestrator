# scripts/archive

1회용 탐색/분석/디버그 스크립트 보관소. 코드 보존 규칙에 따라 삭제하지 않고 이동만 함.

- 정식 진입점은 `scripts/{eum,google,naver,kakao,g2b,smartstore}/` 패키지.
- 여기 파일들은 **참고용 / 히스토리 자료**. 새 작업에서 import 금지.

## 분류

| 폴더 | 내용 |
|------|------|
| `eum_legacy/` | 루트에 있던 EUM 1회성 추출/탐색/대시보드 스크립트 |
| `explore/` | 사이트/페이지/메뉴 1회 탐색 스크립트 |
| `debug/` | `_*`, `debug_*`, `diagnose_*`, `audit_*`, `verify_*`, `test_*` 진단용 |
| `poc/` | COM 자동화 PoC (cad/excel/hwp) |
| `one_off/` | build/generate/validate/run/probe/smoke 1회 실행용 |
| `misc/` | 모니터/세션 트래커/세팅 등 그 외 |

## 복구

기능이 다시 필요하면 정식 패키지로 통합 후 archive에서 제거.
