# 서버 배포 미반영 문제해결

`git push` 후 GitHub webhook은 202(접수)인데 프로덕션에 새 코드가 안 뜰 때.

## 1) 원격 안전 진단 (로컬에서)
```
python tools/deploy/deploy_diagnose.py
```
- `/health 200` + `/grant-radar/report 404` → 서버가 **구 이미지 실행 중**(재빌드 미완료/실패).
- GitHub webhook 전달 확인: `gh api repos/<owner>/<repo>/hooks/<id>/deliveries`

## 2) 호스트(서버)에서 점검 — 배포 담당자/서버 접속 환경에서
> 이 프로젝트는 **로컬 PC에 Docker 없음** — 아래는 서버 호스트에서만 실행.

- 레포 최신 반영 여부
  - 서버 레포 디렉터리에서 최신 커밋이 origin/master와 일치하는지 확인
  - 불일치 시 `git pull origin master`
- 컨테이너 상태/로그
  - 컨테이너 목록·기동 시각 확인 (재빌드 시각이 push 이후인지)
  - API 컨테이너 최근 로그에서 build/start 에러 확인
  - 필요 시 `docker compose build && docker compose up -d` (SOP)
- 배포 트리거 데몬
  - `deploy_trigger_daemon`(host) 프로세스 동작 여부
  - 환경변수 `DEPLOY_WEBHOOK_SECRET` 설정 여부 (없으면 webhook 503)
  - 데몬 로그에서 push 이벤트 수신·실행 결과 확인

## 3) 자주 발생하는 원인
| 증상 | 원인 | 조치 |
|------|------|------|
| webhook 202인데 미반영 | 데몬 미동작 / 빌드 실패 | 데몬 재기동, 빌드 로그 확인 |
| 빌드 실패로 구 이미지 유지 | 의존성·문법 오류 | 빌드 로그의 첫 에러 수정 후 재빌드 |
| pull은 됐는데 미반영 | 컨테이너 미재기동 | `up -d`로 재기동 |

## 4) 참고
- webhook 엔드포인트: `POST /api/v1/deploy/webhook` (HMAC 서명 검증)
- 데스크톱 앱은 **로컬 번들 FastAPI**를 사용하므로 서버 배포와 무관하게 동작.
