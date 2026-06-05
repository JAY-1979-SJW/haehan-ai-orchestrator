# 기준서 — AI 상담 자율 도구호출 에이전트 전환 + 블로그 미디어 업로드 (2026-06-05)

## 배경 / 문제
현재 AI 상담의 GPT는 **통제된 파이프라인**으로 동작:
- `_route_app_task` 분류기가 메시지를 5개 op로 가둠
- `_KNOWN_SITES` 고정 URL표로 GPT가 주소를 못 정함
- 브라우저 에이전트는 6개 액션·12스텝의 경직된 단일-JSON 루프

→ 사용자가 Claude에게 명령하듯 **GPT가 자유롭게 판단·실행**하지 못함. 사용자 지시:
"GPT가 여기서 명령하듯 동일하게, 제약 해제, 현재창(수동 작업) 이어받기."

## 변경 (무엇을·왜·어떻게)

### Part 1 — 자율 도구호출 에이전트 (L8/L4)
- **`openai_proxy_caller.call_openai_agent(messages, tools, …)` 신규** — OpenAI function calling 지원
  (기존 `call_openai_chat` 보존). `tools`/`tool_calls` 포함 요청·응답 파싱.
- **`scripts/browser_agent/free_agent.py` 신규** — 도구호출 루프(관찰→GPT 도구선택→실행→피드백→완료).
  기존 `agent.py`의 `_observe`/`_execute`/`_is_destructive`/`_wait_for_login` **재사용**.
- **도구**: `read_page`(현재 페이지), `navigate(url)`, `click(index)`, `type_text(index,text)`,
  `scroll(dir)`, `session_status`, `analyze_cafe`, `finish(answer)`.
- **제거**: `agent_ai_proxy_router._route_app_task` 분류기 호출·`_KNOWN_SITES`·`_BROWSER_INTENT`
  강제 게이트 → free_agent가 대체. (URL·방법은 GPT가 결정)
- **유지**: 결제·송금·삭제·발송 차단 안전선(`_is_destructive`), 비동기 로그인(job) 흐름.

### Part 2 — 현재창(수동 작업) 이어받기 (Part 1에 포함)
- 에이전트는 시작 시 **고정 URL로 이동하지 않고** `read_page`로 **현재 열린 페이지**를 먼저 관찰.
- 사용자가 수동으로 로그인·이동해 둔 상태를 그대로 이어 작업. `navigate`는 GPT가 필요 시에만.

### Part 3 — 블로그 사진·이미지·동영상 업로드 (L9/L8/L5)
- **`BlogClient.tsx`**: 파일 입력(image/* , video/*) + 미리보기 + 목록.
- **업로드 엔드포인트**(`naver_blog_router`): multipart 수신 → `data/blog_uploads/`(gitignore) 임시 저장.
- **삽입**: CDP로 네이버 블로그 에디터에 미디어 업로드(`scripts/naver/blog/assets.py` 활용/확장).

## 영향 / 안전
- 레이어: L8(router)·L4(browser)·L9(blog UI). 역방향/순환 import 없음.
- API 응답 key·DB schema·핵심 산식 변경 없음. 보안: secret 미출력, 위험동작 차단 유지.
- 파일 업로드는 로컬 임시 저장(외부 전송 아님). 블로그 발행은 기존대로 사용자 확인 필요.

## 단계 실행
1. Part 1 (caller + free_agent + router 배선) → 검증 → 커밋
2. Part 3 (블로그 업로드 UI + 엔드포인트 + CDP 삽입) → 검증 → 커밋
3. 게이트(layer/security/quality) 전 단계 통과 후에만 커밋.

## 롤백
- free_agent 전환은 라우터에서 한 줄(분기)로 토글 가능하게 유지.
- 기존 `_route_app_task`/`_op_*`는 **삭제하지 않고 보존**(코드 보존 원칙) — free_agent가 내부에서 도구로 호출.
