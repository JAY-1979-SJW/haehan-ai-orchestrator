# 기준서 — 배포 파이프라인 복구 + 정책 예외(Scoped Exception)

Status: DRAFT (승인 대기 — 실행 전)
작성일: 2026-06-02
근거: 운영 서버 SSH 진단 + 게이트 코드 확인
관련: `docs/architecture/PROD_DEPLOY_PLAN.md`, `CLAUDE.md`(배포 운영규칙)

---

## 1. 배경 (진단 결과)

운영 배포 데몬(`ai-orchestrator-deploy-trigger.service`)은 정상 동작하나,
실행하려는 배포 스크립트 `scripts/ops/deploy_api_with_runtime_gates.py`가 **삭제됨**
→ 매 트리거마다 `No such file → exit_code=2` → 운영이 origin보다 23커밋 밀림.

원인: "로컬 Docker 제거" 작업 때 배포 스크립트를 삭제(`CLAUDE.md` 복구금지 목록)했으나
데몬(`deploy_trigger_daemon.py:33`)은 그 경로를 그대로 참조.

근본 딜레마: 서버 배포는 `docker compose`가 필요한데, `NO_LOCAL_DOCKER_CLI` 게이트가
docker 호출 스크립트의 repo 커밋을 차단 → 배포 스크립트를 repo에 둘 수 없었음.

---

## 2. 해결 방향: Scoped Exception (정책을 콕 집어 수정)

게이트를 끄지 않고, **단 하나의 지정된 서버 배포 스크립트에만** docker 허용.
나머지 전체는 docker 금지 유지. (게이트는 이미 `tools/quality/quality_gate.py`를 예외 처리하는
선례가 있음 — `quality_gate.py:151`)

---

## 3. 변경 범위 (5개 파일)

### 3-1. `configs/quality_gate.json` (L2 정책 설정)
```json
"no_local_docker_cli": true,
"no_local_docker_cli_allow_paths": ["tools/server_deploy.py"]   // 신규
```

### 3-2. `tools/quality/quality_gate.py` (L2 게이트)
`_has_local_docker_cli()` 에 예외 경로 체크 추가 (기존 quality_gate.py 예외와 동일 패턴):
```python
allow = config.get("no_local_docker_cli_allow_paths", [])  # 호출부에서 전달
if path in allow:
    return False
```
- 변경 최소화: 예외 목록에 포함된 경로면 docker 검사 skip.

### 3-3. `tools/server_deploy.py` (신규, L2/운영)
서버 전용 배포 스크립트. **로컬 PC 오작동 방지 가드 필수:**
```python
# 가드: docker 없으면(=로컬 PC) 즉시 중단
if shutil.which("docker") is None:
    print("server_deploy: docker 없음 — 서버 전용 스크립트. 로컬 실행 차단.")
    sys.exit(3)
# git fetch + reset --hard origin/master (또는 pull)
# docker compose up -d --build (api, admin-web)
```
- `--approved` 인자 받음 (데몬이 전달, 기존 인터페이스 유지)

### 3-4. `scripts/ops/deploy_trigger_daemon.py` (운영)
```python
DEPLOY_SCRIPT = ROOT / "scripts" / "ops" / "server_deploy.py"   # 기존 삭제 경로 → 신규
```
- 1줄 변경.

### 3-5. `CLAUDE.md` (L12 정책 문서)
- "삭제된 스크립트(복구 금지)" 목록에서 맥락 보강
- 예외 사유 명문화: "`server_deploy.py`만 docker 허용 — 서버 배포 전용, 로컬 가드 내장"

---

## 4. 드라이런 (실제 미적용)

1. **게이트 예외 동작 시뮬레이션**:
   - `server_deploy.py`에 `["docker", "compose", ...]` 포함 → 예외 등록 후 `quality_gate.py --staged` 가 **통과**하는지
   - 다른 파일에 동일 패턴 넣으면 여전히 **차단**되는지 (예외가 1개 파일에만 적용 확인)
2. **로컬 가드 시뮬레이션**: `server_deploy.py`를 로컬(docker 없음)에서 실행 → `exit 3`(중단) 확인
3. **데몬 경로 수정 확인**: 운영에서 `python3 server_deploy.py --approved` 가 존재/실행 가능한지 (dry 플래그)

---

## 5. 영향 / 안전장치

| 항목 | 내용 |
|------|------|
| 보안(게이트) | docker 금지 **유지**. 1개 파일만 예외, 그 파일도 로컬 가드 |
| 로컬 오작동 | `server_deploy.py`는 docker 없으면 즉시 종료 → 당신 PC 안전 |
| 운영 영향 | 이 단계는 **데몬 수리까지만**. 실제 배포(git pull+rebuild)는 별도 승인 후 |
| 롤백 | 데몬 경로 1줄·게이트 예외 제거로 원복. 신규 파일 삭제 |
| 레이어 | config(L2)/gate(L2)/deploy(운영)/docs(L12) — 위반 없음 |

---

## 6. 실행 순서 (승인 후)

1. server_deploy.py 작성 (로컬 가드 포함)
2. quality_gate.py 예외 로직 + config 예외 등록
3. 드라이런: 게이트 예외/차단 양방향 + 로컬 가드 검증
4. CLAUDE.md 문서화
5. 게이트 3종 통과 → 커밋 → push
6. (별도 승인) 운영 서버에 server_deploy.py 반영 + 데몬 경로 수정 + 데몬 재시작
7. (별도 승인) 데몬 트리거 → 실제 배포 검증

---

## 7. 주의

- 이 기준서는 **파이프라인 복구**까지. 실제 운영 배포(코드 반영)·nginx 공개 예외는
  `PROD_DEPLOY_PLAN.md`의 후속 단계로, 각각 개별 승인.
- `server_deploy.py`의 `git reset --hard` 사용 여부는 신중히 — 운영 로컬 변경 유실 위험.
  안전하게 `git fetch` + `git log` 확인 후 `git merge --ff-only` 권장.
