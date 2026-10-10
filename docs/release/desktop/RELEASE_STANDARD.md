# Haehan AI 데스크톱 출시 기준 — "Windows 설치 프로그램 = 출시 기준"

- 결정: 대표님. 출시 단위는 Windows 설치 프로그램(`HaehanAI-<버전>-setup.exe`)이다. 포터블(`-portable.exe`)은 같은 빌드에서 함께 나오지만 출시 기준이 아니다.
- 이 문서는 "출시해도 되는가"를 판단하는 10단계다. 각 단계에 **자동으로 막는 장치**(워크플로 단계·시험 이름) 또는 **사람 확인 항목**을 적고, 자동화가 아직 없는 것은 **미자동화**로 표시한다.
- 근거 파일: `.github/workflows/desktop-release.yml`, `admin-web/electron/package.json`(build.nsis), `scripts/ops/verify_desktop_bundle.py`, `scripts/ops/publish_release_to_nas.py`, `admin-web/electron/e2e-electron/*.spec.ts`. 전 기능 점검표: `C:\work\_coordination\APP_FEATURE_CHECKLIST.md`.

## 한눈에 보기

| 단계 | 내용 | 막는 방법 | 상태 |
|---|---|---|---|
| ① | GitHub 빌드만, 버전 규칙 | 워크플로 단계 `Write build-info.json` | 자동 |
| ② | 설치본 내용물 점검 | 워크플로 단계 `설치본 내용물 점검`, 시험 `tests/test_verify_desktop_bundle.py` | 자동 |
| ③ | 설치본 E2E | 워크플로 단계 `E2E (Electron, 빌드 산출물)` | 자동 |
| ④ | 전 화면 점검 | `all_screens.spec.ts`(수동 실행) + 점검표 | 반자동 |
| ⑤ | 실제 PC 설치 확인 | 사람 확인 | 사람 |
| ⑥ | 설치 조건 | `package.json` build.nsis 설정 + 사람 확인 | 설정 고정, 확인은 사람 |
| ⑦ | 제거 시 사용자 데이터 보존 | `deleteAppDataOnUninstall=false` 설정만 있음 | **미자동화** |
| ⑧ | 덮어 설치 시 데이터 유지 | 없음 | **미자동화** |
| ⑨ | 배포는 NAS만 | `publish_release_to_nas.py`, 시험 `tests/test_publish_release_to_nas.py`, 아티팩트 3일 | 자동 |
| ⑩ | 설치 안내서 | 사람 확인 | **미자동화** |

---

## ① GitHub 빌드만 (버전 `<yyyy>.<mmdd>.<run>` · `yyyymmdd-sha7`)

- 출시용 설치본은 이 PC가 아니라 GitHub Actions `Desktop Release Build`(windows-latest)에서만 만든다. 로컬 빌드물은 출시하지 않는다.
- 버전은 두 가지를 쓴다.
  - 앱 메타데이터·Windows 파일 버전: `<yyyy>.<mmdd 정수>.<run_number>` (예: `2026.1008.17`). mmdd 는 앞자리 0 이 semver 에서 무효라 정수로 바꾼다(`0107` → `107`). 각 칸 ≤ 65535.
  - 화면 표시·산출물 이름·`build-info.json`: `yyyymmdd-sha7` (예: `20261008-ab12cd3`).
- 자동으로 막는 장치: 워크플로 단계 `Write build-info.json`(두 버전과 `git_sha`·`build_time` 기록), 산출물 이름 `HaehanAI-<yyyymmdd-sha7>-setup.exe`(package.json `nsis.artifactName`).
- 사람 확인: 설치 후 앱 정보의 빌드 버전이 받은 파일 이름의 `yyyymmdd-sha7` 과 같은지 본다(⑤에서 함께).

## ② 설치본 내용물 점검

- 빌드가 성공해도 묶을 파일이 빠질 수 있다(2026-10-08: `.next/static`·`public` 누락 → 앱이 "로딩 중"에서 멈춤). E2E(약 40분)에 가기 전에 1분 안에 잡는다.
- 자동으로 막는 장치: 워크플로 단계 `설치본 내용물 점검`(`python scripts/ops/verify_desktop_bundle.py dist-electron-new/win-unpacked --dist dist-electron-new`). 종료코드 1 이면 빌드 실패. 검사기 자체의 시험은 `tests/test_verify_desktop_bundle.py`.
- 새로 묶어야 할 파일·폴더가 생기면 `verify_desktop_bundle.py` 의 `REQUIRED` 목록에 같은 변경에서 추가한다.

## ③ 설치본 E2E

- 빌드 산출물(unpacked 폴더의 실제 `Haehan AI.exe`)을 Playwright 로 띄워 `app`, `user_flow`, `fresh_install_signup` 을 돈다.
- 자동으로 막는 장치: 워크플로 단계 `E2E (Electron, 빌드 산출물) — app/user_flow/fresh_install_signup` (`admin-web/electron/e2e-electron/{app,user_flow,fresh_install_signup}.spec.ts`).
- 규칙:
  - `HAEHAN_E2E=1` 에서는 사용자 PC 의 Claude 설정(`~/.claude.json`·Claude Desktop 설정)을 **바꾸지 않는다**(`main.js`). 자동 점검이 사용자 Claude 연결을 건드리면 안 된다.
  - 유료 API 호출은 `HAEHAN_E2E_SKIP_PAID_API=1` 로 건너뛴다. 외부 계정을 건드리는 `diagnose.spec.ts`, 외부 사이트에 접속하는 `agent_employee_eval.spec.ts` 는 이 단계에서 제외한다.
  - 실패하면 스크린샷·trace·앱 로그를 아티팩트(14일)로 남기고, 설치 파일은 `UNVERIFIED-` 이름으로 1일만 보관한다. **UNVERIFIED 설치 파일은 배포 금지**(사람이 확인용으로만 설치).

## ④ 전 화면 점검

- 점검표(`APP_FEATURE_CHECKLIST.md`)의 모든 화면·Electron 기능·라우터·MCP 도구를 안전등급별로 확인한다.
- 자동 점검: `all_screens.spec.ts`(브랜치 `stage/app-feature-check`). 앱을 모두 종료한 뒤(포트 3000/8401/9333 충돌 방지) `cd admin-web\electron; npx playwright test -c playwright.electron.config.ts all_screens`. 화면별 스크린샷과 `all_screens_report.jsonl` 이 남고, 마지막 "요약" 시험이 실패 목록을 모아 보여 준다. 화면이 스스로 보내는 쓰기 요청(POST 등)은 스펙이 차단한다.
- **안전등급 C(외부 발송·쓰기·결제·유료 API)는 자동으로 실행하지 않는다.** 승인 단계·드라이런까지만 확인한다.
  - A: 읽기 전용·이 PC 안에서만 동작 → 자동 실행해 확인.
  - B: 실제 외부 계정 로그인이 있어야 의미 있음 → "연결/로그인 필요" 흐름이 뜨는지까지만.
  - C: 절대 실행하지 않음.
- 현재 한계: `all_screens.spec.ts` 는 아직 `desktop-release.yml` 의 단계가 아니다(수동 실행). 출시 전에 사람이 한 번 돌려 결과를 확인한다. 워크플로 단계로 넣을지는 별도 결정.

## ⑤ 실제 PC 설치 확인 — 사람 확인 항목

받은 `-setup.exe` 를 실제 PC(가능하면 깨끗한 PC 또는 이전 버전이 없는 계정)에 설치해 아래를 확인한다.

1. **설치 위치**: 기본 `%LOCALAPPDATA%\Programs\Haehan AI`(사용자 단위 설치). 설치 폴더 변경 가능.
2. **바로가기**: 바탕화면, 시작 메뉴.
3. **제거 항목**: 설정 → 앱에 `Haehan AI` 가 보이고 제거가 된다.
4. **시작 시간**: `%APPDATA%\Haehan AI\logs` 의 `startup.log` 에서 시작 단계별 시간을 본다(서버 기동·UI 서버 기동·창 표시). 이상하게 오래 걸린 단계가 없는지.
5. **health**: `http://127.0.0.1:8401/api/v1/health` 가 200 이고 응답의 빌드 버전이 설치한 파일의 `yyyymmdd-sha7` 과 같다.
6. **Claude 연결**: 앱 안내에서 `[연결]` 후 Claude Desktop / Claude Code 항목이 추가되고(기존 설정은 보존, 백업 `.bak-날짜시간` 생성), Claude 를 완전히 종료 후 재실행하면 도구가 보인다.
7. 첫 실행 `/setup`(이름·이메일) → AI 콘솔이 열린다.

## ⑥ 설치 조건

`admin-web/electron/package.json` 의 `build.nsis` 가 근거다.

- **관리자 권한 불필요**: `perMachine: false`(사용자 단위 설치). 설치 중 UAC 승격 요청이 뜨지 않아야 한다.
- **라이선스 동의 화면 없음**: `nsis.license` 를 설정하지 않는다(설치 마법사에 라이선스 페이지 없음).
- **Windows 기본 대화상자 대신 앱 안 안내**: 시작 실패·Chrome 미설치·Claude 연결 같은 안내는 Windows 기본 메시지 상자가 아니라 앱 화면 안에서 보여 준다. (E2E 에서는 `HAEHAN_E2E=1` 로 오류 창 없이 바로 종료.)
- 설치 마법사는 한국어(`installerLanguages: ko_KR`), `oneClick: false`, 설치 폴더 변경 허용.
- 자동으로 막는 장치: 설정 값 자체. 이 값을 바꾸는 변경은 이 문서를 같이 갱신한다.
- 사람 확인: ⑤ 설치 때 UAC 창·라이선스 페이지가 나오지 않는지 눈으로 본다. 현재 `설치_및_사용_안내.md` 에 라이선스 키 입력 안내가 남아 있다면 이 기준(라이선스 없음)과 어긋나므로 ⑩에서 맞춘다.

## ⑦ 제거 시 사용자 데이터 보존 — 미자동화

- 제거해도 `%APPDATA%\Haehan AI`(계정·설정·로그·Claude 연결 정보)는 **그대로 남는다**.
- 현재 장치: `package.json` 의 `nsis.deleteAppDataOnUninstall: false`. 설정 값만 있고 이를 실제로 검증하는 시험·워크플로 단계는 **없다(미자동화)**.
- 사람 확인: 설치 → 데이터 생성(`/setup`) → 제거 → `%APPDATA%\Haehan AI` 가 남아 있는지, 재설치 시 `/setup` 없이 이전 계정으로 열리는지.
- 자동화 후보: 러너에서 setup.exe 를 `/S` 로 설치·제거하고 데이터 폴더 잔존을 확인하는 단계.

## ⑧ 이전 버전 위에 덮어 설치 시 데이터·설정·Claude 연결 유지 — 미자동화

- 새 버전을 이전 버전 위에 설치해도 `%APPDATA%\Haehan AI` 의 데이터·설정과 Claude 연결(Claude 설정에 추가된 Haehan AI 항목)이 유지되어야 한다.
- 현재 장치: 없음(**미자동화**). 자동 업데이트(`lib/updater.js`, 시험 `tests/test_desktop_auto_update.py`)는 업데이트 동작 자체의 시험이지 데이터 유지 검증이 아니다.
- 사람 확인: 이전 버전 설치·사용 → 새 버전 setup.exe 로 덮어 설치 → 기존 계정으로 자동 로그인, 설정 유지, Claude 연결 유지(연결 창이 다시 필수로 뜨지 않음).
- 자동화 후보: 이전 빌드 설치 → 데이터 생성 → 새 빌드 설치 → 데이터 잔존·health 확인.

## ⑨ 배포는 NAS만

- **정책(대표님 지시 2026-10-10 13:0x): 설치 파일(setup.exe)은 GitHub 에 올리지 않는다** — Releases 뿐 아니라 Actions 아티팩트에도 설치 파일 본체를 포함하지 않는다(종전 "Releases 금지, 아티팩트 3일 보관"에서 강화). GitHub Actions 는 빌드·설치본 내용물 점검·E2E 까지만 검증하고, 아티팩트는 unpacked 빌드와 로그만 남긴다(보관 기간은 워크플로 설정값 그대로, 설치 파일 보관 자체가 없으므로 "3일" 조항은 설치 파일에는 더 이상 적용 안 됨).
- 실배포용 설치 파일은 GitHub 검증을 통과한 **같은 커밋 sha** 로 이 PC(또는 지정 빌드 PC)에서 로컬로 다시 빌드한다. 로컬 빌드 절차는 `C:\work\_coordination\LOCAL_BUILD_PLAN.md`(참조 구현, 작성 중).
- 배포는 `scripts/ops/publish_release_to_nas.py <산출물 폴더> --version <yyyymmdd-sha7> [--execute]` 로 NAS(Nextcloud `배포/Haehan AI/<버전>/`)에만 한다. 옵션 없으면 dry-run 이고, 같은 버전 폴더가 이미 있으면 중단(덮어쓰기 금지)한다.
- 체크섬 동봉: 로컬 빌드에서 직접 `checksums.txt` 를 만들고, 게시 도구는 `HaehanAI-*.exe` 와 `checksums.txt` 를 필수로 요구하며 업로드 뒤 서버에서 SHA256 을 다시 계산해 대조한다(불일치 시 실패).
- 함께 올라가는 파일: `latest.yml`·`*.blockmap`(자동 업데이트용), `RELEASE_NOTES.md`, `설치_및_사용_안내.md`.
- 자동으로 막는 장치: `publish_release_to_nas.py`, 시험 `tests/test_publish_release_to_nas.py`, 워크플로의 설치 파일 미업로드 설정, "설치 파일은 GitHub(Releases·Actions 아티팩트 모두)에 올리지 않는다" 설정.
- 게시 전 조건: ①~⑥ 통과(GitHub 검증 + 로컬 실설치 시뮬레이션), E2E 실패 빌드(`UNVERIFIED-`) 아님.

## ⑩ 설치 안내서 — 미자동화

- 사용자에게 전달하는 문서: `docs/release/desktop/설치_및_사용_안내.md`.
- 반드시 들어가야 할 것:
  - **PC 보호 경고 넘기기**: 전자서명이 없어 "Windows의 PC 보호"(SmartScreen) 경고가 나올 수 있다 → "추가 정보" → "실행".
  - **앱 브라우저에서 구글 로그인**: 앱이 쓰는 브라우저(앱 전용 프로필)에서 구글에 로그인하는 방법.
  - 설치 기준(⑥)과 맞는 내용(설치 프로그램 사용, 관리자 불필요, 라이선스 안내가 기준과 어긋나지 않을 것).
- 현재 장치: 없음. 게시 전 `〔확정 전〕` 표시가 남아 있지 않은지 사람이 확인한다(**미자동화**). 자동화 후보: 게시 전에 안내서에서 `〔확정 전〕`·담당자용 문구가 남았는지 검사하는 단계.

---

## 출시 체크 순서 (요약)

1. Actions 에서 `Desktop Release Build` 성공(② 내용물 점검 통과, ③ E2E 통과) 확인(설치 파일은 아티팩트에 없음 — 검증 전용).
2. 같은 커밋 sha 로 로컬 빌드한 `setup.exe` 를 실제 PC 에 설치해 ⑤⑥ 확인.
3. ④ 전 화면 점검 실행, C 등급은 실행하지 않음.
4. ⑦⑧ 사람 확인(미자동화).
5. ⑩ 안내서 확인 후 ⑨ NAS 게시(`--execute`), 아티팩트는 3일 뒤 삭제.

## 미자동화 요약

⑦ 제거 시 데이터 보존, ⑧ 덮어 설치 시 데이터·연결 유지, ⑩ 안내서 점검. ④ 는 수동 실행(워크플로 단계 아님), ⑤⑥ 은 사람 확인.
