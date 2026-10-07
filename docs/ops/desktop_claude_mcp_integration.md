# 데스크톱 앱 ↔ 사용자 PC Claude(MCP) 연동

운영은 사용자별 로컬 설치(Electron 포터블/설치형)이고, 설치한 PC의 Claude Desktop·Claude Code 에서 Haehan AI 도구(MCP)를 쓸 수 있어야 한다.

## 구현 (admin-web/electron/lib/claude_mcp.js)
| 항목 | 내용 |
|---|---|
| 고정 경로(M6) | 번들 MCP(`resources/mcp/haehan-mcp`)를 `userData\mcp\<빌드>\` 로 복사(폴더 이름 = `resources/build-info.json` 의 빌드 버전 `yyyymmdd-sha7`, 없으면 `<앱버전>-<exe크기>`)(임시 폴더에 복사 후 rename — 원자적, 이미 있으면 건너뜀)하고 **그 경로**를 등록한다. 옛 빌드 폴더는 최근 2개만 남긴다. electron-builder portable 타깃은 실행마다 TEMP 아래로 리소스를 풀기 때문에(`unpackDirName` 기본값은 빌드마다 바뀌는 UUID 폴더, TEMP) `process.resourcesPath` 경로를 Claude 설정에 쓰면 앱 종료 뒤 경로가 사라질 수 있다 — 종료 시 삭제 여부는 공식 문서에 명시가 없어 **빌드 후 실제 PC 에서 확인**한다(설계는 어느 쪽이든 안전). |
| Claude Desktop(M1) | `%APPDATA%\Claude\claude_desktop_config.json` 의 `mcpServers.haehan-orchestrator` 만 추가·갱신. 쓰기 전 `.bak-<시각>` 백업(최근 5개 보존), tmp+rename 으로 쓰기, 다른 항목·설정·들여쓰기 보존, 같은 내용이면 쓰지 않음, 파싱 실패 시 건드리지 않고 안내. |
| Claude Code(M2) | 사용자 설정 파일을 직접 고치지 않고 공식 CLI 로: `claude mcp get/remove/add-json --scope user haehan-orchestrator …`. 같은 이름이 있으면 `~/.claude.json` 에서 이전 등록을 읽어 둔 뒤 지우고 새 경로로 다시 등록(갱신)한다. **add 가 실패하면 이전 등록으로 복원**하고, 복원까지 실패하면 수동 복구 명령을 안내한다. `claude` 명령이 없으면 건너뛰고 안내만 한다. |
| 앱 주소(M3) | 등록 env 로 `HAEHAN_FASTAPI_URL`(앱 주소)·`HAEHAN_DATA_DIR` 전달. `mcp_server.py` 는 `HAEHAN_FASTAPI_URL` → `HAEHAN_PORT` → 8401 순으로 주소를 정하고, 앱이 꺼져 연결이 거부되면 도구 응답으로 "Haehan AI 앱을 실행한 뒤 다시 시도하세요" 를 돌려준다. |
| 등록 시점 | 설치 후 **처음 실행 때 한 번 동의 창**(연결/나중에). 동의하면 자동 등록하고, 이후 새 빌드·앱 주소 변경 때는 조용히 갱신한다. 트레이 메뉴 **"Claude 연결" / "Claude 연결 해제"** 로 언제든 켜고 끌 수 있다(해제는 우리 항목만 지움). `window.localConfig.connectClaude/disconnectClaude/getClaudeStatus` 로 설정 화면에서도 호출 가능. |

## 시험
`tests/test_desktop_claude_mcp.py` (Node 단위 30개 + 주소 env + 앱 꺼짐 안내 + 배선), `admin-web/electron/tests/claude_mcp.test.js`. 모두 임시 폴더만 쓴다.

## 빌드 후 대표님 PC 점검 항목 (자동화 불가)
1. 포터블 exe 실행 → 처음 실행 동의 창이 뜨는지, "연결" 후 `%APPDATA%\Haehan AI\mcp\<버전-크기>\haehan-mcp.exe` 가 생겼는지.
2. **앱 종료 후에도** 위 폴더가 남아 있고 Claude Desktop 설정의 `command` 가 그 경로인지(임시 폴더 경로가 아닌지).
3. `claude_desktop_config.json` 에 기존 MCP 항목이 그대로 있고 `.bak-<시각>` 백업이 생겼는지. Claude Desktop 재시작 후 도구 목록에 haehan-orchestrator 가 보이는지.
4. Claude Code: `claude mcp list` 에 haehan-orchestrator 가 보이고, 새 세션에서 도구 호출이 되는지. (`claude` 가 .cmd 로 설치된 PC 와 .exe 로 설치된 PC 모두)
5. 앱을 끈 상태에서 Claude 가 도구를 부르면 "Haehan AI 앱을 실행한 뒤 다시 시도하세요" 가 나오는지, 앱을 켠 뒤 재시도가 되는지.
6. 트레이 "Claude 연결 해제" 후 두 설정에서 항목이 사라지고 다른 항목은 남는지. 앱을 새 빌드로 바꿔 실행했을 때 경로가 조용히 갱신되고 예전 폴더가 2개만 남는지.
7. 앱 포트를 `HAEHAN_FASTAPI_URL` 로 바꿔 실행했을 때 등록 env 가 갱신되는지.
