# 자체 CI — Jenkins(틀) + 파이썬 파이프라인(판단) (2026-09-24)

> 2026-09-29 정정: 아래 "GitHub Actions 등은 쓰지 않는다" 결정은 **번복됨**(사용자 승인).
> Jenkins 는 설계만 있고 실제로 설치·구현된 적이 없었다(docs/defect_index.json #4 —
> "CI 없음"). 대신 `.github/workflows/ci.yml` 로 GitHub Actions를 도입, 이 저장소가
> 이미 갖고 있던 "로컬 CI" 도구 `tools/verify_change.py`(기준 대비 새로 생긴
> 문제만 FAIL로 판정)를 그대로 재사용한다. 아래 Jenkins 설계는 실행 이력으로만 남긴다.

## 결정 (사용자, 2026-09-24 — 2026-09-29 번복됨)
- GitHub Actions 등 GitHub 기능은 쓰지 않는다. 오픈소스를 이 PC 에 설치해 자체 운영.
- Jenkins·Buildbot 장점 통합 → **Jenkins 하나를 틀**로, **판단·로직은 전부 우리 파이썬 스크립트**(Buildbot 의 장점). CI 엔진 이중 운영은 하지 않음(결과 분산·중복 구현 방지).
- "느려도 모두 검증" — 병합·일일 실행은 전 모듈 V0~V6 전체. "스크립트로 할 수 있는 건 스크립트로".

## 구조
```
[Jenkins LTS]  대기열·예약·이력·웹 화면(127.0.0.1 전용)·Windows 서비스(창 없음)
   │ Jenkinsfile — 단계마다 python 한 줄 호출만(로직 0)
   ▼
[scripts/ops/ci/run_pipeline.py]  configs/ci_pipeline.json(단계·시간상한·필수여부)
   V0 소속·V1 구조  skeleton_gate / code_map build·modules
   V2 로드          runcheck R0 + 설정·데이터 파일 열기
   V3 입구          runcheck R1(--help) + R2(임시 포트 서버 GET, 위험 이름 제외) + MCP list_tools
   V4 계약·V5 흐름  모듈 카드 기반 계약 테스트·드라이런(외부 게시·발송·결제 금지)
   전체 테스트       pytest 파일별 격리·시간상한(멈춤 = FAIL 기록, 전체 멈춤 없음), 기준선 대비
   V6 실제 사이트    CDP 읽기 전용 점검(세션 만료 → "미실행·재로그인 필요", 병합 보류)
   → data/ci/runs/<sha>.json(판정·단계별 결과·로그) + 모듈 대시보드 HTML + 검증표(md)
   ▼
[로컬 관문]
   merge_stage.py  : CI PASS 기록(<sha>) 없으면 master ff 병합 거부
   pre-push 훅     : master 로 가는 커밋에 PASS 기록 없으면 push 거부(운영 서버가 master 를 가져가므로 = 배포 관문)
```

## 트리거
| 언제 | 무엇 | 범위 |
|---|---|---|
| 커밋 | git 훅(skeleton_gate) — Jenkins 아님 | V0~V1 (수 초) |
| stage/* 브랜치 커밋 | post-commit 훅이 Jenkins 에 작업 등록(로컬 HTTP, 토큰은 로컬 파일) | V0~V6 전체 |
| master 병합 요청 | merge_stage.py → 해당 sha 의 PASS 확인, 없으면 Jenkins 실행 후 대기 | 전체 |
| 매일 1회(새벽) | Jenkins 예약 | master 전체(사이트 변화·세션 만료 감지) |

## 보안·운영 원칙
- Jenkins 는 127.0.0.1 에만 바인딩(외부 접속 불가), 관리자 계정 비밀번호는 로컬 파일(출력 금지).
- 플러그인 최소(Pipeline, Git(로컬 경로), Timestamper 정도). 외부 알림 플러그인 없음.
- 비밀값(.env)은 PC 밖으로 나가지 않음. 로그에 비밀값 출력 금지(기존 redaction 재사용).
- 서비스 실행 계정 = 현재 사용자(크롬 프로필·세션 접근용). 창·터미널 뜨지 않게.
- 자동 실행은 검증만 — 배포·게시·발송·결제·삭제는 CI 에서 절대 실행하지 않음.
- 결과 알림: 기본은 대시보드·검증표만. 텔레그램 알림은 사용자 별도 승인 시.

## 재사용 (신규 최소화)
verify_change.py(전후 비교) · merge_stage.py · skeleton_gate.py · registry_sync.py · code_map/* · runcheck.py · session_probe.
신규: scripts/ops/ci/run_pipeline.py, configs/ci_pipeline.json, Jenkinsfile, 모듈 대시보드 생성기, runcheck R2, 계약·흐름 테스트 생성기(모듈 카드 단계에서).

## 단계 계획
1. 파이프라인 스크립트(run_pipeline + 설정) — Jenkins 없이도 단독 실행 가능하게(Jenkins 는 호출만)
2. Jenkins LTS 설치(winget/공식 msi) · 서비스 등록 · 127.0.0.1 · 초기 설정 — 설치는 사용자 승인 후
3. Jenkinsfile + post-commit 트리거 + 매일 예약
4. 관문: merge_stage PASS 기록 확인 · pre-push master 관문
5. 깨뜨리기: 고장 브랜치 → CI FAIL·병합/푸시 거부 / 정상 → PASS·병합 / 멈추는 테스트 → 해당 파일만 FAIL / 세션 만료 → V6 미실행·보류
6. 공용 스킬(verify-change)에 파이프라인·Jenkinsfile 템플릿 포함 → 다른 폴더 설치

## 확인 사항
- 기존 pre-push(ai_code_review_gate.py)는 Claude Code CLI(구독) 사용 — 유료 API 아님. 관문 추가 시 이 단계 유지.
- Java: OpenJDK 21 설치돼 있음(Jenkins LTS 요구 충족 — 설치 시 재확인).
- PC 가 꺼져 있으면 CI 도 멈춤 → 켜지면 대기열 재개.

## 롤백
Jenkins 서비스 중지·제거, 훅 관문 줄 제거. 파이프라인 스크립트는 단독 실행 가능하므로 CI 없이도 검증 유지.
