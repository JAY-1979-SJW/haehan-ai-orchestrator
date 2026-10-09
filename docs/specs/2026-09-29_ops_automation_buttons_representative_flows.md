# admin-web 대표 자동화 버튼 + 첫 방문 사이트 자동화 강화 — 기준서 (2026-09-29)

> 상태: 기준서만 작성. 코드·설정 미수정, 커밋 없음. 사용자 승인 후 드라이런 → 착수.
> 범위: "버튼 클릭 → AI 에이전트 실행 → 결과" 전체 체인은 이미 구현·검증됨(2026-09-28,
> `docs/specs/2026-09-28_cdp_universal_automation_and_mcp_trigger.md` §5.1). 지금 빠진
> 건 화면의 실제 버튼뿐 — 이 기준서는 "무엇을 대표 사례로 삼아 그 버튼을 조립할지"를 정한다.
> 결정됨(2026-09-29, 사용자): **엑셀 분석은 이번 범위에서 제외(A안)**. 추가 범위 2건:
> 구글(Gmail) 버튼 활성화, 첫 방문 사이트 자동화를 HTML 개발자 힌트로 보강.
> 원칙: 신규 백엔드 로직 최소화, 기존 API/CLI/오픈소스 도구 재사용 우선(CLAUDE.md 기존 구현
> 확인 의무).

## 0. 요약

| 도메인 | 기존 자산 | 신규로 필요한 것 |
|---|---|---|
| 블로그 발행 | `POST /api/v1/naver/blog/write-to-naver`·`/compose` 등 7개 엔드포인트 | 버튼 + 프롬프트뿐 |
| 카페 리서치 | `POST /naver-cafe/collect`·`/ai-analyze` 등 10개 엔드포인트 | 버튼 + 프롬프트뿐 |
| 인스타그램 게시 | `scripts/instagram/api_publish.py`(`publish_reel`/`publish_carousel`, `confirmed=` 승인 인자 내장) | 버튼 + 프롬프트뿐 |
| 유튜브 분석 | `apps/youtube-analyzer-standalone`(yt-dlp·faster-whisper, CLI 4단계 기구현) | 버튼 + 프롬프트뿐(신규 코드 없음) |
| **구글(Gmail) 조사·초안** | `scripts/google/gmail.py`(`run(task, args)` — list/search/analyze/compose_draft, CDP 기반) | 버튼 + 프롬프트뿐(신규 코드 없음) |
| ~~엑셀 분석~~ | ~~범위 제외 확정(A안)~~ | — |

**핵심 설계 판단**: `run_claude_agent` 액션이 실행하는 건 진짜 `claude -p` 헤드리스
세션이라, Claude가 Bash 도구로 기존 API를 직접 호출하거나(`curl`/Python) 기존 CLI를
직접 실행할 수 있다. 즉 도메인마다 새 MCP 도구나 새 액션 타입을 만들 필요 없이
**프롬프트 문구만 다르게** 5개 버튼을 만들 수 있다.

## 1. 요구사항 (사용자 발화)

| ID | 요구사항 |
|---|---|
| REQ-1 | "실제 앱에서 버튼 클릭하고 실행하는걸 ai가 확인하고 검증하는건 언제쯤 될까?" — 버튼→실행→검증 흐름을 실제로 조립 |
| REQ-2 | "범용적인 방식으로 해야 하나?" → 엔진(CDP·트리거 인프라)은 범용, 화면·워크플로는 도메인별 — 이 판단을 대표 사례로 실증 |
| REQ-3 | "기준서를 작성하고 대표적인 내용으로 하자 블로그, 까페, 인스타 등 소셜미디어 자동화, 유투브 분석(오픈소스 도구 보유), 엑셀 분석?" |
| REQ-4 | "a안으로 하고" — 엑셀 분석 제외 확정 |
| REQ-5 | "구글 탭 버튼들을 활성화 하고" — Google 도메인도 대표 버튼에 포함 |
| REQ-6 | "처음 보는 사이트도 자동화 되게 html에서 정보를 수집해서 반영하자 신규 사이트 탐색시 html 개발자 정보가 있으면 쉽게 하잖아" — `universal_actions.py`의 스냅샷을 AXTree 전용에서 HTML 개발자 힌트(`data-testid`·`id`·`name` 등)까지 보게 확장 |

## 2. 기존 자산 확인 (`capability_check.py` 실측, 2026-09-29)

### 2.1 블로그
```
POST /api/v1/naver/blog/write-to-naver   ← 실제 발행
POST /api/v1/naver/blog/compose          ← 초안 작성
POST /api/v1/naver/blog/ai-generate
GET  /api/v1/naver/blog/drafts
POST /api/v1/naver/blog/seo
```
버튼 프롬프트 예: "MCP call_api로 POST /api/v1/naver/blog/compose 호출해 <주제>로 초안을
만들고, 결과를 사람이 승인하면 write-to-naver로 발행해."

### 2.2 카페
```
POST /naver-cafe/collect            ← 게시글 수집
POST /naver-cafe/ai-analyze         ← AI 분석
GET  /naver-cafe/report             ← 분류 보고서
```
쓰기(가입/게시)는 이미 승인 게이트 처리됨(`정책: join-request는 준비만, join-submit·publish는
승인 필요` — capability_check 출력에 명시). 버튼은 읽기 전용 리서치(collect→analyze→report)만
1차로 노출.

### 2.3 인스타그램
`scripts/instagram/api_publish.py`: `publish_reel(video_url, caption, confirmed=False)`,
`publish_carousel(image_urls, caption, confirmed=False)` — **승인 파라미터가 이미 함수
시그니처에 내장**되어 있어 별도 승인 배선 없이도 안전. 버튼은 `confirmed=False`(미리보기)만
1차로 노출하고, 실제 게시는 사람이 한 번 더 확인 후 `confirmed=True` 재요청.

### 2.4 유튜브 분석
`apps/youtube-analyzer-standalone/cli.py` — 오픈소스 `yt-dlp`(다운로드) +
`faster-whisper`(전사) 기반, 이미 4단계 구현됨:
```
python cli.py transcribe <video_id>   # 전사
python cli.py frames <video_id>       # 키프레임 추출
# Claude가 프레임을 Read로 직접 보고 descriptions.json 작성 (기존 관례)
python cli.py report <video_id> --descriptions data/frames/<video_id>/descriptions.json
```
버튼 프롬프트 예: "Bash로 apps/youtube-analyzer-standalone/cli.py analyze <URL> 실행 →
frames의 각 이미지를 Read로 보고 descriptions.json 작성 → report 생성 → 결과 경로 보고."
신규 코드 없이 기존 오픈소스 파이프라인을 그대로 호출.

### 2.5 구글 (Gmail 조사·초안)
`scripts/google/gmail.py`가 이미 CDP 기반 `run(task, args)` 디스패처로 구현되어 있음:
```
run("list", args)            # 받은편지함 목록
run("search", args)          # 검색
run("analyze", args)         # 분석
run("compose_draft", args)   # 초안 작성(발송 아님)
```
블로그/카페와 같은 패턴 — 읽기(list/search/analyze)는 버튼으로 바로 노출, `compose_draft`도
"임시보관함 저장"까지만이라 안전(실제 발송 기능은 이 모듈에 없음 — 발송이 필요해지면 별도
승인·구현 필요, 이번 범위 아님). 버튼 프롬프트 예: "Bash로 scripts/google/gmail.py 를
`list`/`search`로 실행해 받은편지함을 조사하고, 필요하면 `compose_draft`로 답장 초안만
만들어(발송 금지)."

**"구글 탭"이 admin-web에 아직 없는 이유**: `ai_orchestrator/connectors/google/router.py`의
`google_router`는 `APIRouter(tags=["google"])`만 있고 실제 라우트(`@router.get/post`)가
0개 등록된 빈 라우터다(2026-09-29 실측). 예전 `admin-web/src/app/(legacy)/google/*`
UI는 2026-09-23 정리 때 삭제됨(`docs/deleted_code_index.md`). 즉 "비활성화된 버튼을
켜는" 게 아니라 **버튼 자체를 처음부터 새로 붙이는 작업**이다 — 다만 REST 엔드포인트를
새로 만들 필요는 없다(§3.1처럼 `run_claude_agent`가 Bash로 `scripts/google/gmail.py`를
직접 실행하면 되므로, 빈 `google_router`를 채우는 건 이번 범위가 아님).

### 2.6 엑셀 분석 — 범위 제외 확정 (A안, 사용자 결정 2026-09-29)
이 저장소의 Excel 관련 자산은 (a) 오늘 만든 A4 서식 검사(`scripts/common/excel_a4_*.py`,
읽기전용 점검), (b) 수집 데이터를 xlsx로 "쓰는" 리포트 생성(`scripts/naver/excel_reports.py`
등, 이미 blog/카페 리포트에 녹아있음)뿐이다. 사용자가 임의로 업로드한 엑셀을 분석하는
범용 기능은 이 저장소에 없다 — 별도 프로젝트("06. excel-analysis-engine", "09. 견적 프로그램")
영역과 겹친다. 이번 라운드 대표 버튼에서 완전히 제외.

## 3. 설계

### 3.1 흐름 (5개 버튼 공통)
```
[admin-web ops 페이지 새 패널] "실행" 버튼 클릭
        │ 기존 엔드포인트: POST /api/v1/local-agents/{agent_id}/tasks
        │ {"action": "run_claude_agent", "params": {
        │    "prompt": "<도메인별 프롬프트 템플릿 + 사용자 입력값>",
        │    "allowed_tools": ["mcp__haehan-orchestrator__call_api", ...],  # 필요한 것만
        │    "max_budget_usd": <도메인별 상한>
        │ }}
        ▼
[core/agent_runtime/agent.py] (기존, 신규 코드 없음) → claude -p 헤드리스 실행
        │
        ▼
[Claude가 Bash/MCP로 §2의 기존 API·CLI를 직접 호출]
        │
        ▼
[쓰기 작업이면] 기존 승인 플로우(gates/approval.py, 또는 §2.3처럼 함수 자체의 confirmed= 게이트)
        ▼
[결과를 task 상태 API로 보고 → admin-web이 폴링해 화면에 표시]
```

### 3.2 admin-web 배치
`admin-web/src/app/ops/page.tsx`(기존 대시보드)에 신규 컴포넌트
`AutomationButtonsPanel.tsx` 1개 추가 — 기존 `AgentStatusPanel`/`WebTaskPanel` 옆.
버튼 5개(블로그/카페/인스타/유튜브/구글), 각 클릭 시 위 POST 호출 + task_id로 상태 폴링(기존
`fetchWebTasks` 패턴 재사용).

### 3.3 프롬프트 템플릿 위치
신규 파일 `ai_orchestrator/automation_button_prompts.py`(또는 admin-web에서 프론트가
직접 조립) — 도메인별 프롬프트 문자열 + 필요한 `allowed_tools` 목록을 딕셔너리로 관리.
새 액션 타입이나 새 MCP 도구는 만들지 않는다.

## 4. 검증 계획

각 버튼에 대해:
1. `electron_target.py`로 AI가 실제 Electron 창의 그 버튼을 클릭
2. task 상태를 폴링해 `completed` 확인
3. 실제 부작용 확인(블로그: 초안 생성 여부만 우선, 실발행은 2차; 카페: 수집 결과 존재;
   인스타: `confirmed=False` 응답에 미리보기 있는지; 유튜브: 리포트 md 파일 생성; 구글:
   `compose_draft` 결과가 실제 발송이 아니라 임시보관함에만 저장됐는지)
4. 쓰기형 액션은 dry-run/preview 모드로만 1차 검증 — 실제 발행·게시는 별도 승인 후

## 5. 권한/보안

- 각 프롬프트의 `allowed_tools`는 그 버튼에 필요한 MCP 도구만 최소 허용(2026-09-28 이미
  확립한 원칙, `--dangerously-skip-permissions` 사용 안 함).
- 쓰기 작업(발행/게시)은 §2.3처럼 함수 자체 `confirmed=` 게이트나 기존
  `gates/approval.py`를 그대로 거친다 — 버튼이 이 게이트를 우회하지 않는다.
- `max_budget_usd`로 버튼 1회 클릭당 비용 상한(도메인별로 다르게, 유튜브 분석이 프레임
  Read 여러 장이라 가장 높을 것으로 예상).

## 6. 위험

| 위험 | 완화 |
|---|---|
| 프롬프트만으로 Claude가 항상 올바른 API/CLI를 정확히 호출한다는 보장 없음 | 프롬프트에 정확한 엔드포인트·CLI 커맨드를 명시(자유 추론 최소화), 결과 검증 단계에서 실패 시 재시도 유도 |
| 유튜브 분석은 프레임 Read가 여러 번이라 비용·시간이 다른 버튼보다 큼 | `max_budget_usd` 상향 + 타임아웃 상향, 첫 실행에서 실측해 조정 |
| Gmail `compose_draft`가 혹시라도 발송 경로로 오인될 위험 | 프롬프트에 "발송 금지, 임시보관함까지만" 명시 + §4 검증에서 실제 발송 여부 확인 |

## 7. 첫 방문 사이트 자동화 강화 — HTML 개발자 힌트 반영 (REQ-6)

### 7.1 문제
`universal_actions.py::snapshot()`은 지금 **CDP `Accessibility.getFullAXTree` 하나만**
본다(role/name/value). 접근성 트리는 사이트가 ARIA를 얼마나 잘 지켰는지에 좌우되는데,
실제 사이트 HTML에는 접근성 트리보다 더 안정적인 "개발자용 힌트"가 흔히 있다:

- `data-testid`/`data-test`/`data-cy`/`data-qa` — 현대 SPA(React/Vue)가 테스트 자동화
  목적으로 직접 박아두는 속성. 있으면 사실상 가장 신뢰도 높은 선택자.
- `<input>`/`<form>`의 `name`·`autocomplete`·`type` — 로그인·검색·결제 폼 자동화의 핵심 단서.
- `id` — 흔하지만 여전히 유용한 보조 신호.
- `<meta>`(og:title 등)·`<script type="application/ld+json">`(schema.org 구조화 데이터) —
  페이지 자체가 "이게 무슨 페이지인지" 기계가 읽게 미리 선언해둔 정보.

지금 구조는 이 정보를 전혀 안 본다 — 매번 role/name만으로 요소를 찾다 보니, ARIA를
안 지킨 사이트(의외로 많음)에서 스냅샷 품질이 떨어진다.

### 7.2 설계
`snapshot()`이 AXTree를 순회하며 각 노드의 `backendDOMNodeId`를 얻는 지금 흐름에,
**한 번의 배치 `Runtime.evaluate`**로 문서 전체의 `data-testid`/`id`/`name`/`aria-label`
속성을 미리 수집해 AXTree 노드와 매칭하는 단계를 추가한다(요소마다 개별 CDP 왕복을
안 하려고 배치 한 번으로 처리 — 지금 `act()`의 `Runtime.callFunctionOn` 개별 호출과는
다른 패턴).

```
SnapshotNode 에 필드 추가: dev_hint: str | None
  예: [e7] textbox "검색" dev_hint=data-testid=search-input
```

`act()`의 ref 해석은 그대로 `backendDOMNodeId` 기반 유지(안정성 우선순위는 여전히
"이미 잡은 ref" > "새 스냅샷"). `dev_hint`는 **Claude가 스냅샷 텍스트를 읽고 어떤 ref를
고를지 판단하는 데 참고 정보로만 쓰인다** — 새로운 액션 타입(`act(ref, action)`의 API는
안 바뀜)이나 셀렉터 언어를 새로 만들지 않는다.

선택적 2단계(이번 범위 밖, 후보만 기록): `<script type="application/ld+json">`과
`<meta property="og:*">`를 스냅샷 헤더에 요약으로 붙여, "이 페이지가 무슨 사이트/무슨
콘텐츠인지"를 Claude가 첫 스캔에 바로 알 수 있게 한다(오픈클로에는 없는 차별점이 될 수 있음).

### 7.3 검증 계획
2026-09-28에 썼던 것과 같은 방식(위키백과 등 한 번도 설정한 적 없는 사이트)으로,
- `data-testid`가 있는 사이트(예: 많은 React 기반 서비스)에서 `dev_hint`가 실제로 채워지는지
- ARIA가 부실한 사이트에서 `dev_hint` 덕분에 `act()` 성공률이 체감상 올라가는지
두 가지를 실측 비교.

### 7.4 위험
| 위험 | 완화 |
|---|---|
| 배치 `Runtime.evaluate`가 대형 DOM에서 느릴 수 있음 | `max_nodes` 상한 이미 있는 구조 재사용, 초과 시 dev_hint 생략하고 AXTree만으로 폴백 |
| `dev_hint` 텍스트가 스냅샷을 과도하게 길게 만듦 | 있는 노드에만 짧게(`data-testid=x` 한 줄) 붙이고 없으면 생략 |

## 8. 다음 세션 범위

이 기준서 승인 후: (1) 드라이런(각 프롬프트 초안 + 예상 API 응답 형태), (2) admin-web
컴포넌트 1개 + 프롬프트 템플릿 파일 1개 구현, (3) §4 검증 5종 실행, (4) §7 HTML 개발자
힌트 스냅샷 확장 구현 + 실측 비교.
