# 운영 배포 안전 주의사항

## 1. docker compose config — 운영 보고/로그 사용 금지

`docker compose config`는 `.env` 포함 전체 환경 변수를 **평문으로 stdout 출력**한다.
운영 로그, CI 리포트, 배포 보고서에 이 명령의 출력을 포함하면 secret 값이 노출된다.

**허용:**
```bash
docker compose config --services   # 서비스 이름 목록만 출력 (env 값 없음)
docker compose ps                   # 컨테이너 상태 (env 값 없음)
```

**금지:**
```bash
docker compose config               # env 값 평문 출력 — 운영 보고 사용 금지
docker compose config > report.txt  # 로그 파일에 env 값 저장 — 금지
```

## 2. docker inspect — env 값이 아닌 key만 출력

컨테이너에 주입된 환경 변수 확인 시 값(value)이 아닌 키(key) 이름만 출력한다.

**허용 (key만):**
```bash
docker inspect <container> --format '{{range .Config.Env}}{{println .}}{{end}}' \
  | sed 's/=.*//'
# 출력 예: DATABASE_URL
#          API_KEY
#          AUTH_ENABLED
```

**금지 (값 포함):**
```bash
docker inspect <container> --format '{{.Config.Env}}'
# 출력 예: [DATABASE_URL=postgres://user:pass@host/db ...]  ← secret 노출
```

## 3. secret-safe 자동 점검 스크립트

`scripts/check_compose_safe.sh`를 사용한다.

- `docker compose config --services`만 호출
- env key 이름만 출력 (`=` 이후 값 제거)
- health endpoint curl 확인
- 금지 패턴(`PASSWORD=`, `TOKEN=` 등) 자체 검사

실행:
```bash
bash scripts/check_compose_safe.sh 2>&1 | tee /tmp/compose_check.log
# 로그 파일에 secret 값이 없는지 검사
grep -P '(PASSWORD|TOKEN|SECRET|DATABASE_URL|API_KEY)=[^=]' /tmp/compose_check.log \
  && echo "FAIL: secret 값 노출" || echo "PASS: secret 값 미노출"
```

## 4. volume project명 불일치 경고

**증상:**
```
WARNING: Volume "haehan-ai-orchestrator-api-storage" already exists
but was created for project "haehan-ai-orchestrator-api"
```

**원인:**
- compose 실행 경로(프로젝트명)가 volume 최초 생성 시점과 다를 때 발생
- 예: 초기 경로 `/haehan-ai-orchestrator-api/`에서 생성 → 이후 `/haehan-ai-orchestrator/`에서 실행

**판단 기준:**
이 경고 자체는 **운영 장애 아님**. 다음 조건이 모두 충족되면 즉시 rollback 불필요:

| 항목 | 정상 기준 |
|------|-----------|
| 컨테이너 상태 | `Up N seconds (healthy)` |
| health endpoint | `200 OK` + `{"status":"ok"}` |
| import smoke | 모든 모듈 import OK |
| 스토리지(storage) | 읽기/쓰기 정상 |

**금지 조치:**
- volume rename 금지 (데이터 손실 위험)
- volume recreate 금지 (데이터 손실 위험)
- `docker compose down -v` 금지
- 위 조치는 **별도 서면 승인** 후에만 검토 가능

## 5. rollback 검토 조건

rollback은 다음 **실패** 상황에서만 검토한다.

| 상황 | 조치 |
|------|------|
| health endpoint 5xx 또는 timeout | 즉시 보고, 수동 rollback 검토 |
| import smoke 실패 | 즉시 보고, 수동 rollback 검토 |
| 컨테이너 crash 재시작 루프 | 즉시 보고, 수동 rollback 검토 |
| `docker compose ps` STATUS = Exited / Restarting | 즉시 보고, 수동 rollback 검토 |

**rollback 사유 아님:**
- volume project명 불일치 경고 (WARN)
- 로그에 DEBUG/INFO 출력
- compose 파일 내 주석 변경

## 6. 금지 패턴 목록 (secret leak 검사)

다음 패턴이 값(value) 형태로 로그/보고서에 출력되면 즉시 해당 파일 삭제 후 FAIL 처리:

```
PASSWORD=
PASS=
TOKEN=
SECRET=
DATABASE_URL=
API_KEY=
PRIVATE_KEY=
ACCESS_KEY=
REFRESH_TOKEN=
```

키 이름 목록만 출력하는 경우(값 없음)는 허용:
```
ENV_KEYS: DATABASE_URL API_KEY AUTH_ENABLED   ← 허용
DATABASE_URL=postgres://...                   ← 금지
```

---

**작성일**: 2026-04-27  
**적용 대상**: haehan-ai-orchestrator 운영 배포 전 안전 점검
