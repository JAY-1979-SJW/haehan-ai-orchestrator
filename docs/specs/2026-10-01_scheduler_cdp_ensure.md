# 예약(주기) 작업 실행 시 CDP 보장 — 기준서 v1

- 날짜: 2026-10-01 / 사용자 요청: "앱에서 예약작업을 요청하면 CDP가 실행되게 해줘" · 범위 결정: **기존 스케줄러에 CDP 보장**(사용자 예약 화면 신설은 제외)
- 레이어: L3 Connectors(`scripts/community/scheduler.py`). API 응답 key·DB·보안 정책 변경 없음.

## 현황 (실측)
| 스케줄러 | 기본 | 브라우저 |
|---|---|---|
| 커뮤니티 자율 분석(`community_schedule_loop`) | 켜짐 | **사용** — `run_all_sites` 가 `get_page()`, 일부 사이트(ohou 등)는 `CDP(9222)` 직접 연결 |
| gonobi(`gonobi_schedule_loop`) | 켜짐 | 안 씀(`requests`) |
| 네이버 검색(`schedule_loop`) | 꺼짐 | 안 씀(OpenAPI) |
- `get_page()` → `_get_cdp_port()` → 9222 가 꺼져 있으면 `_ensure_cdp_daemon()` 이 이미 CDP 를 자동 기동한다. 데몬(`cdp_daemon.py`)과 `cdp_force_start.py` 는 같은 9222·같은 프로필을 쓰므로 포트 불일치는 없다. 샌드박스 게이트는 샌드박스 런타임에서만 막는다.
- 앱(Electron)에는 사용자가 예약을 거는 화면이 없고, 예약은 서버 lifespan 의 고정 주기 루프뿐이다.

## 변경
`run_all_sites` 가 사이트 루프에 들어가기 **전에** `get_page()` 를 한 번 호출해 CDP 를 먼저 보장한다.
- 성공: 이후 사이트별 `get_page()`·직접 연결(9222)은 이미 떠 있는 브라우저를 쓴다.
- 실패(기동 불가): 사이트마다 반복 실패하지 않고, 전체 사이트를 `error: "CDP 브라우저 기동 실패: …"` 로 한 번에 기록하고 수집은 건너뛴다(리포트·상태 저장은 그대로).

## 검증
단위 테스트 `tests/test_community_scheduler_cdp.py`: (1) 사이트 수집 전에 `get_page` 가 먼저 호출됨 (2) 기동 실패 시 수집 함수가 호출되지 않고 모든 사이트가 CDP 오류로 기록됨 (3) 사이트가 없으면 브라우저를 건드리지 않음.
