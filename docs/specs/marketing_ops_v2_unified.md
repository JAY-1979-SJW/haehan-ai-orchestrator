# 마케팅 운영실 v2 — 3채널 통합 관리 + 유튜브 발행

작성 2026-08-20 · 상태: **기준서(승인 대기)** · 근거 요청: "이곳에서 통합관리하고 유튜브까지 올리자"

---

## 1. 왜 하는가

블로그·인스타·유튜브를 채널별로 따로 작업해 왔다. 그런데 통합 설계
(`marketing_ops_router.py` = 마케팅 운영실 v1)는 **이미 만들어져 있었다.**
쓰지 않고 수작업한 것이 문제였다.

v1에 실제로 빠진 것은 두 가지다.

| # | 문제 | 현재 상태 |
|---|---|---|
| A | 패키지 생성이 **터진다** | `multichannel.py` → `AIResponder._call()` → `assert_openai_allowed()` → 예외. GPT 차단(2026-08-19) 이후 통합 관리의 심장부가 죽어 있다 |
| B | 유튜브·인스타는 **발행 못 한다** | `approve_channel()`이 "직접 게시해주세요(자동 게시 미구현)" 문자열만 남긴다 |

v2는 이 둘만 해결한다. 새 시스템을 만들지 않는다.

---

## 2. 범위

### 하는 것
1. 파생 콘텐츠 생성을 **GPT → Claude Code 작업지시서 방식**으로 교체 (문제 A)
2. 패키지 대본 → **영상 생성**(TTS + 슬라이드쇼) → **유튜브 업로드** (문제 B)
3. 인스타 발행을 운영실에 연결 (`scripts/instagram/api_publish.py` 이미 검증됨)
4. 운영실 화면에서 3채널 상태를 한 눈에

### 안 하는 것
- 새 라우터/새 UI/새 저장소 — v1 구조를 그대로 쓴다
- 자동 발행 (사람 승인 없는 게시). **외부 공개 발행은 매번 재확인**(CLAUDE.md)
- 유튜브 public 업로드 기본값화 — **기본 private 유지**

---

## 3. 이미 있는 부품 (재사용, 신규 작성 금지)

| 레이어 | 모듈 | 역할 | 상태 |
|---|---|---|---|
| L8 | `ai_orchestrator/connectors/marketing_ops_router.py` | 운영실 API | 있음, 보강 |
| L9 | `admin-web/.../marketing/MarketingOpsClient.tsx` | 운영실 화면 | 있음, 보강 |
| L6 | `scripts/naver/blog/marketing/multichannel.py` | 1주제 → 4채널 파생 | **있음, 고장(A)** |
| L6 | `scripts/naver/blog/cli/blog_publish_manual.py` | 블로그 발행 | 검증됨 |
| L3 | `scripts/instagram/api_publish.py` | 인스타 Graph API 발행 | 검증됨(3건 게시) |
| L3 | `scripts/youtube/uploader.py` | `prepare_upload_plan` / `execute_upload_plan` | 있음, 공식 API 경로 포함 |
| L3 | `scripts/video/tts_narration.py` | Edge TTS `ko-KR-InJoonNeural` | 있음 |
| L3 | `scripts/instagram/reel.py::build_slideshow` | ffmpeg 슬라이드쇼 | 검증됨(9:16) |
| L2 | `ai_orchestrator/openai_guard.py` | GPT 차단 | 있음 |

**부품은 전부 있다. 배선만 없다.**

---

## 4. 변경 설계

### 4-1. 파생 생성: GPT → Claude Code (문제 A)

`multichannel.py`의 `generate_*` 함수들이 GPT를 직접 부르는 대신,
**작업지시서를 파일로 떨구고 비어 있는 패키지를 반환**한다.
블로그 원고를 이미 이 방식으로 쓰고 있다(`blog_publish_manual.py`) — 같은 패턴.

```
data/marketing_packages/pkg_YYYYMMDD_xxx.json     패키지(초안 슬롯 비어 있음)
data/marketing_packages/pkg_..._brief.md          Claude Code용 작업지시서
```

패키지 `status` 전이:
```
awaiting_draft → pending_review → (채널별) published
```
- `awaiting_draft` — 지시서만 있고 내용 비어 있음. Claude Code가 채운다
- `pending_review` — 내용 채워짐. 사람이 검토
- 채널별 `publish_log`에 발행 이력 누적

기존 `generate_content_package(topic, angle)` **시그니처는 유지**한다
(라우터가 이미 호출 중). 반환 dict 구조도 `youtube`/`shorts`/`instagram`
키 그대로. 내용만 빈 슬롯 + `_brief` 경로가 들어간다.

> 대안으로 provider를 anthropic으로 돌리는 방법이 있으나(`AIResponder`가
> 지원함), 그러면 API 비용이 다시 발생하고 "Claude Code가 직접 쓴다"는
> 사업자 결정과도 어긋난다. 지시서 방식을 택한다.

### 4-2. 유튜브 발행 (문제 B)

대본만으로는 못 올린다. **영상 파일을 만들어야 한다.**

```
패키지 대본
   ↓ scripts/video/tts_narration.py  (Edge TTS, 무료)
나레이션 mp3 (장면별)
   ↓ 장면 자료: 제품 화면 캡처 / 조명 시공사진 / 오버레이 슬라이드
   ↓ ffmpeg (reel.py::build_slideshow 로직 재사용, 16:9로 확장)
mp4
   ↓ scripts/youtube/uploader.py::prepare_upload_plan
업로드 계획 JSON  ← 사람이 검토
   ↓ execute_upload_plan(approved=True, confirm=승인문구, dry_run=False)
유튜브 (privacy=private 기본)
```

신규 모듈 **1개만** 만든다:

`scripts/video/package_video.py` (L3)
- `build_from_package(package_id, aspect="16:9") -> Path`
- TTS 호출 + 이미지 시퀀스 + ffmpeg 합성
- `reel.py`의 ffmpeg 인자 구성을 재사용 (무음 AAC 트랙 함정 포함)
- 위치 근거: `scripts/video/`에 이미 TTS·녹화가 있다. 영상 생성은 여기가 맞다

라우터에 엔드포인트 2개 추가:

| 메서드 | 경로 | 동작 |
|---|---|---|
| POST | `/marketing-ops/build-video` | 패키지 → mp4 생성 (발행 아님) |
| POST | `/marketing-ops/publish-youtube` | `confirmed=true` + 문구 필수. private 업로드 |

`approve_channel()`의 "자동 게시 미구현" 문구는 인스타/유튜브가 붙으면 제거.

### 4-3. 인스타 연결

POST `/marketing-ops/publish-instagram` — `api_publish.py` 호출.
릴스는 4-2가 만든 mp4(9:16)를 그대로 쓴다.

---

## 5. 레이어·의존성 점검

```
L9 MarketingOpsClient.tsx
   └→ L8 marketing_ops_router.py
        ├→ L6 blog/marketing/{content,multichannel,publish}
        ├→ L3 video/package_video.py ─→ video/tts_narration.py
        │                            └→ instagram/reel.py (ffmpeg 로직)
        ├→ L3 youtube/uploader.py
        └→ L3 instagram/api_publish.py
```
- 역방향 import 없음 (L3가 L6/L8을 부르지 않음)
- 업무 도메인 간 직접 import 없음 (youtube ↔ instagram 서로 모름, 라우터가 조정)
- router에 SQL 없음 / core에 환경변수 직접 접근 없음
- 순환 없음

## 6. 보안·리스크

| 항목 | 처리 |
|---|---|
| 유튜브 공개 범위 | **기본 private.** public은 별도 승인 (CLAUDE.md 금지선) |
| 외부 공개 발행 | 채널별 `confirmed=true` 필수. 매번 재확인 |
| 토큰/키 | 경로만 다룬다. 값 출력·로깅 금지 |
| GPT | `openai_guard` 유지. v2는 GPT를 **더 안 쓴다** |
| 권한 | 기존 `require_role("admin","owner")` 유지 |
| 비용 | Edge TTS 무료 · ffmpeg 로컬 · 유튜브 API 무료. **추가 과금 없음** |

## 7. 영향 파일

| 파일 | 변경 |
|---|---|
| `scripts/naver/blog/marketing/multichannel.py` | 수정 — GPT 호출 → 지시서 생성 |
| `scripts/video/package_video.py` | **신규** — 패키지 → mp4 |
| `ai_orchestrator/connectors/marketing_ops_router.py` | 추가 — 엔드포인트 3개 |
| `admin-web/.../marketing/MarketingOpsClient.tsx` | 추가 — 영상생성/발행 버튼, 3채널 상태 |
| `docs/specs/marketing_ops_v2_unified.md` | 신규 — 이 문서 |

API 응답 key 변경 없음 · DB schema 변경 없음 · 기존 함수 시그니처 유지 · 기존 코드 삭제 없음

## 8. 검증

```bash
python tools/repo_gates/codebase_layer_audit.py
pytest tests/test_codebase_layer_audit.py -q
python scripts/quality_gate.py --staged --enforce --allow-existing-code-change
```
FORBIDDEN_IMPORT / SECURITY_PATTERN / CIRCULAR_IMPORT > 0 → STOP

기능 검증 순서 (라이브는 1건씩):
1. 패키지 생성 → 지시서 파일 생성 확인 (GPT 예외 안 남)
2. Claude Code가 지시서 채움 → `status=pending_review`
3. `build-video` → mp4 재생 확인
4. 유튜브 **private** 1건 업로드 → 실제 확인
5. 이상 없으면 인스타 연결

## 9. 단계

| 단계 | 내용 | 승인 |
|---|---|---|
| 1 | multichannel GPT 제거 (문제 A) | 이 기준서 승인으로 진행 |
| 2 | `package_video.py` 신규 | 〃 |
| 3 | 라우터 엔드포인트 3개 | 〃 |
| 4 | UI 보강 | 〃 |
| 5 | **유튜브 private 실업로드 1건** | **별도 재확인** |
| 6 | 인스타 실발행 | **별도 재확인** |

## 10. 열린 질문

1. **유튜브 채널 콘셉트** — 적산/물량산출(B2B)과 조명(B2C)을 한 채널에 섞을지,
   나눌지. 섞으면 구독자 타깃이 흐려진다. 미정이면 적산 먼저 private으로 쌓는다.
2. **영상 장면 자료** — 적산은 제품 화면 캡처가 있다(블로그에 쓴 것 재활용).
   조명은 시공사진이 있다. 별도 촬영은 범위 밖.
