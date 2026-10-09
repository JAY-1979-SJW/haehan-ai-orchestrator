# 개인 메일함 AI 비서 (Gmail + 네이버메일) — 방향 확정 기준서 (2026-09-29)

> 상태: 방향 확정 단계. **코드 미작성, 커밋 없음.** 사용자 승인 후 착수.
> 이 문서는 오늘 작성된 `2026-09-29_construction_ai_agent_direction.md`("건설 파이프라인
> 알림 채널로서의 메일함")와는 **별개 목적**이다. 사용자 확인: "개인 메일함부터 구글 및
> 네이버를 하자" — 일반 업무메일(개인 계정) 비서 기능이 먼저다. 두 문서는 나중에 같은
> `run_claude_agent` 버튼 메커니즘을 공유할 수 있지만, 요구사항과 우선순위는 분리한다.

## 0. 요약

| 항목 | 내용 |
|---|---|
| 목표 | 명령 1번 → AI가 새 메일 요약+회신 초안 작성 → 사람 승인 → 발송. 신규 작성 시 수신자/본문은 AI가 맥락으로 판단, 첨부파일도 필요하면 찾아서 자동 첨부 |
| 업계 근거 | 2026년 AI 메일 비서(Copilot, Fyxer, Shortwave 등) 전부 "승인 전까지 발송 안 함"이 표준 — 완전자동 발송은 드묾(WebSearch 확인) |
| 가장 큰 기존 걸림돌 | 네이버메일 발송 라우트가 **없는 함수를 import해 100% 크래시**(defect_index #37, 오늘 501로 정직화만 해둠, 미구현) + `scripts.naver.mail` 패키지 자체가 "발송/답장/삭제/이동 금지"를 모듈 docstring에 못박은 **의도적 읽기전용 설계** — 이번 요구사항은 이 경계를 넘어야 함 |
| 첨부파일 자동 검색 | 코드베이스 전체에 **전혀 없음**(Gmail/네이버 둘 다) — 새로 설계해야 함 |

## 1. 요구사항 (사용자 발화 원문 기준)

| ID | 요구사항 | 출처 |
|---|---|---|
| REQ-1 | 메일을 AI 에이전트와 연결 — 메일 요약 보고 | "메일을 ai 에이전트와 연결하면 메일 요약 보고 및 회신을..." |
| REQ-2 | AI가 회신 초안 작성 → 승인 → 발송 | 위와 동일 |
| REQ-3 | 새 메일 작성 시 수신자·내용을 AI가 판단 | "새 메일을 작성하는데 누군가에게 어떤 내용으로 보낼지" |
| REQ-4 | 첨부파일이 필요하면 찾아서 자동 첨부 | "만약 첨부 파일이 있다면 그것도 찾아서 자동 첨부 하는지?" |
| REQ-5 | 발송은 버튼 한 번에 완전자동이 아니라 승인 게이트 유지 | 사용자 확인 + 업계 표준 + CLAUDE.md 메일정책 3자 일치 |
| REQ-6 | 대상: Gmail + 네이버메일 둘 다, 개인 메일함 우선 | "개인 메일함부터 구글 및 네이버를 하자" |

## 2. 현재 상태 (오늘 코드로 실측 확인)

### 2.1 Gmail

| 기능 | 상태 | 근거 |
|---|---|---|
| 받은편지함 조회 | ✅ 동작(오늘 admin-web 버튼까지 연결·실측 완료) | `GET /api/v1/gmail/inbox`, `gmail_cdp_reader.py` |
| 작성 준비(compose, dry_run) | ✅ 동작 | `gmail_router.py POST /compose` |
| 발송 | ✅ 동작(실제 발송 버튼 클릭까지 구현됨) | `gmail_router.py POST /send`(confirmed=True 필수) |
| AI가 본문을 생성 | ❌ 없음 — 호출자가 완성된 `body`를 넘겨야 함 | `GmailComposeRequest.body` 그대로 전달 |
| 메일 요약/분류 보고 | ❌ 없음 — 원문 리스트만 | `gmail_router.py`에 report 기능 없음 |
| 첨부파일 첨부 | ❌ 없음 | `GmailAPI.send/reply`에 첨부 파라미터 자체가 없음(코드 확인) |
| 수신 메일의 첨부 감지 | ⚠️ 있으나 정규식 추측뿐 | `gmail_analysis.py`의 `attachment_hint`(본문에 "첨부"라는 단어 있는지만 봄, 실제 파일 다운로드 안 함) |

### 2.2 네이버메일

| 기능 | 상태 | 근거 |
|---|---|---|
| 받은편지함 조회/수집 | ✅ 동작(성숙) | `scripts/naver/mail/collection/*` |
| AI 요약·카테고리·액션아이템 보고 | ✅ 동작(꽤 잘 만들어짐) | `analysis/business_report.py`, `analysis/action_item_dashboard.py` |
| 새 메일 도착 알림 | ✅ 있음(OS 알림, 발신자/제목만, 요약 아님) | `watch_new_mail.py` — **스케줄 미등록, 수동 실행만** |
| 작성 준비(compose) | ❌ **크래시 확인됨** → 오늘 501로 정직화만 함 | defect_index #37 |
| 발송 | ❌ 구현 자체가 없음 | 위와 동일 |
| `scripts.naver.mail` 패키지 정책 | ⚠️ **모듈 docstring에 "발송/답장/삭제/이동 금지" 명시** — 의도적 읽기전용 | `scripts/naver/mail/__init__.py` |
| 첨부파일 자동 첨부 | ❌ 없음 | 코드 전체 검색 결과 없음 |

### 2.3 핵심 결정 필요 사항

네이버메일 발송을 만들려면 **읽기전용으로 설계된 `scripts.naver.mail` 패키지에 손대지 않고**, Gmail 쪽(`scripts/google/gmail_api.py`, CDP로 작성창 직접 조작)과 같은 패턴으로 **별도의 새 발송 모듈**을 만들어야 한다(defect_index #37의 fix_note가 이미 이렇게 결론 냄). `scripts.naver.mail` 자체의 "금지" 정책은 유지한다 — 우회가 아니라 옆에 새 모듈을 만드는 것.

## 3. 설계

### 3.1 전체 흐름

```
[admin-web ops 패널] "메일 확인+초안" 버튼 클릭
        │ POST /api/v1/local-agents/{agent_id}/tasks
        │ {"action": "run_claude_agent", "params": {
        │    "prompt": "<계정: gmail|naver> 받은편지함을 확인해 안 읽은 메일을 요약하고,
        │               회신이 필요한 메일은 초안을 작성해줘. 첨부가 필요하면
        │               scripts/ops/mail_attachment_finder.py 로 후보를 찾아 제안해.
        │               절대 발송하지 마 — 초안까지만.",
        │    "allowed_tools": ["Bash(py -3.14 scripts/google/gmail.py *)",
        │                       "Bash(py -3.14 scripts/naver/mail/... *)",
        │                       "Bash(py -3.14 scripts/ops/mail_attachment_finder.py *)"] }}
        ▼
[core/agent_runtime/agent.py](기존, 신규 코드 불필요) → claude -p 헤드리스 실행
        ▼
[Claude가 기존 조회 API + 신규 draft 함수로 초안 생성]
        ▼
[결과(요약 + 초안 + 첨부후보)를 task 상태로 admin-web에 표시]
        ▼
[사람이 admin-web에서 초안 검토·수정 → "발송" 버튼 별도 클릭]
        │ POST /api/v1/gmail/send {confirmed:true}  또는
        │ POST /api/v1/naver-mail/send {confirmed:true} (신규 구현)
        ▼
[실제 발송 — 이 마지막 클릭 전까지는 어떤 경로로도 발송 불가]
```

REQ-5(승인 게이트)는 이 흐름 자체로 구조적으로 보장된다 — `run_claude_agent`에게 "발송 금지" 프롬프트 지시만 주는 게 아니라, **애초에 발송 API를 `allowed_tools`에서 빼서** 헤드리스 세션이 물리적으로 발송을 못 하게 한다(프롬프트 준수에 기대지 않음).

### 3.2 신규 컴포넌트

| 컴포넌트 | 위치(제안) | 역할 |
|---|---|---|
| `MailAssistantPanel.tsx` | `admin-web/src/app/ops/components/` | "메일 확인+초안 작성" 버튼(계정 선택: Gmail/네이버), 결과(요약+초안+첨부후보) 표시, 발송 승인 버튼 |
| `scripts/ops/mail_attachment_finder.py`(신규) | 메일 본문에서 언급된 파일명/키워드 추출 → `data/`, 최근 다운로드/업로드 폴더, 프로젝트 산출물 폴더에서 후보 검색 → 매칭 후보 목록 반환(자동 첨부 X, **후보 제안까지만** — REQ-4의 "자동 첨부"는 후보가 1개로 명확할 때만, 모호하면 사람이 선택) |
| `scripts/naver/mail_compose/`(신규, 가칭) | `scripts.naver.mail`과 완전히 분리된 새 패키지. Gmail의 `gmail_api.py`와 동일 패턴(CDP로 작성창 직접 조작, "최종 발송 버튼은 안 누름" 원칙 동일 적용) |
| `ai_orchestrator/connectors/naver_mail_router.py` 수정 | `/compose`, `/send`를 501 대신 실제 구현으로 교체(신규 `naver_mail_compose` 모듈 사용) |
| Gmail 첨부 지원 | `GmailAPI.send/reply`에 `attachments: list[Path]` 파라미터 추가 — Gmail 웹 UI의 첨부 버튼(`input[type=file]`)에 파일 업로드 |

### 3.3 첨부파일 "찾아서 자동 첨부"의 현실적 범위

완전 자동(AI가 알아서 100% 정확히 찾아 첨부)은 오탐 위험이 있다(엉뚱한 파일을 실수로 첨부하면 정보 유출). 제안하는 단계:
1. 메일 본문/맥락에서 파일명 후보 추출(예: "견적서.xlsx", "지난주 사진")
2. `mail_attachment_finder.py`가 후보 파일을 찾아 **경로+최종수정일**과 함께 제시
3. 후보가 정확히 1개면 초안에 "첨부 예정: xxx.xlsx (확인 필요)"로 표시, 여러 개면 사람이 고르게
4. 실제 첨부는 발송 승인 단계에서 사람이 최종 확인한 파일로만

## 4. 위험 / 미해결

- **네이버메일 발송 경로 신규 구현**은 처음 만드는 자동화라 Gmail만큼 검증 안 됨 — 가비아/DNS 케이스처럼 "AI가 직접 CDP로 처리" 원칙은 유지하되, 최초 몇 번은 dry_run으로 충분히 검증 후 실제 발송 활성화 권고.
- **AI가 회신 본문을 창작**하는 부분은 100% `run_claude_agent`(Claude Code 헤드리스)의 판단에 맡겨진다 — 별도 "요약 품질" 게이트는 없음(사람 승인 단계가 그 역할을 대신함).
- 첨부파일 자동 매칭은 오탐 가능성이 본질적으로 있음 — §3.3처럼 "제안"까지만 자동화하고 최종 첨부는 사람 확인 필수로 설계(REQ-4의 "자동 첨부"를 "자동 탐색+제안"으로 해석 — 완전 무인 첨부는 권장하지 않음, 사용자 확인 필요).

## 5. 다음 단계 제안 (승인 필요)

1. `mail_attachment_finder.py`(신규, 읽기전용 파일 검색) — 가장 독립적, 위험 낮음
2. Gmail `GmailAPI.send/reply`에 첨부 지원 추가 — 기존 동작 확장, 위험 낮음
3. `MailAssistantPanel.tsx` + `run_claude_agent` 프롬프트 템플릿 — Gmail만 우선 연결(이미 안정적)
4. 네이버메일 신규 발송 모듈 — 가장 큰 신규 작업, 별도 드라이런 필요

이 순서로 진행할지, 우선순위를 다르게 할지 확인 후 착수합니다.
