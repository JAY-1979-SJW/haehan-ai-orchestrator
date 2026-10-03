# CDP 브라우저 감시 로그 (탭 생성·이동·종료 기록) — 기준서

- 날짜: 2026-09-30 / 상태: **드라이런 완료, 사용자 승인 대기**
- 배경: 사용자가 "브라우저 탭이 2개 실행되고, 네이버에서 다른 탭이 열려 여러 사이트로 이동했다"고 보고. 지금은 누가·언제·어디로 이동시켰는지 남는 기록이 없어 원인을 추적할 수 없다.
- 기존 구현 확인(capability_check cdp navigation tab): 없음. 조각만 있음 — `scripts/naver/smartstore/navigation/cdp_popup_manager.py`(팝업 처리), `local_agent/browser/agent.py`.

## 1. 설계
| 항목 | 내용 |
|---|---|
| 방식 | 브라우저 레벨 CDP 웹소켓(`/json/version` 의 webSocketDebuggerUrl)에 붙어 `Target.setDiscoverTargets` 이벤트만 구독. **Playwright 연결을 새로 맺지 않는다**(CLAUDE.md gotcha: 매번 새 연결 금지·핸드셰이크 멈춤). 페이지에 붙지 않으므로 자동화에 간섭 0 |
| 기록 대상 | 탭(type=page)의 `opened` / `navigated`(URL 변경) / `closed`. 필드: ts, event, target_id, url(300자), title(80자), opener_id |
| 위치 | 신규 `scripts/ops/browser_watch.py` (운영 도구, 순수 로깅). 로그 `data/logs/browser_watch.jsonl` (5MB 넘으면 `.1` 로 회전, 1세대만 유지) |
| 기동 | `scripts/cdp_force_start.py start` 가 감시 프로세스를 분리 기동(이미 떠 있으면 생략, PID 파일 `data/browser_watch_pid.json`), `stop` 이 함께 종료. 브라우저가 죽으면 감시는 재접속을 반복(2초 간격)하고 브라우저 부재 시 조용히 대기 |
| 이상 표시 | 같은 탭이 60초 안에 서로 다른 도메인 5곳 이상으로 이동하면 `anomaly: chain_navigation` 줄 추가 기록. 동시에 page 탭 3개 초과면 `anomaly: many_tabs` |
| 민감정보 | URL 쿼리스트링은 값 마스킹(`?a=***`) — 토큰·인증 코드가 로그에 남지 않게 함. 경로까지만 원문 |
- 레이어/의존: 외부 의존 `websocket-client`(이미 requirements). 서버·DB·API 응답·정책 변경 없음. 로그만 추가.

## 2. 드라이런 (실제 브라우저, 저장소 미변경)
시제품을 임시 폴더에서 25초 실행, 별도 탭을 만들어 example.com → naver.com 으로 이동 후 닫음.
- 기록됨: 기존 탭 2개(네이버 블로그 홈, Google 계정) `opened`, 신규 탭 `opened(about:blank)` → `navigated` 2회 → `closed`. 시각·URL·제목 정상.
- 사용자 탭은 조작하지 않음. 자동화에 대한 부작용 없음(페이지 미접속).
- **한계(확인함)**: CDP 는 "어느 프로세스가 이동시켰는지"를 알려주지 않는다. 탭이 왜 열렸는지는 기록만으로는 부분적으로만 추정 가능(opener_id 가 있으면 부모 탭 표시).

## 3. 2단계(이번 승인 범위 밖, 로그 몇 건 쌓인 뒤 결정)
- 원인 귀속: `scripts/web_connector.py` 의 `open_page`/`get_page`/`goto` 호출 지점에서 호출자 스택 1줄(파일:함수)을 같은 로그에 `caller` 로 남김. 로그로 의심 경로가 좁혀지면 그 경로부터.
- 이번 탭 이상현상의 근본 원인은 **아직 모름** — 로그 확보 후 분석한다.

## 4. 실행 순서(승인 후)
1. `scripts/ops/browser_watch.py` + 단위 테스트(이벤트→기록, 쿼리 마스킹, 회전, 이상판정, 재접속) → 2. `cdp_force_start.py` start/stop 연동 → 3. 실제 브라우저로 기동·이동 재현 확인 → 4. 게이트 3종 + 변이 시험 → 5. 커밋·PR(병합은 사용자)
- 되돌리기: 커밋 revert. 감시 프로세스는 `cdp_force_start.py stop` 으로 종료.
