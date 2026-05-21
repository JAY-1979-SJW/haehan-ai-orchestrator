# HaehanAI-Agent.exe — GUI UX 설계서

- 공정: **AGENT_GUI_UX_DESIGN_SPEC_01**
- HEAD: `e2f7b88`
- 종류: **설계 문서 (코드 변경 없음)**
- 다음 구현 공정명: **AGENT_GUI_SIMPLIFY_IMPLEMENTATION_01**

---

## 1. 사용자 정의

### 1.1 일반 사용자 (Persona A) ⭐ HaehanAI-Agent.exe 의 대상
- **정체**: 시공 현장 / 사무실 / 외주 작업자
- **기술 수준**: Python / 명령줄 모름. Windows GUI 익숙
- **사용 빈도**:
  - 등록: **단 1회** (관리자 발급 코드 1회용)
  - 평소: **앱 보지 않음** (트레이 백그라운드)
  - 진단: **문제 발생 시에만** (월 1회 이하)
- **목표**: "내 PC 에서 알아서 돌게 두고 신경 쓰지 않기"
- **고통점**: 한글 안내 부재 / 무엇이 잘못됐는지 모름 / 재등록 절차 복잡

### 1.2 운영자 (Persona B) ❌ HaehanAI-Agent.exe 의 대상 아님
- **정체**: 관리자 / SRE / 개발자
- **사용 도구**: **`desktop/ui` React 앱** (별도) — admin dashboard / agent 목록 / task 관리 / 승인 / 로그
- **본 라인 (HaehanAI-Agent.exe) 와 분리** — 본 설계서 범위 외

### 1.3 결론
- HaehanAI-Agent.exe = **Persona A 전용 경량 에이전트**
- Persona B 가 보는 모니터링 / 로그 / 통계 / task 관리는 **본 앱에 두지 않는다**

---

## 2. 핵심 사용자 흐름

### 2.1 첫 실행 흐름
```
1. 사용자: HaehanAI-Agent.exe 더블클릭
2. 앱: 트레이 아이콘 표시 (회색 = 미등록) + 자동으로 등록 다이얼로그 1개 띄움
3. 사용자: 관리자에게 받은 등록코드 붙여넣기 → [등록]
4. 앱: register-with-code 호출 → device_token 저장 → wss 자동 연결
5. 앱: 트레이 아이콘 녹색 + 토스트 "연결됨"
6. 사용자: 다이얼로그 자동 닫힘. 이후 트레이만 남음.
```

### 2.2 평상시 흐름 (24/7)
```
- 트레이 아이콘 색만 변함 (녹색=정상, 주황=재연결중, 빨강=인증실패)
- 사용자 아무 행동 없음
```

### 2.3 PC 재부팅 후 흐름
```
1. (autostart 설정 시) 앱 자동 실행
2. Credential Manager 에서 device_token 로드
3. wss 자동 연결 → 녹색 트레이
```

### 2.4 인증 실패 (4401) 흐름
```
1. 트레이 아이콘 빨강 + 자동 popup "장치 인증 실패. 재등록이 필요합니다."
2. [재등록] 버튼 → 등록 다이얼로그 (서버 URL 자동 채움)
3. 사용자: 관리자에게 새 코드 받아 입력 → [등록]
4. 위 2.1 단계 5~6 으로 복귀
```

### 2.5 서버 접속 실패 흐름
```
1. 트레이 빨강 + popup "서버에 접속할 수 없습니다."
2. [재시도] / [진단] / [닫기]
3. 진단 → 서버 URL / 마지막 오류 / 권장 조치 텍스트 표시
```

### 2.6 진단 요청 흐름 (사용자가 관리자에게 보고 시)
```
1. 트레이 우클릭 → [진단]
2. 진단 창: 한 화면, 텍스트 9~10 줄
   - 서버 / WS URL (token query redact)
   - 상태 / 마지막 heartbeat / 마지막 오류
   - agent_id 마스킹
   - 권장 조치
3. [복사] 버튼 → 클립보드 (마스킹 적용본만)
4. 사용자: 관리자에게 메시지 첨부
```

### 2.7 재등록 흐름
```
1. 트레이 [재등록] → 확인 dialog "저장된 token 을 삭제합니다. 계속할까요?"
2. [확인] → Credential Manager 삭제 → 등록 다이얼로그
3. 이후 2.1 단계 3~5 와 동일
```

### 2.8 종료 흐름
```
1. 트레이 [종료] → 즉시 종료 (확인 dialog 없음 — 트레이 우클릭 자체가 명시적)
```

---

## 3. GUI 구조안 비교 (4종)

### 3.1 평가 기준
| 차원 | 가중치 |
|------|--------|
| 일반 사용자 이해도 | ★★★ |
| 구현 난이도 | ★★ |
| 유지보수성 | ★★★ |
| 보안 / PII 노출 위험 | ★★★ |
| exe 용량 영향 | ★★ |
| field test 적합성 | ★★ |
| 운영자 UI 와 중복 회피 | ★★★ |

### 3.2 A. 현재 4탭 풀 GUI (Dashboard / Registration / Logs / Settings)

| 차원 | 평가 |
|------|------|
| 이해도 | ✓ 명확하지만 페이지 4개 — Persona A 가 다 볼 일 없음 |
| 구현 난이도 | ✓ 이미 구현됨 |
| 유지보수 | ✗ 4페이지 = 코드 70% 가 사용 빈도 낮은 기능 |
| 보안 위험 | ⚠ Logs 탭 → token redact 잘 됐지만 실수 표면 증가 |
| exe 용량 | ✗ 14.7MB (sparkline / log buffer 등 무게) |
| field test 적합 | ⚠ 본 환경 PASS, 외부 PC 미검증 |
| 운영자 중복 | ✗ Dashboard sparkline / Logs export = 운영자(React)와 책임 중복 |
| **총평** | **over-engineering. Persona A 가 안 보는 페이지에 노력 집중됨** |

### 3.3 B. 트레이 중심 + 등록/진단 다이얼로그 ⭐ 권장

| 차원 | 평가 |
|------|------|
| 이해도 | ✓✓ 트레이만 보면 됨. 등록은 dialog 1개 |
| 구현 난이도 | ✓ 기존 코어 (gui_state/connection_diagnostics/token_store) 그대로 |
| 유지보수 | ✓✓ 코드 양 50% 감소 (Logs / Settings / Dashboard 페이지 제거) |
| 보안 위험 | ✓✓ 표시 면적 최소 → 실수 표면 작음 |
| exe 용량 | ✓ sparkline / PIL chart 제거 가능 → 12-13MB 추정 |
| field test 적합 | ✓ 트레이만 → SmartScreen 노출 표면 작음 |
| 운영자 중복 | ✓✓ 모니터링 / 로그 = 운영자 (React) 책임, 본 앱은 등록+heartbeat만 |
| **총평** | **Persona A 사용 패턴에 정확히 매칭. 사용 빈도 낮은 기능 제거** |

### 3.4 C. 단일 창 2탭 (연결 / 진단)

| 차원 | 평가 |
|------|------|
| 이해도 | ✓ 단순함 |
| 구현 난이도 | ✓ 중간 |
| 유지보수 | ✓ 4탭보다 깔끔 |
| 보안 위험 | ✓ |
| exe 용량 | ✓ 13MB 추정 |
| field test 적합 | ⚠ 사용자가 "창" 을 닫으면 백그라운드 인식 못 함 |
| 운영자 중복 | ✓ |
| **총평** | B 와 큰 차이 없으나, 창이 있어 시각적 무게 더 큼. B 가 더 깔끔 |

### 3.5 D. 첫 등록 wizard + 이후 tray only

| 차원 | 평가 |
|------|------|
| 이해도 | ✓✓✓ 가장 직관적 — wizard 1, 2, 3 step |
| 구현 난이도 | ⚠ wizard 별도 페이지 (3 step) — B 보다 약간 복잡 |
| 유지보수 | ✓ wizard 는 1회만 보이고 이후 사라짐 |
| 보안 위험 | ✓ |
| exe 용량 | ✓ B 와 유사 |
| field test 적합 | ✓✓ 첫 사용자 경험 우수 |
| 운영자 중복 | ✓ |
| **총평** | B 의 강화판. 등록 1회를 wizard 로 가이드하면 신규 사용자 만족도 ↑ |

### 3.6 비교 매트릭스

| 항목 | A 현재 | B 트레이 | C 2탭 | D wizard+tray |
|------|--------|----------|-------|----------------|
| Persona A 매칭 | △ | ✓✓ | ✓ | ✓✓✓ |
| 구현 난이도 | 이미 됨 | 중간 | 중간 | 약간 ↑ |
| 운영자 중복 회피 | ✗ | ✓✓ | ✓ | ✓✓ |
| exe 용량 | 14.7MB | ~12MB | ~13MB | ~12MB |
| 첫 사용자 친화 | △ | ✓ | ✓ | ✓✓✓ |
| 권장 순위 | 4 | **2** | 3 | **1** |

---

## 4. 최종 권장안

### 4.1 권장 = **D. 첫 등록 wizard + 이후 tray only**

**이유**:
1. **Persona A 사용 패턴 정확 매칭** — 등록 1회 + 트레이 24/7 + 진단 가끔
2. **첫 사용자 친화** — wizard 3 step 으로 가이드 (등록 / 연결확인 / 완료)
3. **운영자 (React) 와 책임 명확 분리** — 모니터링 / 통계 / 로그 = 운영자, 본 앱 = 개인 연결만
4. **코드 양 감소** — 현재 1837 라인 → 약 800-900 라인 예상 (Dashboard sparkline / Logs export / Settings 탭 제거)
5. **PII 표면 최소** — Logs 탭 (redact 실수 가능 표면) 제거 → 안전 마진 ↑
6. **exe 용량 감소** — sparkline PIL chart 코드 제거 → ~12MB

### 4.2 대안 (의견 불일치 시)
- **차선: B (트레이 중심 + 등록 다이얼로그)** — wizard 대신 단일 dialog. 거의 동등.
- ❌ 비추천: A (현재 4탭) — Persona A 에게 과함

---

## 5. 화면 설계

### 5.1 첫 등록 wizard (Step 1: 서버 확인)

```
┌──────────────────────────────────────────────┐
│  Haehan AI Local Agent                  ✕    │
├──────────────────────────────────────────────┤
│                                              │
│   ●━━━━━━━━━━━●─────●     Step 1 of 3        │
│                                              │
│   설치 환영합니다                            │
│                                              │
│   서버 URL                                   │
│   ┌────────────────────────────────────┐     │
│   │ https://haehan-ai.kr/orchestrator  │     │
│   └────────────────────────────────────┘     │
│   (관리자가 다른 URL 을 안내한 경우 변경)    │
│                                              │
│                       [ 다음 → ]              │
└──────────────────────────────────────────────┘
```

- 제목: "Haehan AI Local Agent — 설치 환영합니다"
- 표시: 서버 URL 입력 (기본값 채움)
- 버튼: [다음 →]
- 사용자 행동: 그대로 두거나 URL 수정 → [다음]
- 실패: URL 형식 잘못 → 입력 보더 빨강 + caption "올바른 URL 을 입력하세요"

### 5.2 첫 등록 wizard (Step 2: 등록코드)

```
┌──────────────────────────────────────────────┐
│  Haehan AI Local Agent                  ✕    │
├──────────────────────────────────────────────┤
│                                              │
│   ●━━━━━━━━━━━●━━━━━━━━━━━●─────  Step 2/3   │
│                                              │
│   등록코드 입력                              │
│                                              │
│   관리자에게 받은 1회용 코드 (10분 유효)     │
│   ┌────────────────────────────────────┐     │
│   │ ● ● ● ● ● ● ● ● ●                  │     │
│   └────────────────────────────────────┘     │
│   ☐ 입력 보이기                              │
│                                              │
│   [ ← 이전 ]              [ 등록 → ]          │
└──────────────────────────────────────────────┘
```

- 제목: "등록코드 입력"
- 표시: registration_code 입력 (show='●' 기본)
- 마스킹 토글: [입력 보이기] 체크박스
- 버튼: [← 이전], [등록 →]
- 성공: Step 3 으로 자동 전환
- 실패:
  - INVALID: "등록코드가 유효하지 않습니다. 다시 확인하세요." + 입력 보더 빨강
  - EXPIRED: "등록코드가 만료되었습니다. 관리자에게 새 코드를 요청하세요."
  - ALREADY_USED: "이미 사용된 코드입니다. 새 코드를 요청하세요."
  - SERVER_NOT_REACHABLE: "서버에 접속할 수 없습니다. URL/네트워크를 확인하세요."

### 5.3 첫 등록 wizard (Step 3: 완료)

```
┌──────────────────────────────────────────────┐
│  Haehan AI Local Agent                  ✕    │
├──────────────────────────────────────────────┤
│                                              │
│   ●━━━━━━━━━━━●━━━━━━━━━━━●  Step 3 of 3     │
│                                              │
│             ✓                                │
│        등록 완료                             │
│                                              │
│   agent_id    la-9bc***22df                  │
│   상태        ● 연결됨                        │
│                                              │
│   앞으로 백그라운드에서 자동 실행됩니다.     │
│   트레이 아이콘에서 상태를 확인할 수 있습니다.│
│                                              │
│   ☑ Windows 시작 시 자동 실행                │
│                                              │
│                       [ 시작하기 ]            │
└──────────────────────────────────────────────┘
```

- 제목: "등록 완료"
- 표시: agent_id 마스킹, 연결 상태, autostart 토글 (옵션)
- 버튼: [시작하기] → 창 닫히고 트레이만 남음

### 5.4 진단 다이얼로그 (트레이 우클릭 → [진단])

```
┌──────────────────────────────────────────────┐
│  진단                                   ✕    │
├──────────────────────────────────────────────┤
│                                              │
│   상태               ● 연결됨                │
│   agent_id           la-9bc***22df           │
│   서버               https://haehan-ai.kr/.. │
│   WS                 wss://haehan-ai.kr/...  │
│   마지막 heartbeat   2026-05-21 14:23:01     │
│   재연결 횟수        0                       │
│   마지막 오류        —                       │
│                                              │
│   조치: —                                    │
│                                              │
│   [ 복사 ]   [ 재등록 ]   [ 닫기 ]            │
└──────────────────────────────────────────────┘
```

- 제목: "진단"
- 표시: 9 필드 모두 마스킹 적용
- [복사]: 클립보드에 텍스트 (token / agent_id 풀버전 절대 없음)
- [재등록]: 5.5 로 이동
- [닫기]: 창 닫음 (앱은 트레이 유지)

### 5.5 재등록 확인 다이얼로그

```
┌──────────────────────────────────────────┐
│  재등록 확인                        ✕    │
├──────────────────────────────────────────┤
│                                          │
│   저장된 device_token 을 삭제하고        │
│   재등록 화면으로 이동합니다.            │
│                                          │
│   이후 새 등록코드가 필요합니다.         │
│                                          │
│        [ 취소 ]      [ 삭제 후 재등록 ]   │
└──────────────────────────────────────────┘
```

### 5.6 오류 안내 (popup toast)

종류별 다른 popup:

- **인증 실패 (4401)**: 자동 popup
  ```
  ⚠ 장치 인증 실패
  device_token 이 변경되었거나 폐기되었을 수 있습니다.
  재등록이 필요합니다.
  [ 재등록 ]   [ 나중에 ]
  ```

- **서버 접속 실패**: 자동 popup
  ```
  ⚠ 서버에 접속할 수 없습니다
  네트워크 또는 서버 URL 을 확인하세요.
  [ 재시도 ]   [ 진단 ]   [ 닫기 ]
  ```

- **token 저장 실패**:
  ```
  ⚠ token 저장 실패
  Windows Credential Manager 에 접근할 수 없습니다.
  관리자 권한으로 다시 시도하세요.
  [ 닫기 ]
  ```

- **registration_code 만료/재사용**:
  - wizard step 2 의 caption 영역에 표시 (별도 popup 불필요)

### 5.7 트레이 메뉴

```
┌───────────────────────┐
│ ● 연결됨               │ ← 상태 표시 (비활성)
├───────────────────────┤
│ 진단...                │
│ 재등록...              │
├───────────────────────┤
│ Windows 시작 시 자동실행│ ← 토글
├───────────────────────┤
│ 종료                   │
└───────────────────────┘
```

상태별 트레이 아이콘 색:
- 녹색 = HEARTBEAT_OK / CONNECTED
- 주황 = CONNECTING / AUTHENTICATING / RECONNECTING
- 빨강 = AUTH_FAILED / SERVER_UNREACHABLE
- 회색 = NOT_REGISTERED / DISCONNECTED

---

## 6. 탭/메뉴 결정

### 6.1 제거 항목 (현재 GUI 에서 빼는 것)
- ❌ **Dashboard 탭** — sparkline / Network 카드 → Persona A 가 안 봄, 운영자가 React 에서 봄
- ❌ **Logs 탭** — 1000-line buffer / export → Persona A 가 안 씀, 운영자가 봄. redact 표면 ↓
- ❌ **Settings 탭** — 서버 URL 변경 / autostart 외 대부분 불필요. autostart 만 트레이 메뉴로 이관

### 6.2 유지 / 이동 항목
- ✅ **Registration** → wizard 로 변환 (3 step)
- ✅ **진단** → 다이얼로그 1개 (탭 없음)
- ✅ **재등록** → 확인 다이얼로그 1개
- ✅ **트레이 메뉴** → 상태 + 진단 + 재등록 + autostart + 종료

### 6.3 판단 근거 표
| 기능 | 매일 보는가 | 문제 해결에 필요 | 운영자 중복 | 보안 노출 | 결정 |
|------|-------------|-------------------|--------------|------------|------|
| Dashboard sparkline | ✗ | ✗ | ✓ | △ | **제거** |
| Logs 탭 | ✗ | △ (진단 1줄로 충분) | ✓ | ⚠ | **제거** |
| Settings 서버 URL | ✗ (1회) | △ | — | — | **wizard step 1 로 흡수** |
| autostart 토글 | ✗ (1회) | — | — | — | **트레이 메뉴로 이관** |
| 진단 | ✗ (가끔) | ✓✓ | △ | △ | **다이얼로그 유지** |
| 등록 | ✗ (1회) | ✓✓ | — | ✓✓ | **wizard 유지** |

---

## 7. 상태/오류 UX

### 7.1 상태 source 단일화
- 단일 진실 = `gui_state.GuiController`
- 표시 위치 (전부 동일 source):
  - 트레이 아이콘 색
  - 트레이 메뉴 첫 줄 ("● 연결됨")
  - 진단 다이얼로그 "상태" 행
  - 오류 popup (특정 상태일 때만)

### 7.2 상태 → UX 매핑
| 상태 | 트레이 아이콘 | 트레이 메뉴 | 자동 popup |
|------|---------------|---------------|------------|
| NOT_REGISTERED | 회색 | "● 미등록" | wizard 자동 열기 (첫 실행 시) |
| CONNECTING | 주황 (점멸) | "● 연결 중…" | — |
| AUTHENTICATING | 주황 (점멸 빠르게) | "● 인증 중…" | — |
| CONNECTED | 녹색 | "● 연결됨" | — |
| HEARTBEAT_OK | 녹색 (subtle pulse) | "● 정상" | — |
| RECONNECTING | 주황 (점멸) | "● 재연결 중…" | 5분 지속 시 1회 |
| AUTH_FAILED | 빨강 | "● 인증 실패" | **자동 popup (재등록 요청)** |
| SERVER_UNREACHABLE | 빨강 | "● 서버 접속 실패" | **자동 popup (재시도/진단)** |
| TOKEN_NOT_STORED | 회색 | "● 토큰 없음" | **자동 popup (재등록 안내)** |
| DISCONNECTED | 회색 | "● 끊김" | — |

### 7.3 오류별 사용자 안내

| 오류 코드 | 사용자 문구 | 권장 행동 | 재시도 | 재등록 |
|-----------|------------|----------|---------|---------|
| REG_CODE_EXPIRED | "등록코드 만료. 새 코드를 요청하세요." | 관리자 연락 | ✗ | wizard 유지 (코드만 재입력) |
| REG_CODE_INVALID | "등록코드가 유효하지 않습니다." | 코드 재확인 | ✗ | wizard 유지 |
| REG_CODE_ALREADY_USED | "이미 사용된 코드. 새 코드를 요청하세요." | 관리자 연락 | ✗ | wizard 유지 |
| AUTH_FAILED_4401 | "장치 인증 실패. 재등록이 필요합니다." | 재등록 | ✗ | **버튼 표시** |
| TOKEN_NOT_STORED | "device_token 없음. 데스크앱을 다시 등록하세요." | 재등록 | ✗ | **버튼 표시** |
| SERVER_NOT_REACHABLE | "서버에 접속할 수 없습니다." | URL / 네트워크 확인 | **표시** | ✗ |
| NETWORK_BLOCKED_PROXY | "회사 프록시/방화벽 차단 의심." | IT 부서 연락 | ✗ | ✗ |
| HEARTBEAT_LOST | "heartbeat 끊김. 재연결 중." | 대기 (자동 재시도) | ✗ | ✗ |
| TOKEN_STORE_FAIL | "Credential Manager 접근 실패." | 관리자 권한 재실행 | **표시** | ✗ |

---

## 8. PII / 보안 UX

### 8.1 절대 화면 표시 금지
- **device_token** — 어디서도 표시 0
- **registration_code** — 입력창에만 (show='●'), 변수에서 즉시 폐기

### 8.2 마스킹 규칙
- **agent_id** — 어디서나 `la-xxx***yyy` 형식 (`mask_agent_id` 사용)
- **server URL query** — token / device_token / registration_code / authorization / session / api_key / bearer 키는 `[REDACTED]` 치환
- **클립보드 복사 ([복사] 버튼)** — 동일 마스킹 적용본만

### 8.3 입력 마스킹
- registration_code 입력 — `show='●'` 기본
- [입력 보이기] 토글로 잠시 평문 (사용자 확인용)
- wizard step 전환 시 자동 입력창 비우기

### 8.4 폐기 정책
- 등록 worker 함수 종료 직전 `device_token = ""`, `code = ""` 명시
- 메모리 객체에서 즉시 참조 끊기
- 디버그/예외 메시지에 토큰 변수명 절대 안 씀

### 8.5 클립보드 / 스크린샷
- 진단 [복사]: 마스킹된 텍스트만 (raw token 0)
- 스크린샷 가이드 (런북): "agent_id 마스킹 형태인지 확인 후 첨부"
- 스크린샷 자동 캡처 없음

### 8.6 로그 정책
- **본 앱은 로그 파일 미생성** — Logs 탭 제거와 함께 1000-line buffer 도 제거
- stdout/stderr 로그도 redact 적용 (이미 connection_diagnostics 가 처리)
- 진단 텍스트는 메모리 only

---

## 9. 디자인 스타일

### 9.1 창 크기
- wizard: **560 × 480** (다이얼로그 느낌)
- 진단: **480 × 360**
- 재등록 확인: **400 × 200**
- 메인 윈도우 **없음** (트레이 only)

### 9.2 테마 / 색상
- **Dark 기본** (Windows 11 시스템 테마 따라 옵션)
- 배경 `#0F1115`, 카드 `#1A1D24`
- 텍스트 `#E6E9EF` / dim `#9AA3B2`
- accent `#6366F1` (primary 버튼)
- 상태: 녹색 `#10B981` / 주황 `#F59E0B` / 빨강 `#EF4444` / 회색 `#6B7484`

### 9.3 폰트
- 본문: **Segoe UI** 12
- 라벨: Segoe UI 10
- agent_id / URL: **Consolas** 11
- 헤더: Segoe UI 16 semibold

### 9.4 버튼 hierarchy
- **Primary** (accent 채움): 등록, 다음, 시작하기
- **Secondary** (보더): 진단, 복사, 닫기, 이전
- **Danger** (red 보더, 투명 채움): 삭제 후 재등록
- **Ghost** (텍스트만): 나중에, 취소

### 9.5 spacing
- 8px grid
- 다이얼로그 내부 padding 24px
- 버튼 hgap 8px

### 9.6 아이콘
- unicode glyph (●, ✓, ⚠, →, ←) — 추가 의존성 없음
- 트레이 아이콘만 PIL 동적 색 원

### 9.7 모션
- wizard step 전환: 200ms ease fade
- 상태 pulse: HEARTBEAT_OK 시 4s 천천히 (안정감)
- AUTH_FAILED popup: 페이드 인 (튀어나오기 없음)

---

## 10. 구현 우선순위

### 10.1 MVP (즉시 구현 — `AGENT_GUI_SIMPLIFY_IMPLEMENTATION_01` 공정)
1. **wizard 3 step** (Step 1 서버 / Step 2 등록코드 / Step 3 완료)
2. **트레이 메뉴 단순화** (상태 / 진단 / 재등록 / autostart / 종료)
3. **진단 다이얼로그 1개** (10 필드 + 복사 + 재등록 / 닫기)
4. **재등록 확인 다이얼로그**
5. **오류 popup 3종** (AUTH_FAILED, SERVER_UNREACHABLE, TOKEN_NOT_STORED)
6. **상태 source 단일화 유지** (gui_state.GuiController)
7. **PII 마스킹 정책 유지** (mask_agent_id, _strip_secrets_from_url)
8. **CLI 모드 회귀 유지** (--self-test / --diagnostics / --register / --agent-id / --reset)

### 10.2 Later (후속 공정)
- **autostart 등록** (Windows Registry HKCU\Software\Microsoft\Windows\CurrentVersion\Run)
- **CODE_SIGNING_01** (코드 서명 인증서)
- **AUTO_UPDATE_01** (zip 자동 다운로드 + sha256 검증)
- **EXTERNAL_FIELD_TEST_INTAKE_01** (외부 PC 결과 통합)

### 10.3 하지 않음 (본 앱 범위 외)
- ❌ 운영자 task 관리 / 승인 / 통계 → React 운영자 UI
- ❌ admin dashboard 임베드
- ❌ React UI 와 통합 / 호스팅
- ❌ heartbeat sparkline (운영자만)
- ❌ Logs 파일 export (운영자만)
- ❌ task delivery 알림

---

## 11. 구현 가이드 (다음 공정 — AGENT_GUI_SIMPLIFY_IMPLEMENTATION_01)

### 11.1 파일별 변경 예상
| 파일 | 변경 |
|------|------|
| `gui_app.py` | 전면 재작성 — 4탭 → wizard + 진단 dialog (코드 ~50% 감소) |
| `gui_tray.py` | 메뉴 단순화 (상태 + 진단 + 재등록 + autostart + 종료) |
| `gui_state.py` | 변경 없음 (상태 머신 그대로) |
| `gui_log_buffer.py` | **제거** (Logs 탭 폐지) — 또는 connection_diagnostics 의존성으로 흡수 |
| `gui_icons.py` | sparkline 제거 (tray dot + spinner 만 유지) |
| `desktop_launcher.py` | 변경 없음 |
| `scripts/build_desktop_agent_windows.py` | hidden imports 정리 (불필요 의존성 제거) |
| 테스트 | `test_local_agent_gui_pages.py` 일부 → wizard 테스트로 변환 |

### 11.2 회귀 보장 필수
- CLI (--self-test / --diagnostics / --register / --agent-id / --reset) 0 회귀
- gui_state 단위 테스트 100% 유지
- token leak 검사 동일 또는 강화

### 11.3 빌드 / smoke
- PyInstaller 재빌드 후 sha256 갱신
- wizard 첫 실행 시 정상 표시
- 등록 → 트레이로 전환 확인
- 트레이 [진단] 클릭 → 다이얼로그
- 5초 GUI launch smoke (audit 자동)

---

## 12. desktop/ui (React 운영자 앱) 미수정

본 설계서는 **`HaehanAI-Agent.exe` 라인 한정**.

- `desktop/ui/*` — 절대 수정 안 함
- `desktop/ui_dist/*` — 절대 수정 안 함
- React / Vite / Tailwind / shadcn 구조 — 건드리지 않음
- 운영자 admin UI — 분리 유지

만약 사용자 등록/wss 흐름을 React 앱에 통합하려면 별도 공정 **`REACT_GUI_AGENT_INTEGRATION_01`** 으로 진행.

---

## 13. 결정 / 승인 요청

본 설계서 승인 시:
- 다음 공정 = **`AGENT_GUI_SIMPLIFY_IMPLEMENTATION_01`**
- 작업 범위: §10.1 MVP 8 항목
- 예상 산출:
  - `gui_app.py` 재작성
  - `gui_tray.py` 메뉴 단순화
  - `gui_icons.py` slim
  - `gui_log_buffer.py` 제거 또는 통합
  - 신규 테스트 (wizard 흐름 단위)
  - audit + smoke + commit

승인 의견:
- (a) 권장 D (wizard + tray) 그대로 진행
- (b) 차선 B (단일 dialog + tray) 로 변경
- (c) 일부 수정 (특정 화면 / 색 / 단축키)
- (d) 보류 — 추가 검토 필요

---

## 14. 다음 공정명

**`AGENT_GUI_SIMPLIFY_IMPLEMENTATION_01`** — 본 설계서 §10.1 MVP 구현
