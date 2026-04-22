# FastAPI 인증/RBAC API — A안 컨테이너 분리 배포

## 상태 (2026-04-22)
- **상시 운영 전환 완료 (PASS).** 실운영 salted SHA-256 해시 반영 → 컨테이너 상시 기동.
- 운영 디렉터리: `/home/ubuntu/apps/haehan-ai-orchestrator-api/`
- 컨테이너명: `haehan-ai-orchestrator-api`
- 이미지: `haehan-ai-orchestrator-api:local`
- 포트: `127.0.0.1:8400` (외부 직접 노출 없음)
- restart 정책: `unless-stopped`
- 자격증명 파일: `secrets/api/http_users.json` (chmod 600, git 추적 외부)
- 기존 `ai-orchestrator-dashboard.service` / `ai-orchestrator-monitor.service` 는 그대로 systemd 유지.

## 왜 A안인가

서버(`haehan-app`)에는 이미 systemd 로 다음 두 서비스가 돌고 있다.

- `ai-orchestrator-dashboard.service` — `/home/ubuntu/apps/haehan-ai-orchestrator` 에서
  `python3 app.py --dashboard --host 0.0.0.0 --port 5050`
- `ai-orchestrator-monitor.service` — 같은 경로에서 `python3 app.py --monitor`

이들은 `feature/dashboard-monitor` 브랜치 체크아웃 위에서 동작한다.
반면 `master` 브랜치는 구조가 다른 **FastAPI 인증/RBAC API** (uvicorn, port 8400) 를 가진다.

두 코드베이스를 머지하지 않고 동시에 안전히 운영하기 위해, 이번 단계는
**"신규 API 만 별도 컨테이너로 분리"** 하는 A안을 채택한다.

- B안(전부 컨테이너화)은 다운타임/머지 위험.
- C안(브라우저 워커만 분리)은 1단계 범위를 넘는다.

## 무엇을 컨테이너화했고 무엇은 유지했는가

| 구성 | 운영 방식 |
|------|----------|
| dashboard (`app.py --dashboard`, port 5050) | **호스트 systemd 유지** — 이번 단계에서 수정 없음 |
| monitor (`app.py --monitor`)                | **호스트 systemd 유지** — 이번 단계에서 수정 없음 |
| FastAPI 인증/RBAC API (uvicorn, port 8400)  | **신규 Docker 컨테이너** `haehan-ai-orchestrator-api` |

## 파일 구성

- `Dockerfile` — Python 3.11 slim, `uvicorn ai_orchestrator.server:app`, HEALTHCHECK 포함
- `docker-compose.yml` — 서비스 1개(`ai-orchestrator-api`), 127.0.0.1:8400 바인딩, named volume
- 호스트 배치 권장 경로: `/home/ubuntu/apps/haehan-ai-orchestrator-api/`
  (기존 `.../haehan-ai-orchestrator/` 와 **별도 디렉터리**. 브랜치/레이아웃 다이버전스 이슈 회피)

## 포트 / 네트워크 정책

- **호스트 포트 8400** (서버에서 현재 비어있음 — 2026-04-22 기준 ss 확인)
- 바인딩 `127.0.0.1:8400:8400` — 외부 직접 공개 금지, 필요 시 추후 단계에서 reverse proxy 부착
- dashboard 가 쓰는 5050 은 건드리지 않는다 (point-in-time 관찰 기준)
- docker 네트워크: 기본 bridge (별도 네트워크 생성 안 함; API 단일 서비스이므로 불필요)

## env / 경로 / 볼륨 정책

- `env_file: .env` — **호스트의 `.env` 는 git 추적 금지**. 예시는 `.env.example` 참고.
- 컨테이너 안에서 강제 override 되는 환경변수:
  - `LOG_DIR=/app/ai_orchestrator/storage` (named volume 으로 영속화)
  - `HTTP_USERS_PATH=/run/secrets/api/http_users.json` (read-only 마운트 경로)
  - `APP_HOST=0.0.0.0`, `APP_PORT=8400`
- Volume
  - `api_storage` → `/app/ai_orchestrator/storage` (named volume: `haehan-ai-orchestrator-api-storage`)
    - dashboard/monitor 가 쓰는 호스트 `storage/` 와 **공유하지 않음** (로그·토큰 파일 충돌 방지)
  - `./secrets/api` (host) → `/run/secrets/api` (container, **read-only**)
    - 안에 `http_users.json` (salted sha256 해시) 배치. 이 디렉터리는 `secrets/` 하위라 `.gitignore` 로 차단됨.

## 기동 / 중지 / 상태 (서버 기준)

최초 1회 셋업:

```bash
# 신규 API 전용 디렉터리에 master 로 fresh clone
sudo -u ubuntu mkdir -p /home/ubuntu/apps/haehan-ai-orchestrator-api
cd /home/ubuntu/apps/haehan-ai-orchestrator-api
git clone --branch master https://github.com/JAY-1979-SJW/haehan-ai-orchestrator.git .

# secrets 준비 (git 추적 금지)
mkdir -p secrets/api
# secrets/api/http_users.json 작성 (salted sha256 hash; policies/http_users.sample.json 참고)

# .env 작성 (AUTH_ENABLED=true, 기타 키는 .env.example 참고)
cp .env.example .env
# 필요 시 vi .env 로 AUTH_ENABLED=true 설정
```

일상 운영:

```bash
cd /home/ubuntu/apps/haehan-ai-orchestrator-api

# 기동
docker compose up -d --build

# 상태
docker compose ps
docker inspect -f '{{.State.Health.Status}}' haehan-ai-orchestrator-api

# 로그
docker compose logs --tail=100 -f ai-orchestrator-api

# 헬스
curl -s http://127.0.0.1:8400/api/v1/health

# 중지
docker compose stop

# 제거 (볼륨은 유지)
docker compose down

# 전체 제거 (볼륨까지 — 로그 소실 주의)
docker compose down -v
```

## 기존 서비스 비영향 확인 체크

- `systemctl is-active ai-orchestrator-dashboard ai-orchestrator-monitor` → 둘 다 `active`
- `ss -lntp | grep :5050` → dashboard 여전히 listen
- `docker ps` 에 `haehan-ai-orchestrator-api` 만 신규 등장
- `ls /home/ubuntu/apps/haehan-ai-orchestrator/` (기존 경로) 변화 없음

## 롤백 (API 만 내리기 — dashboard/monitor 무영향)

```bash
cd /home/ubuntu/apps/haehan-ai-orchestrator-api
docker compose stop        # 정지만 (볼륨·설정 유지)
# 또는
docker compose down        # 컨테이너·네트워크 제거, 볼륨 유지
# 또는
docker compose down -v     # 볼륨까지 제거 (로그 소실 주의)
```

`dashboard.service` / `monitor.service` 는 이 명령들로 절대 영향받지 않는다. 5050 포트 점유도 변하지 않는다.

## 다음 단계 (이번 범위 밖)

- 서버 `/home/ubuntu/apps/haehan-ai-orchestrator-api/` 에 실제 운영 `http_users.json` 배치 후 AUTH_ENABLED=true 로 상시 기동
- reverse proxy (nginx 등) 부착 여부 결정
- dashboard/monitor 와의 머지 전략 (장기)
- 브라우저 워커 분리 여부 검토 (C안)
- git commit / push 자동화는 이번 단계에서 도입하지 않음 (기존 self-hosted runner 고려 필요)
