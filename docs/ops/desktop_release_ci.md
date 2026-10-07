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
  `gpt_description_writer`·`scripts.critical_logger`·`scripts.logger`를 hidden_imports
  에서 뺐고, 실제로 동적 import하는 `scripts.naver.smartstore.*`·`scripts.naver.cafe.*`·
  `ai_orchestrator.local_agent.browser.*`로 갱신.

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
- 포터블 파일명도 같은 `version`을 쓴다(`package.json`의 `portable.artifactName`:
  `HaehanAI-${version}-portable.exe` → `-c.extraMetadata.version=<yyyymmdd>-<sha7>`로 주입).

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
