# HaehanAI-Agent.exe — OpenAI BYOK UX 설계서

- 공정: **AGENT_DESKTOP_UI_OPENAI_KEY_UX_SPEC_01**
- HEAD: `596494f`
- 종류: **설계 문서 (코드 변경 없음)**
- 다음 구현 공정명: **`AGENT_OPENAI_BYOK_KEY_STORE_01`** → **`AGENT_OPENAI_CHAT_CLIENT_01`** → **`AGENT_GUI_CHAT_IMPLEMENTATION_01`**

---

## 1. 기존 설계 검토

### 1.1 검토 대상
- `docs/design/local_agent_gui_ux_design_spec_20260521.md` (1차 — wizard + tray only)
- `docs/design/local_agent_gui_ux_design_spec_ai_chat_amend_20260521.md` (2차 — wizard + tray + 3탭)

### 1.2 검토 결과
| 항목 | 결과 |
|------|------|
| wizard + tray + 3탭 구조 | ✅ **유지** (사용 흐름 적합) |
| Chat 기본 탭 | ✅ **유지** (AI 비서 앱 기본 진입) |
| Status / Diagnostics 탭 구성 | ✅ **충분** |
| OpenAI API key 설정 위치 | ⚠ **재검토 필요** — 기존 설계에는 없었음 |
| Settings 탭 재도입 여부 | ❌ **하지 않음** — modal 로 대체 |
| AI Settings 탭 신설 | ❌ **하지 않음** — 탭 수 증가 부담 |

→ **3탭 유지 + Settings modal 추가** 가 보정 방향.

---

## 2. OpenAI API key 사용 방식 (확정)

### 2.1 BYOK (Bring Your Own Key) 채택
- 사용자가 **자신의 OpenAI API key** 를 직접 입력
- key 는 **Windows Credential Manager** 에 저장 (기존 `token_store.py` 모듈 패턴 재사용)
- 앱 화면에는 **key 원문 절대 표시 안 함**
- 저장 후 표시: **`sk-****abcd`** (앞 3자 + last4)
- 버튼: **[연결 테스트] / [교체] / [삭제]**

### 2.2 절대 금지
- exe 에 API key 하드코딩 0
- git / json / log / report / clipboard 에 API key 저장 0
- 서버로 API key 전송 0 (BYOK 의 핵심 — server 는 key 를 모름)
- 화면에 key 원문 재표시 0
- diagnostics export 에 key 원문 0
- 동일 PC 의 다른 앱이 읽을 수 있는 위치 평문 저장 0

### 2.3 저장 backend 우선순위
1. **Windows Credential Manager** (keyring `WinVaultKeyring`)
2. 평문 fallback: **기본 OFF**. 사용자가 명시적으로 옵트인해야 활성 (별도 공정에서 정책 결정).

### 2.4 saved-state 표현 (UI)
- "저장됨 · sk-****abcd · 마지막 테스트 2026-05-21 14:23"
- "저장 안 됨 — [AI 설정] 에서 입력하세요"
- "오류: API_KEY_INVALID — 마지막 테스트 시 키가 거부됨. 교체하세요"

---

## 3. UI 구조 재검토 (4 후보)

### 3.1 A. 기존 3탭 유지 + Chat 상단 inline key 패널
| 차원 | 평가 |
|------|------|
| 초보 이해도 | △ Chat 화면이 어수선해짐 |
| 보안 노출 위험 | △ key fingerprint 가 항상 Chat 에 보임 |
| 설정 빈도 | 낮음 — 매번 보일 필요 없음 |
| 권장 | ❌ |

### 3.2 B. 4탭 (Chat / Status / Diagnostics / AI Settings)
| 차원 | 평가 |
|------|------|
| 초보 이해도 | ✓ 탭 이름 명확 |
| 탭 수 증가 | ✗ 4탭 — 인지 부담 |
| 설정 빈도 | 낮음 (1~2회) → 별도 탭으로 두기 과함 |
| 권장 | △ 차선 |

### 3.3 C. 3탭 유지 + Settings modal ⭐ 권장
| 차원 | 평가 |
|------|------|
| 초보 이해도 | ✓ 기본 3탭 그대로 |
| 보안 노출 표면 | ✓ modal 열 때만 표시 |
| 설정 빈도 | ✓ 1~2회 — modal 적합 |
| 확장성 | ✓ provider 추가 시 modal 안에서 dropdown |
| 권장 | ⭐ **최적** |

### 3.4 D. Wizard 에 OpenAI key 입력 포함
| 차원 | 평가 |
|------|------|
| 첫 사용자 흐름 | ✗ wizard 가 길어짐 (4 step) |
| 혼동 위험 | ✗ **registration_code 와 OpenAI API key 혼동** 가능 |
| 강제성 | ✗ key 없어도 등록 자체는 가능해야 함 |
| 권장 | ❌ |

### 3.5 비교 매트릭스

| 항목 | A inline | B 4탭 | **C modal** | D wizard |
|------|---------|-------|-------------|----------|
| 초보 이해도 | △ | ✓ | ✓ | ✗ |
| 보안 표면 | △ | △ | ✓✓ | ✓ |
| 설정 빈도 적합 | ✗ | △ | ✓✓ | ✗ |
| 탭 수 부담 | ✓ (3) | ✗ (4) | ✓ (3) | ✓ (3) |
| revoke/교체 흐름 | △ | ✓ | ✓✓ | ✗ |
| 권장 순위 | 4 | 2 | **1** | 5 |

---

## 4. 최종 권장 구조 = C. wizard + tray + 3탭 + Settings modal

### 4.1 윈도우 구조
```
┌─ Wizard (첫 실행, 1회) ─────────────────────────────────┐
│  Step 1 서버 URL → Step 2 등록코드 → Step 3 완료         │
│  (OpenAI key 입력은 wizard 에 포함하지 않는다)            │
└──────────────────────────────────────────────────────────┘

┌─ 메인 윈도우 (760×640, 3탭) ────────────────────────────┐
│  [ Chat ] [ Status ] [ Diagnostics ]    [⚙ AI 설정] [≡] │
│  ──────                                                  │
│  (탭별 내용)                                              │
└──────────────────────────────────────────────────────────┘

┌─ AI Settings Modal (사용자가 [AI 설정] 클릭 시) ─────────┐
│  OpenAI key 입력 / 모델 선택 / 연결 테스트 / 삭제         │
└──────────────────────────────────────────────────────────┘

┌─ Tray ────────────────────────────────────────────────┐
│  ● 상태 / 열기 / Chat 열기 / 상태 / 진단 / AI 설정 /   │
│  autostart / 재등록 / 종료                              │
└────────────────────────────────────────────────────────┘
```

### 4.2 창 크기 (보정)
- 메인 윈도우: **760 × 640** (직전 720×600 보다 약간 큼 — Chat 가독성 ↑)
- AI Settings modal: **520 × 420**
- Wizard 다이얼로그: 560 × 480 (유지)
- 진단 다이얼로그 (별도): 미사용 — Diagnostics 탭으로 대체

### 4.3 탭 배치
- 탭 위치: **상단** (좌측 사이드바보다 콘텐츠 폭 확보 우선 — Chat 중심)
- 좌측 정렬, 우측 끝에 [⚙ AI 설정] + [≡ (메뉴)] 버튼

---

## 5. 화면 설계 (요약)

| # | 화면 | 트리거 | 목적 |
|---|------|--------|------|
| 1 | Wizard Step 1 | 첫 실행 | 서버 URL |
| 2 | Wizard Step 2 | Step 1 [다음] | registration_code |
| 3 | Wizard Step 3 | Step 2 성공 | 등록 완료 + autostart |
| 4 | **Chat 탭** | 기본 진입 | AI 대화 |
| 5 | **AI Settings modal** | [AI 설정] 클릭 | OpenAI key 관리 |
| 6 | Status 탭 | 탭 클릭 | 연결 상태 |
| 7 | Diagnostics 탭 | 탭 클릭 | 진단 정보 |
| 8 | 재등록 확인 dialog | 트레이 / Diagnostics [재등록] | 확인 |
| 9 | 오류 popup | 인증 실패 / 서버 실패 / API key 실패 | 안내 + 행동 |

각 화면 필드 / 버튼 / 마스킹 규칙은 §6~§9 에서 정의.

---

## 6. Chat 탭 설계

### 6.1 와이어
```
┌─────────────────────────────────────────────────────┐
│ [Chat★] [Status] [Diagnostics]      [⚙ AI 설정] [≡] │
├─────────────────────────────────────────────────────┤
│  AI 상태: ● OK · gpt-4 · sk-****abcd                │
│  ─────                                              │
│                                                     │
│  ┌─ 메시지 ──────────────────────────────┐          │
│  │ AI    안녕하세요. 무엇을 도와드릴까요?  │          │
│  │ 나    오늘 일정 알려줘                  │          │
│  │ AI    네, 오늘 일정은 ...               │          │
│  │ [작업 위임] 파일 검색 [승인][거절]      │          │
│  └────────────────────────────────────────┘          │
│                                                     │
│  ┌─ 입력 ────────────────────────────────┐          │
│  │ 메시지를 입력하세요…                    │          │
│  └────────────────────────────────────────┘          │
│  [ 전송 ]  Enter 전송 · Shift+Enter 줄바꿈           │
│  ⚠ 비밀번호/주민번호 등 민감정보 입력 금지            │
└─────────────────────────────────────────────────────┘
하단: ● 정상 · agent la-xxx***yyy · v0.1.0
```

### 6.2 AI 상태 badge (Chat 상단)
- **● OK** (녹색) — key 저장됨 + 연결 테스트 PASS + 사용 가능
- **● 미설정** (회색) — key 없음 → "AI 설정에서 키 입력" 안내 + 입력창 비활성
- **● 테스트 필요** (주황) — key 있지만 한 번도 테스트 안 됨 → "[연결 테스트] 권장" 배너
- **● 오류** (빨강) — 마지막 호출 실패 (코드별 안내)

### 6.3 상태별 입력 활성/비활성
| AI 상태 | 입력창 | 전송 버튼 | 배너 |
|---------|--------|-----------|------|
| OK | 활성 | 활성 | "AI 와 대화 가능" |
| 미설정 | 비활성 (placeholder "AI 키를 먼저 설정") | 비활성 | "[AI 설정] 에서 OpenAI API key 입력" |
| 테스트 필요 | 활성 | 활성 | "⚠ 아직 키 연결 테스트 안 됨. 권장: [연결 테스트]" |
| 오류 | 비활성 | 비활성 | 오류 코드별 한글 + [AI 설정] |

### 6.4 메시지 표시
- 역할 라벨: `AI` (좌측) / `나` (우측) / `[작업 위임]` (가운데, 카드)
- font: Segoe UI 12 본문, Consolas 11 코드 블록
- 작업 위임 카드: 별도 박스 + 위험도 배지 (low/medium/high)

### 6.5 [AI 설정] 버튼
- 우상단 톱니바퀴 아이콘
- 클릭 → AI Settings modal (§7)

---

## 7. OpenAI API key 설정 modal (핵심)

### 7.1 와이어 (520×420)
```
┌─ AI 설정 ─────────────────────────────────────── ✕ ┐
│                                                    │
│  Provider          [ OpenAI ▾ ]                    │
│                                                    │
│  API key                                           │
│  ┌──────────────────────────────────────────────┐  │
│  │ ● ● ● ● ● ● ● ● ● ● ● ● ● ● ● ●              │  │
│  └──────────────────────────────────────────────┘  │
│  저장 상태: 저장됨 · sk-****abcd                    │
│  마지막 테스트: 2026-05-21 14:23                    │
│                                                    │
│  모델              [ gpt-5.5 ▾ ]                   │
│                                                    │
│  [ 저장 ]   [ 연결 테스트 ]   [ 교체 ]              │
│                                            [ 삭제 ] │
│                                                    │
│  ⓘ key 는 Windows Credential Manager 에 저장됩니다. │
│     서버로 전송되지 않으며, 화면에 다시 표시되지     │
│     않습니다. 분실 시 OpenAI 계정에서 재발급하세요.   │
└────────────────────────────────────────────────────┘
```

### 7.2 필드
- **Provider**: `OpenAI` 고정 (MVP). dropdown 형태로 두되 선택지는 OpenAI 만 (Later 에서 추가)
- **API key**: `show='●'` 입력. 저장 즉시 입력창 비움. 재표시 안 함.
- **저장 상태**: "저장됨 · sk-****abcd" 또는 "저장 안 됨"
- **마지막 테스트 시각** + **마지막 오류 코드** (있을 경우)
- **모델**: dropdown (`gpt-5.5` / `gpt-4o` / 사용자 입력 — provider 별 후보)

### 7.3 버튼
| 버튼 | 동작 |
|------|------|
| 저장 | 입력값 → Credential Manager 저장 → 입력창 비움 → fingerprint 갱신 |
| 연결 테스트 | 작은 healthcheck 호출 (예: list models / 1 token ping) → 성공 시 "테스트 PASS" |
| 교체 | 새 key 입력 모드 (저장 → 기존 key 덮어쓰기) |
| 삭제 | 확인 dialog → Credential Manager 에서 제거 → fingerprint "없음" |
| 닫기 | modal 닫기 |

### 7.4 보안 규칙
- 저장 직후 **입력창 즉시 비움**
- key 원문은 메모리 변수에서 즉시 폐기 (저장 함수 종료 직후)
- diagnostics / log / report 에 key 원문 0
- diagnostics 에는 **fingerprint** (sk-****abcd) 만 노출
- clipboard 복사 버튼 **없음**
- 입력창에 paste 한 직후 [저장] 누르면 자동 비움

### 7.5 fingerprint 규칙
- 입력값 길이 ≥ 8 이면: `key[:3] + "****" + key[-4:]`
- 길이 < 8 이면: `"****" + key[-4:]` 또는 `"********"`
- fingerprint 는 hash 가 아닌 단순 마스킹 (사용자가 자기 key 인지 인지하기 위함)

---

## 8. Status / Diagnostics 탭 설계 (요약)

### 8.1 Status 탭 (변경 없음)
- 연결 상태 + agent_id 마스킹 + server/ws URL + 마지막 heartbeat + 재연결 횟수
- 버튼: [재연결] [재등록]
- **추가**: AI 상태 1줄 ("AI: ● OK · gpt-5.5 · sk-****abcd · 마지막 테스트 ...")

### 8.2 Diagnostics 탭 (보강)
- 기존 `connection_diagnostics.render_user_block()` 텍스트
- **추가 1 행**: `OpenAI    sk-****abcd (마지막 테스트 ...)` — fingerprint 만
- [복사] → 마스킹된 본문 + fingerprint 만 (key 원문 0)
- [재등록] / [AI 키 교체] 버튼

---

## 9. OpenAI 호출 방식 (정책 확정)

### 9.1 MVP: 로컬 데스크앱 직접 OpenAI API 호출
- API key 는 사용자 PC 의 Credential Manager
- 호출 경로: `사용자 PC → OpenAI API` (서버 경유 안 함)
- HaehanAI 서버에는 **OpenAI key 전송 0**
- 서버는 사용자의 AI 사용 사실/비용 모름 (별도 통계 분리 시 별도 공정)

### 9.2 장점
- 사용자가 자기 비용 부담 (서비스 비용 부담 ↓)
- 서버에 key 보관 책임 0 (보안 감사 부담 ↓)
- 테스트/초기 배포에 적합

### 9.3 단점 (명시)
- 사용자 PC 에서 외부 API 호출 발생 → 회사 방화벽/프록시 통과 필요할 수 있음
- 중앙 통제 어려움 (모델/비용 제한을 사용자 책임)
- 사용자가 OpenAI 계정 / billing 이해 필요

### 9.4 Later: Company Proxy 모드
- 회사가 OpenAI key 1개 보유 → 사용자는 회사 proxy 로 호출 → 회사가 비용 부담 + 사용량 통계
- MVP 이후 별도 공정 `AGENT_OPENAI_PROXY_MODE_01`

---

## 10. 오류 UX (OpenAI 관련)

| 코드 | 사용자 문구 | 권장 행동 | 재시도 | [AI 설정] 버튼 |
|------|------------|-----------|--------|----------------|
| `API_KEY_NOT_SET` | "OpenAI API key 가 설정되지 않았습니다." | AI 설정에서 key 입력 | ✗ | ✅ |
| `API_KEY_INVALID` | "API key 가 거부되었습니다." | 키 확인 / 교체 | ✗ | ✅ |
| `API_QUOTA_EXCEEDED` | "OpenAI 할당량 초과. 결제 정보를 확인하세요." | 비용 한도 / billing | ✗ | △ |
| `RATE_LIMITED` | "요청 한도를 초과했습니다. 잠시 후 다시 시도하세요." | 1~5분 대기 | ✅ | ✗ |
| `NETWORK_ERROR` | "네트워크 오류가 발생했습니다." | 인터넷/프록시 확인 | ✅ | ✗ |
| `MODEL_NOT_AVAILABLE` | "선택된 모델 '{model}' 을 사용할 수 없습니다." | 모델 변경 | ✗ | ✅ |
| `REQUEST_TIMEOUT` | "요청 시간 초과." | 짧은 입력으로 재시도 | ✅ | ✗ |
| `PROVIDER_ERROR` | "AI 서비스 응답 오류 (provider)." | 잠시 후 재시도 | ✅ | ✗ |

각 오류는:
- Chat 상단 배너 + 입력 비활성 (특정 오류만)
- toast popup (RATE_LIMITED, NETWORK_ERROR, REQUEST_TIMEOUT) 또는
- 상태 badge 색 변경 (KEY_INVALID, MODEL_NOT_AVAILABLE → 빨강)

---

## 11. 보안 / PII UX (전수)

### 11.1 절대 금지
- OpenAI API key 원문 — 화면 표시 / 로그 / 보고서 / clipboard / git / diagnostics 0
- device_token / registration_code 원문 — 동일 정책 유지
- AI 응답 내 echo back token-like 문자열 — redact 필터 1차 통과 후 표시

### 11.2 저장 정책
- API key → **Windows Credential Manager** (`token_store.py` 같은 backend 패턴 재사용 — 별도 service name `haehan-openai`)
- 평문 fallback → **기본 OFF**. opt-in 시에만 활성 (현재 공정 OUT_OF_SCOPE)
- 대화 history → **메모리 only**. 디스크 저장은 Later 별도 동의 토글

### 11.3 마스킹 규칙
- API key: `sk-****abcd` (앞 3 + ****+ last 4)
- agent_id: `la-xxx***yyy`
- URL query: token/auth/code/session 자동 `[REDACTED]`

### 11.4 사용자 입력 경고
- 사용자 입력에 token-like 패턴 (sk-* / 40자+ 토큰 / 주민번호 / 전화 / 이메일) 감지 시 confirm dialog
- "다음 패턴이 감지되었습니다. 그래도 전송하시겠어요?"

### 11.5 diagnostics 정책
- [복사] 결과에 API key 원문 0
- diagnostics fingerprint 만 표시 (`sk-****abcd`)
- 마지막 오류 코드는 OK (코드명만, 원문 없음)

### 11.6 동시 leak 검사 (audit)
- device_token / registration_code / OpenAI key — 셋 다 원문 패턴 부재 확인
- 보고서 / 문서 / 테스트 결과 / log export 모두 동일

---

## 12. Provider mode 확장성

### 12.1 MVP (이번 공정 → 다음 구현)
- **OpenAI BYOK only**

### 12.2 Later (별도 공정)
- `AGENT_OPENAI_PROXY_MODE_01` — 회사 proxy
- `AGENT_PROVIDER_ANTHROPIC_01` — 다른 provider 추가
- `AGENT_PROVIDER_GEMINI_01`
- `AGENT_PROVIDER_LOCAL_OLLAMA_01`

### 12.3 하지 않을 항목 (영구 제외)
- **ChatGPT 웹 자동화** — 브라우저 세션 자동 조작 ❌
- **웹 응답 스크래핑** ❌
- **무단 헤드리스 ChatGPT.com 자동화** ❌
- 운영자 admin / task dashboard
- React desktop/ui 통합

---

## 13. 디자인 스타일 재검토

### 13.1 창 크기
- 메인 윈도우: **760 × 640** (이전 720×600 보다 약간 큼)
- AI Settings modal: **520 × 420**

### 13.2 탭 배치
- **상단 탭** (3개, Chat default)
- 우상단 [⚙ AI 설정] + [≡ 메뉴]

### 13.3 Chat message bubble
- AI 응답: 좌측 정렬, 카드 형태, accent 보더
- 사용자: 우측 정렬, accent 채움
- 작업 위임 카드: 가운데, 위험도 배지 (low/medium/high 색)

### 13.4 AI 상태 badge
- Chat 탭 상단 1줄: `● [상태]  ·  gpt-5.5  ·  sk-****abcd`
- 색: 녹색/주황/빨강/회색 (§6.2)

### 13.5 API key modal 레이아웃
- 단일 column, 16px 간격
- 입력창 폭 모달 90%
- 저장 버튼 primary, 삭제 버튼 우하단 danger

### 13.6 키보드 단축키
| 키 | 동작 |
|----|------|
| Ctrl+1 | Chat 탭 |
| Ctrl+2 | Status 탭 |
| Ctrl+3 | Diagnostics 탭 |
| **Ctrl+,** | **AI 설정 modal 열기** (신규) |
| Ctrl+R | 재등록 |
| F1 | 진단 보기 (Diagnostics 탭) |
| Esc | modal/dialog 닫기 |
| Enter (Chat 입력) | 전송 |
| Shift+Enter | 줄바꿈 |

---

## 14. 구현 우선순위

### 14.1 MVP — 즉시 구현 (3 공정 분리)

#### 공정 1: `AGENT_OPENAI_BYOK_KEY_STORE_01`
- `local_agent/openai_key_store.py` 신규 (token_store 패턴 재사용)
- Credential Manager service name `haehan-openai`
- save / load / delete / fingerprint API
- 평문 fallback 기본 OFF
- 단위 테스트 (저장/로드/삭제/마스킹/leak 차단)

#### 공정 2: `AGENT_OPENAI_CHAT_CLIENT_01`
- `local_agent/openai_chat_client.py` 신규
- `AiChatClient` Protocol 구현 (기존 ai_chat_client 의 mock 과 같은 인터페이스)
- 실제 OpenAI Chat Completions API 호출
- streaming 지원
- key load (호출 직전, 메모리 변수 즉시 폐기)
- 오류 매핑 (§10 의 8 코드)
- redaction (요청/응답 모두)

#### 공정 3: `AGENT_GUI_CHAT_IMPLEMENTATION_01`
- `gui_app.py` 보정 — 760×640 + 3탭 + AI Settings modal
- `gui_chat_panel.py` 신규 — Chat 탭
- `gui_ai_settings_modal.py` 신규 — Settings modal
- AI 상태 badge, 입력 활성/비활성, 작업 위임 카드 UI
- redaction wrapping
- 회귀: CLI 모드 / 기존 wizard / Status / Diagnostics

### 14.2 Later
- streaming 응답 (위 공정 2 안에서 가능하면 함께)
- 대화 저장 (사용자 명시 토글 + 위치 안내)
- 파일 첨부
- 회사 proxy 모드 (`AGENT_OPENAI_PROXY_MODE_01`)
- 다른 provider (Anthropic / Gemini / Ollama)
- 음성 입력 / 메시지 검색

### 14.3 하지 않을 항목 (영구 제외)
- ChatGPT 웹 자동화 / 브라우저 세션 조작
- React desktop/ui 통합
- 운영자 admin 패널
- task 관리 dashboard
- 상세 로그 export (개인 사용자 범위 외)

---

## 15. 다음 구현 공정명 (순서 확정)

1. **`AGENT_OPENAI_BYOK_KEY_STORE_01`** (먼저 — 저장소 계약)
2. **`AGENT_OPENAI_CHAT_CLIENT_01`** (다음 — 실제 API 호출)
3. **`AGENT_GUI_CHAT_IMPLEMENTATION_01`** (마지막 — UI 연결 + 빌드)

이후:
- `PYINSTALLER_BUILD_EXEC_V4_01` — GUI + OpenAI 포함 재빌드
- `USER_FIELD_TEST_02` (외부 PC + BYOK 검증)
- `CODE_SIGNING_01`

---

## 16. desktop/ui (React 운영자 앱) 미수정

본 설계 보정도 **`HaehanAI-Agent.exe` 라인 한정**.

- `desktop/ui/*` — 절대 수정 안 함
- `desktop/ui_dist/*` — 절대 수정 안 함
- React / Vite / Tailwind / shadcn — 건드리지 않음
- 통합 필요 시 별도 공정 `REACT_GUI_AGENT_INTEGRATION_01`

---

## 17. 결정 / 승인 요청

본 설계서 승인 시 다음 공정 큐:
1. `AGENT_OPENAI_BYOK_KEY_STORE_01`
2. `AGENT_OPENAI_CHAT_CLIENT_01`
3. `AGENT_GUI_CHAT_IMPLEMENTATION_01`

승인 의견:
- (a) **권장 C (3탭 + Settings modal)** 그대로 진행
- (b) 차선 B (4탭 — AI Settings 탭) 로 변경
- (c) 일부 수정 (모달 위치 / 단축키 / 모델 dropdown 옵션)
- (d) 보류
