# MCP 서버 CDP 연결 통일 기준서

작성: 2026-09-30 · 관련 이슈: #45 · 상태: 사용자 "다 처리" 지시(2026-09-30)로 진행

## 1. 문제 (실측)
`ai_orchestrator/server/mcp_server.py` 에 도구 호출마다 `sync_playwright()` + `connect_over_cdp("http://127.0.0.1:9222")` 로
**새 연결을 맺는 지점이 6곳**(`_cdp_collect`, `_open_seller_center`, `_list_cafe_boards`, `_add_cafe_board`,
`_auto_register_product`, `_edit_product`) 있다. `CLAUDE.md` 가 금지한 패턴이다. 2026-09-30 `list_cafe_boards` 가
300초 멈췄고(`running_timeout`), 같은 조건에서 브라우저가 오염되면 새 연결의 핸드셰이크(`retrieving websocket`)가
45초 이상 멈춘다는 것을 재현했다(브라우저 재시작 후 0.4초로 복구).
추가로 `_cdp_collect`, `_open_seller_center` 는 `contexts[0].pages[0]`(첫 탭)을 무조건 잡아 **사용자가 보던 탭을 덮어쓴다**.

## 2. 이미 있는 좋은 패턴
`_get_universal_page()` (snapshot_page/act_on_page 용) 는 이 MCP 프로세스 수명 동안 연결 1개를 `_universal_browser` 에 보관하고,
죽으면 재연결한다. 이 패턴을 **재사용**한다(새 방식을 만들지 않는다).

## 3. 변경
| 파일 | 변경 |
|---|---|
| `ai_orchestrator/server/mcp_server.py` | 공용 헬퍼 `_cdp_context()` 추가(= `_get_universal_page` 와 같은 캐시 사용, context 반환). 6곳의 독자 연결을 이 헬퍼로 교체 |
| `tests/test_mcp_shared_cdp.py` (신규) | 소스 검사로 "도구 함수에 `sync_playwright()`/`connect_over_cdp` 직접 호출이 없다" 고정, 헬퍼 동작은 가짜 playwright 로 검증 |

- 탭 선택: 도구별로 필요한 탭을 명시한다. 셀러센터 이동/수집은 **새 탭**(`context.new_page()`) 을 열어 쓰고 끝나면 닫는다(사용자 탭 미침범).
  이미 스마트스토어 탭이 열려 있으면 그 탭을 재사용한다(URL 에 `smartstore` 포함).
- 연결 실패 시: 기존과 같은 `{ok: False, error, hint}` 반환(예외 전파 안 함). 오류 메시지는 값 없이 유형만.
- 캐시된 연결이 죽었으면 1회 재연결 후 실패하면 hint 로 브라우저 재시작(`cdp_force_start.py stop/start`)을 안내.

## 4. 변경하지 않는 것
도구 이름·스키마·반환 키(`ok`, `error`, `hint`, `dry_run` 등), `snapshot_page/act_on_page/navigate_page` 동작, FastAPI 쪽 공유 연결, DB, 외부 호출.

## 5. 위험과 대응
| 위험 | 대응 |
|---|---|
| 캐시 연결이 죽은 채 재사용 | 사용 전 `page.url` 접근 대신 `browser.is_connected()` 확인, 죽으면 재연결 |
| 새 탭이 남음 | `try/finally` 에서 닫기 |
| 스마트스토어 폼 도구가 기존 폼 탭을 찾던 동작 | 기존 로직(`products/create` 탭 재사용, 없으면 새 탭) 그대로 유지 — 연결 부분만 교체 |

## 6. 검증
1. 단위: 헬퍼 재사용/재연결, 소스에 독자 연결 0건
2. 실제(읽기 전용): 재시작된 CDP 브라우저에서 `list_cafe_boards` 를 AI 창으로 호출해 300초 멈춤이 사라졌는지
3. 게이트: ruff 신규 위반 0, 레이어 감사, 영향 테스트 전/후 대조

롤백: `git revert`.
