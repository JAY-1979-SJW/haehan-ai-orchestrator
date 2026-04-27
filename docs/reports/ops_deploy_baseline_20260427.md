# 운영 배포 기준선 — 2026-04-27

## 1. 최종 운영 상태

| 항목 | 값 | 비고 |
|------|-----|------|
| 서버 | haehan-app (1.201.176.236, user ubuntu) | SSH alias: haehan-app (haehan-mcp ❌) |
| 실제 운영 경로 | `/home/ubuntu/apps/haehan-ai-orchestrator` | docker-compose.yml 관리 경로 |
| 현재 운영 HEAD | `4bbf61f` | Merge pull request #4 |
| PR #3 | `15529c6` | feature/local-agent-capture-clean merge |
| PR #4 | `4bbf61f` | hotfix/agent-action-registry-import merge |
| docker service | haehan-ai-orchestrator-api | image: haehan-ai-orchestrator-api:local |
| container status | Up (healthy) | 3+ min uptime |
| port binding | 127.0.0.1:8400→8400 | 외부 공개 금지, reverse proxy 경유 |
| health | 200 OK | `{"status":"ok","service":"haehan-ai-orchestrator"}` |
| import smoke | PASS | agent.action_registry/policy/approval_policy/app/task_executor |
| requirements.txt | ✓ 변경 없음 | pip install 재실행 불필요 |
| .env | ✓ 변경 없음 | 신규 키 추가 없음 |
| DB migration | ✓ 없음 | 스키마 변경 없음 |
| systemd services | ✓ 무영향 | dashboard/monitor 독립 운영 |

## 2. 실제 운영 경로

### 정식 경로
```
/home/ubuntu/apps/haehan-ai-orchestrator
```
- `docker-compose.yml` 소재지
- `docker inspect` 기준 `working_dir`
- PR #3, #4 hotfix 반영 경로

### 사용 금지 / 정리 후보 경로
```
/home/ubuntu/apps/haehan-ai-orchestrator-api
```
- **즉시 삭제 금지**
- docker compose 프로젝트로 실행 중이던 legacy path (Stage 8C-4 초기 권장)
- HEAD: 4bbf61f (pull 완료, 동일 커밋)
- 용도: 문서 권장 기준선, 실제 운영 전환 전 테스트 경로
- **정리 기준**: Stage 8C-4R 이후 용도 확인 → 별도 승인 후 삭제 검토

### 주의: 경로 혼동 방지
- `docker-compose build/up` 반드시 **`/home/ubuntu/apps/haehan-ai-orchestrator`** 에서만 실행
- 잘못된 경로에서 build하면 이미지 이름 충돌 발생 (container name reuse error)

## 3. 표준 배포 명령

### 사전 확인
```bash
ssh haehan-app
cd /home/ubuntu/apps/haehan-ai-orchestrator

# 브랜치 및 HEAD 확인
git branch --show-current  # 출력: master
git rev-parse --short HEAD # 현재 커밋

# 원격 상태 fetch
git fetch origin

# 로컬 vs 원격 차이 확인
git status --short         # 출력: 빈 라인 (clean)
git rev-list --left-right --count HEAD...origin/master
# 출력 형식: ahead behind (예: "0 17" = 0 ahead, 17 behind)
```

### 배포 실행
```bash
# FF-only pull (merge 불가, rebase 불가)
git pull --ff-only origin master

# HEAD 확인
git rev-parse --short HEAD

# 컨테이너 build (새 이미지 필요 시)
docker compose build ai-orchestrator-api

# 컨테이너 up (재생성 포함)
docker compose up -d ai-orchestrator-api
```

### 배포 후 검증
```bash
# 헬스 확인 (3초 대기 후 진행)
sleep 3
curl -fsS http://127.0.0.1:8400/api/v1/health
# 기대: {"status":"ok","service":"haehan-ai-orchestrator"} (200 OK)

# 컨테이너 상태
docker compose ps
# 기대: STATUS = Up N seconds (healthy)

# 로그 (최근 120줄)
docker compose logs --tail=120 ai-orchestrator-api
```

## 4. 금지 명령

| 명령 | 이유 |
|------|------|
| `docker compose down` | 네트워크·volume 제거로 cascade 영향 |
| `docker stop/rm <container>` | systemd 관리 네트워크 차단 가능성 |
| `docker cp` | 보안, 파일 버전 추적 불가 |
| `scp` | 금지 사항과 동일 |
| 컨테이너 내부 직접 수정 (docker exec -it /bin/bash 편집) | 배포 폐기 시 변경 소실, 추적 불가 |
| `vi /home/ubuntu/apps/.../env` | 환경 변수 직접 변경 시 이미지 rebuild 필요 불명확 |
| 잘못된 경로 `/haehan-ai-orchestrator-api/`에서 build/up | 컨테이너 이름 충돌 |

**자동 실행 금지:**
- 장애 시 자동 rollback, auto-remediate 스크립트
- 모든 수정은 수동 승인 후 단계별 진행

## 5. 배포 전 체크리스트

```bash
cd /home/ubuntu/apps/haehan-ai-orchestrator

# 1. 브랜치 확인
[ "$(git branch --show-current)" = "master" ] || exit 1

# 2. 로컬 변경 없음
[ -z "$(git status --short)" ] || exit 1

# 3. 원격 신규 커밋 fetch
git fetch origin

# 4. ahead = 0 확인
ahead=$(git rev-list --left-right --count HEAD...origin/master | cut -f1)
[ "$ahead" -eq 0 ] || exit 1

# 5. health 정상 (현재 서비스)
curl -fsS http://127.0.0.1:8400/api/v1/health || exit 1

# 6. requirements.txt 변경 여부
git diff origin/master -- requirements.txt && echo "WARN: requirements changed" || true

# 7. .env 신규 키 확인
git diff origin/master -- .env.example | grep "^+" | head -5

# 8. DB migration 여부
git diff origin/master -- ai_orchestrator/migrations | head -10 || echo "No migrations"

# 9. rollback commit 기록
echo "Rollback candidates:"
git log --oneline | head -3
```

## 6. 배포 후 체크리스트

```bash
cd /home/ubuntu/apps/haehan-ai-orchestrator

# 1. 컨테이너 상태
docker compose ps
# 기대: Up N seconds (healthy)

# 2. health 200 OK
curl -fsS http://127.0.0.1:8400/api/v1/health
# 기대: {"status":"ok","service":"haehan-ai-orchestrator"}

# 3. 로그 (에러/exception 없음)
docker compose logs --tail=120 ai-orchestrator-api | grep -i "error\|exception" || echo "No errors"

# 4. import smoke
docker compose exec -T ai-orchestrator-api python - <<'PY'
mods = [
    "agent.action_registry",
    "agent.policy",
    "agent.approval_policy",
    "agent.app",
    "agent.task_executor",
]
for m in mods:
    __import__(m)
    print("OK", m)
print("IMPORT_SMOKE_OK")
PY
```

## 7. rollback 기준

### rollback 후보 커밋

| 커밋 | 설명 | 상황 |
|------|------|------|
| `15529c6` | feature/local-agent-capture-clean merge | PR #3 이전 마지막 안정화 |
| `438ae67` | (초기 배포 기준) | 측정 필요 |

### rollback 조건

| 상황 | 조치 |
|------|------|
| health 실패 (500/timeout) | **즉시 보고**, 자동 실행 금지 |
| import smoke 실패 | **즉시 보고**, 자동 실행 금지 |
| 컨테이너 crash 재시작 루프 | **즉시 보고**, 자동 실행 금지 |
| 로그 exception 및 서비스 장애 | **즉시 보고**, 자동 실행 금지 |

### 수동 rollback 절차

```bash
ssh haehan-app
cd /home/ubuntu/apps/haehan-ai-orchestrator

# 현재 HEAD 기록
git rev-parse --short HEAD

# rollback commit으로 reset (--soft 권장, 변경 보존)
git reset --soft 15529c6  # 또는 438ae67

# 확인
git rev-parse --short HEAD
git status --short

# rebuild + up
docker compose build ai-orchestrator-api
docker compose up -d ai-orchestrator-api

# health 재확인
sleep 3
curl -fsS http://127.0.0.1:8400/api/v1/health
```

## 8. 이번 배포 결과 요약 (2026-04-27 Stage 8C-4R)

| 단계 | 항목 | 결과 |
|------|------|------|
| Stage 8C | PR #3 merge | ✓ PASS — local-agent-capture-clean |
| Stage 8C-2 | PR #4 merge | ✓ PASS — hotfix/agent-action-registry-import |
| Stage 8C-4 (초기) | 잘못된 경로 시도 | ⚠ WARN — `/haehan-ai-orchestrator-api/` |
| Stage 8C-4R | 실제 경로 반영 | ✓ PASS — `/haehan-ai-orchestrator` |
| | git pull --ff-only | ✓ HEAD 15529c6 → 4bbf61f |
| | docker build | ✓ 새 이미지 (py 파일 추가) |
| | docker up | ✓ 컨테이너 재생성 및 healthy |
| | health | ✓ 200 OK |
| | import smoke | ✓ 5개 모듈 load 성공 |

### 해결된 문제
- **action_registry/policy 누락 문제**: hotfix merge로 agent 코어 파일 복구
- **경로 혼동 문제**: 실제 운영 경로 명확화 및 Stage 8C-4R로 정정

### 최종 판정
**✓ PASS** — 운영 배포 완료, 기능 검증 완료

## 9. 잔여 정리 항목

### 9.1. legacy path 용도 정리
```
경로: /home/ubuntu/apps/haehan-ai-orchestrator-api
상태: git repo (master, HEAD 4bbf61f), 비활성
정리 일정: Stage 9 (용도 확인 → 아카이브 또는 삭제)
```

### 9.2. GitHub Actions CI 강화
- 배포 전 import smoke CI 추가 검토
- test_import_smoke.py 자동화 (현재: local dry-run)

### 9.3. local agent dry-run smoke
- 별도 문서 및 playbook 작성 필요
- 운영 배포와 분리 (dev/staging 스핀업 검토)

### 9.4. 운영 .env 신규 환경 변수
- 향후 기능 활성화 시 (예: 외부 API 키)
- 배포 전 체크리스트 Step 7 참고
- **현재**: AUTH_ENABLED=true, 기타 기본값

### 9.5. compose volume external 설정
```yaml
# 현재 경고:
# volume "haehan-ai-orchestrator-api-storage" already exists but was created for project "haehan-ai-orchestrator-api"

# 검토 대상:
# docker volume inspect haehan-ai-orchestrator-api-storage
# 영속화 필요 여부 재확인
# - 로그 보관 필요?
# - 토큰 재사용 필요?
```

## 10. 참고: 네트워크 토폴로지

```
외부 요청
  ↓
nginx reverse proxy (Docker 컨테이너)
  ↓ /orchestrator/api/ → :8400/api/
172.18.0.1 (app_web bridge)
  ↓
haehan-ai-orchestrator-api 컨테이너 (포트 8400)
  ↓
내부 모듈: agent, ai_orchestrator
```

- **허용 IP**: 220.79.246.190 (사무실), 127.0.0.1 (localhost), 172.18.0.1 (docker nginx)
- **AUTH**: Basic 인증 필수 (AUTH_ENABLED=true)
- **외부 경로**: https://haehan-ai.kr/orchestrator/api/v1/...

---

**문서 작성일**: 2026-04-27  
**작성자**: Claude Code Stage 8D  
**다음 단계**: Stage 8E (문서 커밋 및 monitoring baseline 설정)
