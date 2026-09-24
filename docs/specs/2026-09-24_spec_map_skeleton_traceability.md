# 기준서 ↔ 코드맵 ↔ 골격 3자 대조 + 합격 조건 실행 (2026-09-24)

```yaml
spec:
  id: spec-traceability
  status: planned
  files:
    add:
      - scripts/ops/spec_trace.py
      - tests/test_spec_trace.py
  acceptance:
    - cmd: python scripts/ops/spec_trace.py --check
      expect: exit0
```

## 목적 (사용자 승인 2026-09-24)
"설계 기준서와 코드맵, 골격 3개가 일치하는지 검증하고 실제 동작이 되는지" — 계획대로 만들었는지까지 기계가 판정한다.
- 기준서 = 무엇을·왜(docs/specs/*.md) / 골격 = 어디에 속하나(configs/module_registry.json, 모듈 카드) / 코드맵 = 실제 파일·연결(data/code_map/map.json).

## ① 기준서 기계용 칸 (`spec:` YAML 블록, 문서 맨 위 코드블록)
| 키 | 뜻 |
|---|---|
| id | 고유 id(파일명과 별개, 커밋 trailer 에서 참조) |
| status | planned / building / done / superseded(대체됨, `superseded_by`) |
| files.add / delete / move{옛:새} / modify | 기준서가 약속한 파일 변화 |
| modules{이름:{layer, uses[], files[glob]}} | 기준서가 정의하는 모듈·층·의존 |
| routes.add / remove | 서버 라우트 약속 |
| acceptance[] | 합격 조건 = 실행 가능한 검사. `{cmd, expect: exit0 / stdout 값 / regex}` 또는 `{grep: 패턴, in: 경로들, count: 0}` 또는 `{pytest: 경로}` |

## ② 대조 규칙 (spec_trace.py) — status 별로 적용
| 대조 | building/done 에서 FAIL |
|---|---|
| 기준서 ↔ 코드맵 | delete 인데 파일 존재 / add 인데 없음 / move 옛 경로 존재·새 경로 없음 |
| 기준서 ↔ 골격 | modules.layer ≠ 정본 층, files[glob] 이 정본 모듈 소속과 다름 |
| 기준서 ↔ 코드맵(연결) | modules.uses 에 없는 모듈로의 실제 import(선언 안 된 연결) |
| 기준서 ↔ 실행 | routes 약속 불일치(서버 라우트 목록), acceptance 명령 실패 |
| 기준서끼리 | done 기준서 2개가 같은 파일·모듈을 서로 다르게 정의(층·소속 충돌) |
| 골격 ↔ 코드맵 | skeleton_gate 결과 재사용(중복 구현 안 함) |
planned 는 대조하지 않음(계획 단계). superseded 는 대체 기준서만 대조.

## ③ 추적(Traceability)
- 코드 파일을 바꾸는 커밋은 메시지 trailer `Spec: <id>` 필수. 예외(CLAUDE.md 즉시실행 예외와 동일): 오타·주석·1줄 수정 → `Spec: trivial`.
- commit-msg 훅이 존재하는 id 인지 확인(없으면 차단). 커밋↔기준서 역색인 → "이 파일은 왜 생겼나" 조회(`spec_trace.py --why <path>`).
- 기존 커밋은 소급하지 않음(시행일 이후만).

## ④ CI 편입
- 자체 CI(docs/specs/2026-09-24_self_hosted_ci_jenkins.md) 파이프라인 단계 "S 기준서 대조": 모든 done/building 기준서의 ②+acceptance 실행. 매 병합·매일.
- 결과는 모듈 대시보드에 기준서별 행으로(약속 N개 중 지켜진 수).

## 드라이런 계획
최근 기준서 4개(OpenAI 삭제, 지도↔골격 게이트, 자체 CI, 허브 분리 1·2단계 — 허브 분리는 기준서 신규 작성)에 spec 블록을 붙여 --check → 불일치 건수 보고. 나머지 7개(과거 기준서)는 status 판단 후 done/superseded 표기, 약속 추출이 어려우면 `legacy: true`(대조 제외, 목록에만).

## 영향
신규 2파일 + commit-msg 훅 1단계. API·DB·보안 영향 없음. 공용 스킬(verify-change)에 포함 — 판매 키트의 "설계→시공→감리" 축.

## 롤백
훅 단계 제거, spec 블록은 문서라 무해.
