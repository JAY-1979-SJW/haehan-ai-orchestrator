# 배포 파이프라인 복구 기준서 + 운영 SHA 확인 절차 (R3)

- 작성: 2026-10-07 (W4) / 브랜치 `stage/r3-deploy-visibility` / 기준 `db235656`
- 상태: **DRAFT — 기준서와 절차 문서. 서버 접속·변경 없음.** 서버 측 작업은 전부 §6에 모았고, 하나하나 대표님 승인 대상이다.
- 관련: `docs/architecture/DEPLOY_PIPELINE_REPAIR.md`(2026-06-02, 데몬 수리안 — 이후 데몬이 삭제돼 낡음), `docs/architecture/PROD_DEPLOY_PLAN.md`, `docs/defect_index.json` #4·#6·#29, `CLAUDE.md` '배포 운영규칙'
- 같이 구현된 것(커밋 `f9d03fe8`): `/api/v1/health` 응답에 `git_sha`·`build_time` 추가, Dockerfile `ARG`, compose `build.args`, `server_deploy.py`가 빌드에 SHA 전달. **이 기준서의 §5 확인 절차가 그 값을 쓴다.**

## 1. 문제 요약
운영(`haehan-ai.kr`)이 최신 master인지 알 수 없고, push해도 운영에 반영되는지 보장이 없다.
- 2026-06-02 실측: 운영 HEAD가 origin보다 **23커밋 뒤**였다(`PROD_DEPLOY_PLAN.md` §2-2). 이후 상태는 서버를 보지 못해 **모른다**.
- 이번 점검(2026-10-07)에서도 공개 health 두 경로가 FastAPI JSON이 아니라 웹앱 HTML을 돌려줬고, health에 커밋 정보가 없어 확인이 불가능했다.

## 2. 끊긴 지점 (코드로 확인한 사실 / 서버를 봐야 아는 추정을 구분)

### 2-1. 확인된 것 (저장소 기준)
| # | 끊긴 지점 | 근거 |
|---|---|---|
| ① | **배포 데몬이 저장소에 없다.** `scripts/ops/deploy_trigger_daemon.py`는 2026-06-02 커밋 `d7d84390`("좀비 스크립트" 정리, 171줄 삭제)에서 삭제됐다. 결함 #6 본문의 `b4ad2f70`은 히스토리 재작성 전 해시로 같은 커밋이다 | `git ls-files`에 없음, `git log --diff-filter=D -- scripts/ops/deploy_trigger_daemon.py`로 삭제 이력 확인 |
| ② | **systemd 유닛이 삭제된 데몬을 가리킨다.** `scripts/ops/ai-orchestrator-deploy-trigger.service`의 `ExecStart`가 `.../scripts/ops/deploy_trigger_daemon.py` | 유닛 파일 `ExecStart` 줄. 서버에 같은 유닛이 켜져 있으면 데몬 파일이 없어 재시작 루프(`Restart=always`)일 것 |
| ③ | **webhook이 리슨하는 이가 없는 곳으로 전달한다.** `deploy_router.py`의 `POST /api/v1/deploy/webhook`은 서명 검증 뒤 `http://host.docker.internal:8401/trigger`로 전달(`TRIGGER_URL`, `:37-40`). 이 포트를 열던 게 ①의 데몬 | `ai_orchestrator/routers/deploy_router.py:37-40,59-80,83-107`. 데몬이 없으면 `503 trigger_daemon_unreachable` |
| ④ | **`server_deploy.py`는 호출자가 없다.** 이 스크립트는 `--approved`가 있어야 도는데(`server_deploy.py:97`), 그것을 부르던 데몬이 ①로 사라졌다. 스크립트 자체는 정상(`git fetch` → `merge --ff-only` → `docker compose up -d --build` → nginx reload) | `tools/server_deploy.py` |
| ⑤ | **배포 전 검증이 배포 흐름에 연결돼 있지 않다.** CI(`.github/workflows/ci.yml`)는 push마다 verify_change를 돌지만, `server_deploy.py`는 CI 결과를 확인하지 않는다 | 결함 #4(status fixed지만 "연결하는 두 번째 절반은 미해결"이라고 evidence에 적힘), `server_deploy.py`에 테스트·게이트 호출 0 |
| ⑥ | **운영 반영 여부를 볼 수단이 없었다.** health에 SHA 없음 | **이번 커밋으로 해소**(§4). 단 값이 채워지려면 서버가 새 `server_deploy.py`로 빌드해야 한다 |
| ⑦ | 문서가 낡았다. `CLAUDE.md` 52줄의 "git push 후 서버가 자체 처리"와 `DEPLOY_PIPELINE_REPAIR.md`의 "데몬 경로 1줄 수정"은 현재 코드와 맞지 않는다 | 결함 #6의 fix_note(2026-09-29)에 이미 "데몬 복구/재설계는 별도 승인"이라고 적힘 |

### 2-2. 추정 (서버를 봐야 확정, 이번엔 접속하지 않음)
- 운영 서버의 데몬 서비스가 켜져 있는지, 서버에 `deploy_trigger_daemon.py`가 아직 남아 있는지(저장소에서 지워도 서버 working tree에는 ff-only 병합으로 따라 지워졌을 수 있음).
- **GitHub webhook이 설정돼 있는지, 그 URL이 무엇인지.** 만약 URL이 `https://haehan-ai.kr/orchestrator/api/v1/deploy/webhook`이라면 nginx의 `/orchestrator/api/` **owner IP 잠금**(`PROD_DEPLOY_PLAN.md` §2-3, 2026-06 실측)에 걸려 GitHub 서버가 닿지 못했을 수 있다. 즉 ③ 이전에 또 하나의 끊김이 있을 수 있다.
- 운영 `.env`의 `DEPLOY_WEBHOOK_SECRET` 설정 여부(없으면 webhook은 `503 deploy_webhook_not_configured`).
- 서버 working tree에 로컬 변경이 있어 `merge --ff-only`가 exit 4로 멈췄을 가능성.
- 결함 #29(open): 서버에 `file-map-executor` 컨테이너가 compose에서 빠진 뒤에도 남아 있음(수동 정리 필요).

## 3. 선택지

| 안 | 내용 | 장점 | 단점·위험 | 서버 측 작업 |
|---|---|---|---|---|
| **A. 호스트 데몬 복구** | `deploy_trigger_daemon.py`를 새로 작성(HMAC `X-Deploy-Signature` 검증, 8401, 동시 실행 방지 409, `server_deploy.py --approved` 호출, 상태 파일 `server_deploy_latest.json` 기록)하고 systemd로 상시 실행. GitHub webhook → nginx → API(`/deploy/webhook`) → 데몬 | 기존 `deploy_router.py`·`.service` 설계를 그대로 살림. push 즉시 자동 | **구성요소가 가장 많다**: 데몬·systemd·webhook 등록·nginx 공개 예외(webhook 경로)·시크릿 3종. 외부에 열린 배포 트리거 엔드포인트가 생김(공격면). 6월에 "좀비"로 삭제된 전례. CI 결과와 무관하게 push면 배포(#4 ⑤ 미해결) | 데몬 설치, 유닛 교체, nginx에 webhook 경로 공개 예외, GitHub webhook 등록, `DEPLOY_WEBHOOK_SECRET` 설정 |
| **B. GitHub Actions → SSH 배포 (승인 게이트 포함)** | `ci.yml`과 같은 저장소의 `deploy` 워크플로. `master`에서 CI 통과 후 `environment: production`(필수 검토자=대표님 승인)을 거쳐 SSH로 `python3 tools/server_deploy.py --approved` 실행. 끝나면 §5 절차로 health SHA 대조까지 워크플로가 수행 | 데몬·webhook·nginx 예외가 **모두 필요 없다**. CI 통과를 배포 조건으로 만들 수 있어 ⑤가 해소된다. 승인이 GitHub UI에 기록으로 남는다. 서버에 상주 프로세스가 늘지 않는다 | 서버가 GitHub 러너의 SSH 접속을 받아야 한다(포트 22 공개 또는 허용 대역 관리). **SSH 개인키가 GitHub Secrets에 들어간다** — 이 저장소는 PUBLIC(`ci.yml` 주석 2026-09-30)이므로 환경 보호 규칙·`master` 한정이 필수. 키 유출·워크플로 변조 시 서버 접속 위험 | 배포 전용 SSH 계정/키(명령 제한 `authorized_keys`: `command=` 로 `server_deploy.py`만 허용), GitHub environment·secrets 설정, (필요 시) 방화벽 |
| **C. 수동 `server_deploy.py` + SHA 확인** | 운영자가 서버에 SSH로 접속해 `python3 tools/server_deploy.py --approved`를 직접 실행하고, §5로 확인 | **지금 바로 가능.** 새로 만들 것이 없고 공격면이 늘지 않는다. 대표님이 매번 승인하는 현행 정책(CLAUDE.md '서버 배포는 승인')과 일치 | 사람이 잊으면 뒤처진다(2026-06의 23커밋 지연이 이 유형). 자동 검증 없음 | 없음(운영자가 하는 일) |

## 4. 권장안

**단계적으로 C → B. A는 권하지 않는다.**

1. **지금(0단계): C + health SHA.** 이번에 들어간 `git_sha`·`build_time` 덕분에 "운영이 어느 커밋인가"를 처음으로 한 번의 `curl`로 확인할 수 있다. 새 코드가 서버에 반영되도록 **서버에서 `server_deploy.py`를 한 번 실행**(§6-1)하고 §5로 확인한다. 이것만으로 "알 수 없음"이 "알 수 있음"으로 바뀐다.
2. **다음(1단계): B.** 수동 운영이 반복되면 뒤처질 위험이 남으므로, 승인 게이트(GitHub environment)가 있는 SSH 배포로 옮긴다. 이유:
   - 데몬·webhook·공개 엔드포인트가 필요 없어 **공격면이 늘지 않는다**(A는 외부에서 배포를 유발할 수 있는 경로를 만든다).
   - **CI 통과를 배포 조건**으로 걸 수 있어 결함 #4의 남은 절반이 풀린다.
   - 승인이 기록으로 남아 "서버 배포는 승인 후"라는 규칙을 시스템이 강제한다.
   - 단, 공개 저장소에 SSH 키를 두는 위험이 있으므로 **명령 제한 키 + `master`·environment 보호**를 전제로 한다. 이 전제를 못 지키면 1단계는 보류하고 C를 유지한다.
3. **정리(2단계):** 삭제된 데몬을 가리키는 `ai-orchestrator-deploy-trigger.service`·`deploy_router.py`의 webhook/trigger 코드를 폐기할지 결정(B를 택하면 불필요), `CLAUDE.md` 52줄 문구 갱신.

> 권장안은 의견이다. 선택은 대표님 몫이며, 어느 안이든 서버 변경은 §6의 승인 항목을 거친다.

## 5. 배포 후 운영 SHA 확인 절차 (공개 health 대조)

### 5-1. 준비 — 기대값
- push·병합 후 운영에 있어야 할 커밋: `git ls-remote origin refs/heads/master`의 SHA(앞 7자리 이상이면 충분).
- 병합 전 점검이면 로컬 `git rev-parse HEAD`.

### 5-2. 운영 값 조회
```bash
curl -s https://haehan-ai.kr/orchestrator/api/v1/health
# 기대 응답(JSON): {"status":"ok","service":"haehan-ai-orchestrator","git_sha":"<40자 SHA>","build_time":"2026-10-07T12:34:56Z"}
```
- **접근 가능 범위**: 2026-06 실측 기준 nginx가 `/orchestrator/api/`를 owner IP로 잠갔다(`PROD_DEPLOY_PLAN.md` §2-3). 그러면 **owner 네트워크에서만** JSON이 나온다. 외부에서 확인하려면 nginx에 `location = /orchestrator/api/v1/health` 공개 예외가 필요하다(§6-4, 승인 대상). 이 기준서 작성 중 외부에서 보낸 GET은 HTML이 왔으므로 **현재 경로 설정은 확인되지 않았다.**
- health에는 비밀이 없다. SHA는 저장소가 PUBLIC이라 이미 공개된 정보이고, 형식이 맞지 않는 값은 응답에 싣지 않는다(`unknown`).

### 5-3. 대조와 판정
| 응답 | 의미 | 조치 |
|---|---|---|
| `git_sha`가 기대 SHA와 앞 7자 이상 일치 | **운영이 해당 커밋으로 빌드됨** | 완료. `build_time`을 배포 시각으로 기록 |
| `git_sha` 불일치 | 운영이 다른 커밋(뒤처짐 또는 앞섬) | `git log <운영SHA>..origin/master --oneline`으로 뒤처진 커밋 수 확인 후 §6-1 재배포 |
| `git_sha`가 `"unknown"` | 이 코드 이후 이미지지만 **`server_deploy.py`를 거치지 않고 빌드**됨(수동 `docker compose build` 등) | `server_deploy.py --approved`로 재빌드. 이 상태에서는 어느 커밋인지 증명 불가 |
| 응답에 `git_sha` 키 없음 | **이번 변경 이전 이미지** — 구버전 가동 중 | 배포 필요. 아직 한 번도 새 코드가 서버에 반영되지 않은 것 |
| JSON이 아니라 HTML | 경로가 웹앱(Next.js)으로 가고 있음 — nginx 라우팅·IP 잠금 문제 | 서버에서 `curl http://127.0.0.1:8400/api/v1/health`(컨테이너 직접)로 API 자체 상태를 확인하고 nginx 설정을 점검(§6-4) |
| 4xx/5xx·타임아웃 | API 컨테이너 비정상 또는 nginx 문제 | `docker ps`·컨테이너 로그 확인(서버 작업) |

### 5-4. 타이밍·주의
- `docker compose up -d --build` 이후 API가 올라오기까지 컨테이너 `start_period` 10초 + 빌드 시간(수 분)이 걸린다. 응답이 옛 값이면 1~2분 뒤 재시도한다.
- **이 값은 API 컨테이너 한 개만 증명한다.** `admin-web`(Next.js)은 별도 이미지라 같은 방식의 SHA 노출이 없다(후속 과제: 같은 `ARG`/환경변수를 admin-web에도 적용).
- SHA는 `server_deploy.py`가 병합 직후 `git rev-parse HEAD`로 읽은 값이다. **서버 working tree에 커밋 안 된 로컬 변경이 있어도 SHA에는 드러나지 않는다.** 필요하면 후속으로 `git status --porcelain` 결과(dirty 표시)를 함께 넘기도록 확장한다.
- 값이 `unknown`이어도 컨테이너 healthcheck는 통과한다(200만 본다). 가시성 정보일 뿐 기동 조건이 아니다.

### 5-5. 자동 대조 (선택, 후속)
`tools/deploy/deploy_diagnose.py`가 이미 `PROD/health`를 조회한다. 거기에 "응답의 `git_sha`가 `git ls-remote` 결과와 일치하는가"를 추가하면 §5-2~5-3이 한 명령이 된다(코드 변경이라 이번 범위에는 넣지 않았다). 1단계(B)를 택하면 워크플로 마지막 단계가 같은 대조를 수행해 불일치 시 실패 처리한다.

## 6. 서버 측 필요 작업 (전부 대표님 승인 대상 — 이번에 하나도 실행하지 않음)

| # | 작업 | 필요한 안 | 위험 | 비고 |
|---|---|---|---|---|
| 1 | **새 코드 반영**: 서버에서 `python3 tools/server_deploy.py --approved` 1회 실행(= `git fetch`·`merge --ff-only`·`docker compose up -d --build api admin-web`·nginx reload) | A·B·C 공통 첫 단계 | 중간(컨테이너 재생성 중 순간 중단). 서버 로컬 변경이 있으면 ff-only가 exit 4로 멈춤 → 수동 확인 필요. `users.db` 백업 선행 권장(`PROD_DEPLOY_PLAN.md` §5) | 완료 확인은 §5 |
| 2 | **서버 현황 읽기 전용 점검**: `git rev-parse HEAD`, `git status --porcelain`, `systemctl status ai-orchestrator-deploy-trigger`, 데몬 파일 존재, `.env`의 `DEPLOY_WEBHOOK_SECRET` **설정 여부만**(값은 보지 않음), GitHub webhook 설정 URL | 모든 안의 전제(§2-2 추정을 사실로 바꿈) | 낮음(읽기 전용) | SSH 접속 자체가 승인 대상 |
| 3 | 낡은 데몬 유닛 정리: `ai-orchestrator-deploy-trigger.service` 중지·비활성화·제거 | B·C 선택 시 | 낮음~중간 | 유닛이 재시작 루프 중이면 로그가 쌓이고 있음 |
| 4 | **nginx**: `location = /orchestrator/api/v1/health` 공개 예외(외부에서 SHA 확인용), 또는 A안이면 webhook 경로 공개 예외 | C의 외부 확인(선택), A | **높음**(오설정 시 사이트 다운) — 백업 → `nginx -t` → `reload`(restart 금지)가 `PROD_DEPLOY_PLAN.md` §4 단계 C의 기존 규칙 | health는 비밀 정보가 없어 공개 예외 위험이 낮지만 나머지 `/orchestrator/api/` 잠금은 유지해야 함 |
| 5 | (B) 배포 전용 SSH 계정/키: `authorized_keys`에 `command="python3 /home/ubuntu/apps/haehan-ai-orchestrator/tools/server_deploy.py --approved",no-pty,no-port-forwarding` 형태로 **명령 제한**, GitHub `production` environment(필수 검토자)·secrets 등록, 22번 포트 허용 범위 결정 | B | **높음**(서버 접근 경로 신설) | 공개 저장소이므로 environment 보호·`master` 한정 필수 |
| 6 | (A) 데몬 재작성·설치, 유닛 교체, webhook 등록, `DEPLOY_WEBHOOK_SECRET` 설정, nginx webhook 경로 예외 | A | **높음** | 권장하지 않음(§4) |
| 7 | 결함 #29: 서버에 남은 `file-map-executor` 컨테이너 수동 정리 | 공통(독립 정리) | 낮음~중간 | 삭제 전 컨테이너 내용 확인 |

## 7. 저장소 쪽 후속 작업 (서버 접속 불필요, 승인 후 별도 커밋)
1. `deploy_diagnose.py`에 SHA 대조 추가(§5-5).
2. admin-web 이미지에도 같은 빌드 식별 적용.
3. B안 선택 시 `.github/workflows/deploy.yml` 신설(`needs: verify`, `environment: production`, 대조 단계 포함).
4. 삭제된 데몬을 가리키는 `scripts/ops/ai-orchestrator-deploy-trigger.service`·`deploy_router.py`의 trigger 전달 코드 폐기 여부 결정, `CLAUDE.md` 52줄·`DEPLOY_PIPELINE_REPAIR.md` 낡은 서술 정리, 결함 #6 fix_note 갱신.
5. `server_deploy.py`에 배포 전 `git status --porcelain` dirty 표시 전달(§5-4).

## 8. 검증 (이번 커밋)
- `tests/test_health_build_info.py` 16건 통과: 기본값 `unknown`, 주입 값 반영, 잘못된 형식 거부(빈 값·7자 미만·비16진·길이 초과·특수문자), 기존 키(`status`·`service`) 유지, Dockerfile `ARG`/`ENV`, compose `build.args`, `server_deploy.py` 전달, healthcheck URL 불변.
- 기존 시험: `test_auth_basic_enforcement` 17, `test_codebase_layer_audit` 24 통과. `ai_orchestrator/tests/test_router_smoke`의 4건 실패(401)는 기준 `db235656`에서도 동일한 기존 실패.
- **실제 docker 빌드와 서버 반영은 이 PC에서 하지 않았다**(docker 미설치, 서버 접속 금지). compose 파일은 YAML 파싱과 `build.args` 구조만 확인했다. 첫 서버 빌드에서 `GIT_SHA`가 컨테이너에 들어가는지는 §5 절차로 **확인해야 한다**(미검증 항목).
