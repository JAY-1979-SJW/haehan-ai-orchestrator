/**
 * lib/bus.js — 데스크톱 메인 프로세스 내부 이벤트 버스 (통신 채널)
 *
 * 목적: lib/* 모듈이 서로를 직접 import 하지 않고, 이 버스를 통해
 *       pub/sub 로만 통신하도록 분리(decoupling)한다.
 *   - 발행자(tray 등): bus.emit(EVENTS.X, payload)
 *   - 구독자(main 등): bus.on(EVENTS.X, handler)
 *
 * 규칙: 모듈 간 직접 호출/직접 import 대신 이벤트로 통신한다.
 *       (config 같은 순수 설정/상수 모듈은 예외 — 공유 계약 계층)
 */
const { EventEmitter } = require("events");

// 이벤트 이름 계약 — 오타 방지 및 단일 출처
const EVENTS = Object.freeze({
  // 창 표시/복원 요청 (트레이 클릭, 두번째 인스턴스, activate 등)
  SHOW_WINDOW: "window:show",
  // YouTube 계정 (재)연결 요청 (트레이 메뉴, 셸 버튼)
  YOUTUBE_RECONNECT: "youtube:reconnect",
  // YouTube 연결 상태 변경 통지 (connected | failed | disconnected)
  YOUTUBE_STATUS: "youtube:status",
  // 앱 종료 요청
  APP_QUIT: "app:quit",
  // Windows 시작 시 자동 실행 토글 요청
  TOGGLE_AUTO_LAUNCH: "app:toggle-auto-launch",
  // 시스템 Chrome 프로필 사용 토글 (사용자 Chrome 세션 공유)
  TOGGLE_SYSTEM_CHROME: "cdp:toggle-system-chrome",
});

// 단일 버스 인스턴스 (메인 프로세스 전역). 핸들러 수가 많지 않으므로 경고 한도만 상향.
const bus = new EventEmitter();
bus.setMaxListeners(32);

module.exports = { bus, EVENTS };
