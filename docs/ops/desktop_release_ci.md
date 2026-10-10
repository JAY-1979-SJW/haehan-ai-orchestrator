# 데스크톱 릴리스 빌드 (GitHub Actions)

운영 배포는 서버가 아니라 **사용자별 로컬 설치(Electron 데스크톱 앱)**이고, 배포 파일은
**NAS(Nextcloud)**로 공유한다(대표님 결정, 2026-10-07). 빌드는 이 PC가 아니라
**GitHub Actions**에서 한다 — 공개 저장소라 Windows 러너가 무료이고, 로컬 PC의 CPU를
보호한다.

워크플로: `.github/workflows/desktop-release.yml`

## 실행 방법

이 워크플로는 `workflow_dispatch`(수동) + 태그 push(`v*`)로 돈다. **`workflow_dispatch`는
기본 브랜치(master)에 올라간 워크플로만 수동 실행할 수 있다** — 이 파일이 아직 PR로
master에 반영되지 않았다면 Actions 탭에 나타나지 않는다. 먼저 master에 merge한 뒤 실행한다.

- 수동 실행: GitHub → Actions → "Desktop Release Build" → Run workflow. `ref` 입력을
  비우면 기본 브랜치, 특정 브랜치/태그/커밋을 넣으면 그걸 빌드한다.
- 태그로 실행: `git tag v1.2.3 && git push origin v1.2.3` — 태그 push가 자동으로 트리거.

## 첫 실행 점검 목록

이 워크플로는 master 반영 전까지 정적 점검만 했다(실제 PyInstaller/electron-builder
빌드 없음). master 반영 후 **첫 실행**에서 반드시 로그로 확인할 것:

- [ ] `haehan-server.spec` PyInstaller 로그에 `ai_orchestrator.paths` 패키지(및
      `paths.bootstrap`·`paths.runtime`·`paths.migrate`)가 포함됐는지 확인한다.
      `t-base`(db8bc309)가 PR 2에 이 패키지를 들여오면서 `asgi.py`가 정적으로
      `from ai_orchestrator.paths import bootstrap` 형태로 import하게 되는데,
      일반 import라 PyInstaller가 자동 탐지해야 하지만 hiddenimports 없이도
      실제로 번들에 들어갔는지는 실빌드로만 확인된다(W4 skyjw-3c 요청, 2026-10-07).
      안 들어갔으면 `haehan-server.spec`의 `hidden_imports`에
      `"ai_orchestrator.paths"`·`"ai_orchestrator.paths.bootstrap"` 등을 추가한다.
- [ ] 3개 PyInstaller 빌드 모두 에러 없이 끝나는지(ModuleNotFoundError 등).
- [ ] `build-info.json`이 실제 git_sha/build_time/version 값으로(== "unknown"/"0.0.0-dev"
      스텁이 아님) 채워져서 exe에 들어갔는지.
- [ ] 포터블 exe 파일명이 `HaehanAI-<yyyymmdd>-<sha7>-portable.exe` 형태로 나오는지.
- [ ] `checksums.txt`가 비어 있지 않은지.
- [ ] E2E 잡(app/user_flow/fresh_install_signup)이 초록인지. `fresh_install_signup`의
      시나리오 1·3·4·5는 D3·reject 미병합 + §E2E 알려진 제한 항목이 해결되기
      전까지는 **스킵으로 표시되는 게 정상**(실패가 아니라 스킵인지 확인).

## E2E (빌드 산출물, Playwright Electron)

같은 작업(job) 안에서 포터블 빌드 뒤 `electron-builder --win dir`로 unpacked
빌드를 한 번 더 뽑아 그걸 실행 대상으로 `admin-web/electron/e2e-electron/`의
기존 Playwright 스펙을 돈다(새 프레임워크 없음, `launch_helper.ts`·
`playwright.electron.config.ts` 재사용).

- 실행: `app.spec.ts`, `user_flow.spec.ts`(AI 비서 GPT 1턴은 유료 API라
  `HAEHAN_E2E_SKIP_PAID_API=1`로 스킵), `fresh_install_signup.spec.ts`(신규 — 새 PC
  첫 설치/자동 로그인 시나리오, 아래 참고).
- 제외: `diagnose.spec.ts`(mail/google 페이지의 "조회" 버튼이 실제 Gmail/Google
  OAuth 계정에 접근), `agent_employee_eval.spec.ts`(외부 사이트
  `books.toscrape.com`·`cafe.naver.com` 접속, CDP 9222 전제, 15분 평가용 — CI
  스모크 범위가 아님).
- 실패 시 `test-results/`·`playwright-report/`·스크린샷을 artifact로 올린다
  (`HaehanAI-Desktop-e2e-failure-<version>`, 14일 보관).

### fresh_install_signup.spec.ts — 새 PC 첫 설치(B안: 비밀번호 없음)

대표님 결정(2026-10-07): 데스크톱에는 비밀번호 로그인 화면이 없다(B안). 첫
실행 때 `/setup`에서 **이름·이메일만** 입력하면 바로 메인 화면으로 가고, 그
뒤로는 재실행해도 다시 묻지 않고 자동 로그인된다. W4(`stage/desktop-session`)가
구현 중이라 이 브랜치(PR 2 기준)에는 아직 `/setup`·자동 로그인 로직이 없다 —
3개 시나리오 전부 `SKIP_PENDING_FEATURES`로 "대기" 표시해 뒀다. 병합되면 그
상수를 `false`로 바꾸고, 실제 `/setup` 화면 선택자(현재는 설계 의도로 추정한
placeholder/버튼 텍스트)를 맞춰 보정한다.

임시 `userData`(`--user-data-dir`)로 완전히 빈 상태에서 시작:

1. 첫 실행 → `/setup`에서 이름·이메일만 입력 → 제출 즉시 메인 화면(로그인
   화면을 전혀 거치지 않음) — **[대기]**
2. 앱 종료 후 같은 `userData`로 재실행 → `/setup`·`/login` 둘 다 다시 안 거치고
   자동 로그인 → 1회차에 등록한 이름이 재실행 후에도 그대로 보임(D1, 데이터 유지) — **[대기]**
3. 마이페이지 "앱 정보"에 `build-info.json` 기반 버전(`<yyyymmdd>-<sha7>`)이
   표시됨 — **[대기]**

가입 승인·거절(대기자 조회/승인/거절 API)은 **서버 모드(다중 사용자) 전용
개념**이다 — 데스크톱은 비밀번호도 승인 대기도 없어(B안) 해당 경로를 데스크톱
E2E에서 다루지 않는다. 그 경로는 서버 모드 pytest가 이미 가지고 있다
(`tests/test_user_approval_gate.py`, `tests/test_user_auth_audit.py`). 참고로
서버 모드에서 그 API를 직접 호출하는 방법은 아래 "서버 모드 — API로 가입자
관리하기"에 남겨 둔다.

## 서버 모드 — API로 가입자 관리하기 (참고, 데스크톱 아님)

서버 모드(다중 사용자, `AUTH_ENABLED=true`)에서는 가입 승인·거절을 화면이
아니라 API로 직접 한다. 전부 `owner`(또는 `admin`, 거절·owner 이메일 계정
승인은 `owner`만) 권한의 Bearer 토큰이 필요하다 — `POST /api/v1/users/login`
으로 먼저 로그인해 토큰을 받는다.

### 1. 로그인(토큰 발급)

```bash
curl -s -X POST http://127.0.0.1:8401/api/v1/users/login \
  -H "Content-Type: application/json" \
  -d '{"email": "owner@example.com", "password": "<비밀번호>"}'
```

```powershell
$resp = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8401/api/v1/users/login" `
  -ContentType "application/json" `
  -Body (@{ email = "owner@example.com"; password = "<비밀번호>" } | ConvertTo-Json)
$token = $resp.token
```

### 2. 승인 대기자 조회 (owner/admin)

```bash
curl -s http://127.0.0.1:8401/api/v1/users/pending \
  -H "Authorization: Bearer <토큰>"
```

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8401/api/v1/users/pending" `
  -Headers @{ Authorization = "Bearer $token" }
```

### 3. 승인

```bash
curl -s -X POST http://127.0.0.1:8401/api/v1/users/<user_id>/approve \
  -H "Authorization: Bearer <토큰>"
```

```powershell
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8401/api/v1/users/<user_id>/approve" `
  -Headers @{ Authorization = "Bearer $token" }
```

### 4. 거절 (owner 전용)

```bash
curl -s -X POST http://127.0.0.1:8401/api/v1/users/<user_id>/reject \
  -H "Authorization: Bearer <토큰>"
```

```powershell
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8401/api/v1/users/<user_id>/reject" `
  -Headers @{ Authorization = "Bearer $token" }
```

거절된 사용자는 같은 이메일로 다시 가입할 수 있다(영구 차단 아님). owner
이메일(`OWNER_EMAILS`)로 가입한 계정은 `owner`만 승인할 수 있다 — `admin`이
승인을 시도하면 403(권한 상승 차단).

## 빌드 단계

1. checkout(해당 ref, `fetch-depth: 0` — git sha/버전 계산에 전체 히스토리 필요)
2. Python 3.14, Node 20 설정(npm 캐시)
3. `admin-web`·`admin-web/electron` 각각 `npm ci`
4. `npm run build`(admin-web) — `next.config`의 `output: "standalone"`으로 `.next/standalone` 생성
5. PyInstaller 3종 — 저장소 루트의 `haehan-server.spec`·`local-agent.spec`·`mcp-server.spec`로
   `dist/haehan-server`·`dist/local-agent`·`dist/haehan-mcp` 생성
6. `build-info.json` 작성(`admin-web/electron/build-info.json` — git_sha·build_time·version)
7. `electron-builder --win portable` — `dist-electron-new/HaehanAI-<version>-portable.exe`
8. SHA256 체크섬(`checksums.txt`)
9. `actions/upload-artifact`로 exe + 체크섬 업로드(30일 보관)

## PyInstaller spec 3종 — 복구 경위

2026-09-23 커밋 `b13d1216`이 "타인 배포는 당분간 하지 않음" 결정으로 Electron 셸·
PyInstaller spec·인스톨러·로컬 에이전트 GUI를 통째로 삭제했다. 9/28 `f9f1a8e9`에서
Electron 셸만 복원됐고(사용자가 "AI 에이전트+브라우저 CDP 자동화를 Electron 앱으로
연동"이 목표라고 재확인), PyInstaller spec은 "타인 배포에 특화된 부분"이라 그때는
복원하지 않았다. 대표님의 2026-10-07 결정(로컬 설치 + NAS 배포)으로 다시 필요해져
`git show b13d1216^:<spec>`으로 복구했다.

복구하며 바뀐 부분(2주 사이 루트 모듈 분리 등 리팩터링 반영, 모두 정적 점검만 함 —
**로컬에서 실제 PyInstaller 빌드는 하지 않았다**, 실빌드 확인은 master 반영 후 첫 CI
실행에서):

- `haehan-server.spec`: 진입점 `scripts/run_server.py`(삭제됨) → `ai_orchestrator/asgi.py`.
  `scripts.browser_agent`(삭제됨) hidden_imports 제거. `hookspath`가 가리키던
  `build_hooks/`가 없어 빈 값으로. **`ai_orchestrator/storage/`(계정 DB·감사 로그 등
  사용자 데이터)는 `datas`에서 명시적으로 제외** — CI는 git 체크아웃이라 `.gitignore`된
  그 폴더가 원래 비어 있지만, 로컬에서 실수로 빌드해도 사용자 데이터가 번들에 안
  들어가게 방어적으로 막아 뒀다(`DESKTOP_RUNTIME_AUDIT.md` D1/D3).
- `local-agent.spec`: 진입점·hidden_imports(smartstore 경로) 전부 유효, 변경 없음.
- `mcp-server.spec`: OpenAI 제거(2026-09-24) 이후 `mcp_server.py`가 더 안 쓰는
  `gpt_description_writer`·`scripts.common.critical_logger`·`scripts.common.logger`를 hidden_imports
  에서 뺐고, 실제로 동적 import하는 `scripts.naver.smartstore.*`·`scripts.naver.cafe.*`·
  `scripts.browser.agent.*`로 갱신.

## build-info.json 형식 (W4 합의)

`admin-web/electron/build-info.json`(extraResources로 `resourcesPath/build-info.json`에 복사):

```json
{"git_sha": "<40자 소문자 hex>", "build_time": "<ISO8601 UTC>", "version": "<yyyymmdd>-<sha7>"}
```

- `fastapi_server.js`(W4)가 이 파일을 읽어 `git_sha`→`GIT_SHA`, `build_time`→`BUILD_TIME`
  env로 서버 spawn에 넘긴다. 서버(`ai_orchestrator/router.py`의 `/api/v1/health`,
  R3 관례)는 이미 이 두 env를 런타임에 읽어 검증·노출하므로 서버 코드 수정은 필요 없다.
  파일이 없거나 깨져도 "unknown"으로 처리되며 앱 시작을 막지 않는다.
- 저장소에 커밋된 기본값(`git_sha`·`build_time`: `"unknown"`, `version`: `"0.0.0-dev"`)은
  CI가 빌드 때마다 덮어쓴다 — 로컬 `electron-builder`(dev 패키징) 때 파일이 없어서
  실패하는 일을 막기 위한 플레이스홀더다.
- 버전은 두 가지다. **표시용** `yyyymmdd-sha7`(예: `20261008-abc1234`)은 `build-info.json`의 `version`,
  포터블 파일 이름(`package.json` `portable.artifactName` = `HaehanAI-${env.HAEHAN_BUILD_VERSION}-portable.exe`),
  앱의 `userData\mcp\<버전>` 폴더, 게시 도구 `--version` 에 쓴다. **Windows/electron-builder용**
  `<yyyy>.<mmdd 정수>.<run_number>`(예: `2026.1008.17`, semver 유효·각 칸 ≤65535)는
  `-c.extraMetadata.version` 으로만 넘긴다(비-semver 날짜 문자열은 Windows 16비트 파일 버전에서 잘린다).
  로컬에서 `electron-builder` 로 직접 빌드할 때는 `HAEHAN_BUILD_VERSION=<표시용 버전>` 환경변수를 줘야 파일 이름이 정해진다.
- 아티팩트(`HaehanAI-Desktop-<버전>`)는 `release-out/` 한 폴더에 평평하게 담긴다: `HaehanAI-*.exe`,
  `checksums.txt`, `RELEASE_NOTES.md`, `설치_및_사용_안내.md`(두 문서는 `docs/release/desktop/` 에서 복사, 없으면 건너뜀).
  압축을 푼 폴더를 그대로 `publish_release_to_nas.py <폴더> --version <표시용 버전>` 의 산출물 폴더로 쓴다 — 게시 도구는
  exe·checksums.txt 를 필수로, 두 문서를 있으면 함께 NAS 에 올린다.

## 서명·비밀값

이 워크플로에는 코드 서명 비밀값이나 사내 비밀을 넣지 않는다(서명 없는 포터블
빌드). 제3자 GitHub Action은 기존 `ci.yml`의 관례(R4 — 태그가 아니라 전체 커밋 SHA로
고정)를 따른다. `permissions: contents: read`만 부여한다.

## NAS 게시 절차 (수동)

1. Actions 실행이 끝나면 아티팩트(`HaehanAI-Desktop-<version>`)를 다운로드한다.
2. NAS(Nextcloud) `회사공용/배포/Haehan AI/<버전>/` 폴더를 만든다.
3. 그 안에 `HaehanAI-<yyyymmdd>-<sha7>-portable.exe`와 `checksums.txt`를 올린다.
4. 같은 폴더에 변경 요약(무엇이 바뀌었는지 2~3줄)을 `변경사항.txt` 또는 비슷한 이름으로
   같이 올린다 — 사용자가 업데이트 여부를 판단할 근거.
5. 사내 공지(예: 메신저)로 새 버전 경로를 알린다.

## 사용자 설치 안내

1. NAS 폴더에서 최신 `<버전>` 폴더의 `HaehanAI-<버전>-portable.exe`를 받는다.
2. `checksums.txt`로 다운로드가 온전한지 확인하고 싶으면:
   `CertUtil -hashfile HaehanAI-<버전>-portable.exe SHA256` (PowerShell)로 비교.
3. 포터블 exe는 설치 과정 없이 그대로 실행한다. 최초 실행 시 Windows Defender
   SmartScreen이 "알 수 없는 게시자" 경고를 띄울 수 있다(서명 안 된 빌드) —
   "추가 정보" → "실행"으로 진행.
4. 대상 PC에 **Google Chrome 설치가 필요**하다(Playwright Chromium 번들을 빼서
   용량을 줄였다 — 앱이 Chrome 미탐지 시 설치 안내를 띄운다).
5. 알려진 제한(해결 전까지 참고): 포터블 실행은 압축을 임시 폴더에 풀기 때문에,
   다음 버전으로 갱신하면 계정·감사 로그 등 로컬 데이터가 유지된다고 보장할 수
   없다(`DESKTOP_RUNTIME_AUDIT.md` D1 — 근본 수정은 별도 작업).
