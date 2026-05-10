# 카카오톡/카카오워크 데스크톱 연동 설계서 v2

> **작성일**: 2026-05-10  
> **이전 설계 폐기**: v1 (송수신 자동화 포함) — 아래 사유로 불가  
> **확정 방향**: 송수신은 사용자가 직접. AI는 **모니터링 · 요약 · 분류** 전담.

---

## 0. 탐지 결과 요약 (구현 근거)

| 앱 | 탐지 결과 | 자동화 가능 범위 |
|----|----------|----------------|
| **카카오워크** | ConversationListBox(UIA) 정상 노출. 채팅방 이름/미읽음/마지막 메시지 추출 성공. 메시지 영역·입력창은 CefSharp webBrowserView 내부 → UIA/CDP 모두 불가 | 채팅방 목록 폴링, 미읽음 감지 |
| **카카오톡** | GDI 자체 렌더링(EVA_Window_Dblclk). UIA 노드 12개뿐 (PaneControl만). 텍스트 추출 불가 | "대화 내보내기" 파일 파싱 |
| **다운로드 폴더** | 사진/파일 저장 경로 탐지 필요 (사용자 설정 확인 후) | watchdog 폴링 |

---

## 1. 역할 분담

| 역할 | 담당 |
|------|------|
| 메시지 송신 | **사용자 직접** |
| 메시지 수신 (읽기) | **사용자 직접** |
| 채팅방 미읽음 모니터링 | AI (ConversationListBox 폴링) |
| 메시지 텍스트 요약 | AI (대화 내보내기 파일 파싱 후 LLM) |
| 사진/파일 다운로드 감지 | AI (다운로드 폴더 watchdog) |
| 사진/파일 분류 | AI (AI Vision + 파일 분류 규칙) |
| 검색 인덱스 생성 | AI (파싱된 메시지 기반) |

---

## 2. 디렉토리 구조

```
ai_orchestrator/local_agent/
├── browser/                         # 기존 (네이버 등)
└── desktop/                         # 신규
    ├── __init__.py
    ├── desktop_agent.py             # DesktopAgent (Mixin 조합)
    ├── mixins/
    │   ├── __init__.py
    │   ├── kakaowork_mixin.py       # ConversationListBox 폴링
    │   └── kakaotalk_mixin.py      # export 파일 파싱
    ├── kakaotalk_export.py          # 대화 내보내기 파서
    ├── download_watcher.py          # 다운로드 폴더 watchdog
    ├── summarizer.py                # LLM 메시지 요약
    ├── classifier.py                # 파일/이미지 분류
    └── ui_helpers.py                # 공통 UIA 헬퍼
```

```
scripts/
├── explore_kakao_desktop.py         # 완료 — KakaoTalk/KakaoWork UIA 탐지
├── explore_kakaowork.py             # 완료 — ConversationListBox 상세 탐지
├── explore_kakaowork_active.py      # 완료 — 채팅방 클릭 후 재탐지
└── monitor_kakao.py                 # 신규 — 통합 모니터링 CLI
```

---

## 3. 카카오워크 모니터링 (KakaoworkMixin)

### 3.1 가능 범위

ConversationListBox에서 추출 가능한 항목:
- 채팅방 이름 (TextControl depth=1)
- 마지막 메시지 미리보기 (TextControl depth=1, 2번째)
- 미읽음 카운트 (숫자 TextControl)
- 마지막 활동 시간

메시지 본문 전체 / 입력창 → **불가** (CefSharp 내부)

### 3.2 메서드

```python
class KakaoworkMixin:
    def kakaowork_window(self) -> WindowControl | None:
        """카카오워크 메인 창 핸들 (psutil PID 기반)."""

    def kakaowork_list_rooms(self) -> list[dict]:
        """채팅방 목록 스냅샷.
        반환: [{name, last_msg, unread_count, last_time}]
        """

    def kakaowork_unread_rooms(self) -> list[dict]:
        """미읽음이 있는 채팅방만 필터링."""

    def kakaowork_poll(self, interval: int = 30,
                       on_new_unread=None) -> None:
        """주기적 폴링. 미읽음 변화 시 on_new_unread(rooms) 호출.
        블로킹 — 별도 스레드에서 실행.
        """
```

---

## 4. 카카오톡 메시지 읽기 (KakaotalkMixin)

### 4.1 대화 내보내기 파일

사용자가 채팅방 우측 상단 메뉴 → "대화 내보내기" → 텍스트 파일 저장.  
AI가 파일 변경을 감지하여 자동 파싱.

**파일 형식**:
```
카카오톡 대화
대화 상대: 개발팀
저장한 날짜: 2026-05-10 14:30

2026년 5월 10일 토요일
[홍길동] [오후 2:30] 안녕하세요
[김철수] [오후 2:31] 네 안녕하세요
```

### 4.2 모듈: `kakaotalk_export.py`

```python
DEFAULT_SEARCH_DIRS = [
    Path.home() / "Downloads",
    Path.home() / "Documents" / "KakaoTalk Downloads",
    Path.home() / "OneDrive" / "Downloads",
]

def find_export_files(dirs=DEFAULT_SEARCH_DIRS) -> list[Path]:
    """KakaoTalk*.txt 파일 탐색."""

def parse_export_file(path: Path) -> dict:
    """파싱 결과.
    반환: {
        room_name: str,
        saved_at: str,
        messages: [{date, sender, time, text}],
    }
    """

def latest_export(dirs=DEFAULT_SEARCH_DIRS) -> Path | None:
    """가장 최근 저장된 export 파일."""

def watch_for_new_export(callback, dirs=DEFAULT_SEARCH_DIRS) -> None:
    """새 export 파일 감지 시 callback(path) 호출. watchdog 기반."""
```

### 4.3 메서드

```python
class KakaotalkMixin:
    def kakaotalk_load_export(self, path: Path | None = None) -> dict:
        """export 파일 파싱. path=None이면 latest_export 사용."""

    def kakaotalk_messages(self, max_n: int = 100,
                            sender: str | None = None) -> list[dict]:
        """최근 메시지 필터링. sender 지정 시 해당 발신자만."""

    def kakaotalk_summary(self, max_n: int = 50) -> str:
        """최근 N개 메시지 LLM 요약 텍스트."""
```

---

## 5. 다운로드 감지 + 분류 (DownloadWatcher)

### 5.1 `download_watcher.py`

```python
KAKAO_DOWNLOAD_DIRS = [
    Path.home() / "Downloads",
    Path.home() / "Pictures" / "카카오톡 받은 파일",
    Path.home() / "OneDrive" / "Pictures",
]

class DownloadWatcher:
    def __init__(self, dirs=KAKAO_DOWNLOAD_DIRS, callback=None):
        """dirs에 새 파일 생성 시 callback(path, file_type) 호출."""

    def start(self) -> None:
        """watchdog 시작 (백그라운드 스레드)."""

    def stop(self) -> None:
        """watchdog 중지."""

    def scan_existing(self) -> list[dict]:
        """기존 파일 스캔. 반환: [{path, type, size, mtime}]"""
```

### 5.2 `classifier.py`

```python
def classify_file(path: Path) -> dict:
    """파일 분류.
    반환: {
        category: "image" | "video" | "document" | "audio" | "other",
        subcategory: "photo" | "screenshot" | "invoice" | ...,
        suggested_folder: str,
        tags: list[str],
    }
    이미지: PIL EXIF 분석 + (선택) Claude Vision API
    문서: 확장자 + 크기
    """

def organize_files(files: list[dict], base_dir: Path) -> dict:
    """분류 결과에 따라 파일을 base_dir 하위 폴더로 이동.
    반환: {moved: int, skipped: int, errors: list}
    """
```

---

## 6. AI 요약 (summarizer.py)

```python
def summarize_messages(messages: list[dict], model: str = "claude-haiku-4-5-20251001") -> str:
    """메시지 목록 → 핵심 내용 요약 (Claude API 호출).
    반환: 자연어 요약 텍스트
    """

def extract_action_items(messages: list[dict]) -> list[str]:
    """메시지에서 할 일/요청 항목 추출."""

def extract_keywords(messages: list[dict]) -> list[str]:
    """검색용 키워드 추출."""
```

---

## 7. DesktopAgent (통합)

```python
class DesktopAgent(KakaoworkMixin, KakaotalkMixin):
    """Windows 데스크톱 앱 모니터링·요약·분류 에이전트."""

    def __init__(self):
        self._kw_window_cache = None
        self._watcher: DownloadWatcher | None = None

    def __enter__(self):
        self._watcher = DownloadWatcher()
        self._watcher.start()
        return self

    def __exit__(self, *_):
        if self._watcher:
            self._watcher.stop()

    def full_report(self) -> dict:
        """전체 상태 리포트.
        반환: {
            kakaowork_rooms: list[dict],
            kakaowork_unread: list[dict],
            kakaotalk_latest_export: str | None,
            kakaotalk_summary: str,
            recent_downloads: list[dict],
        }
        """
```

---

## 8. 사용 예시

```python
from ai_orchestrator.local_agent.desktop.desktop_agent import DesktopAgent

with DesktopAgent() as a:
    # 카카오워크 미읽음 확인
    unread = a.kakaowork_unread_rooms()
    for r in unread:
        print(f"[카카오워크] {r['name']} — 미읽음 {r['unread_count']}건")
        print(f"  마지막: {r['last_msg']}")

    # 카카오톡 대화 요약
    a.kakaotalk_load_export()
    summary = a.kakaotalk_summary(max_n=100)
    print(f"\n[카카오톡 요약]\n{summary}")

    # 전체 리포트
    report = a.full_report()
```

---

## 9. 단계별 구현 순서

> 직렬, 한 단계씩, 각 단계 완료 후 검증

| 단계 | 작업 | 검증 기준 |
|------|------|----------|
| **Step 1** | `desktop/` 골격 생성 (빈 모듈) | import 오류 없음 |
| **Step 2** | `ui_helpers.py` + `KakaoworkMixin` 구현 | 채팅방 목록 추출, 미읽음 감지 |
| **Step 3** | `kakaotalk_export.py` + `KakaotalkMixin` 구현 | export 파일 파싱, 메시지 100건 추출 |
| **Step 4** | `download_watcher.py` + `classifier.py` 구현 | 새 파일 감지, 카테고리 분류 |
| **Step 5** | `summarizer.py` 구현 | 메시지 요약 1건 성공 |
| **Step 6** | `DesktopAgent` 통합 + `monitor_kakao.py` CLI | `full_report()` 1회 실행 성공 |

---

## 10. 절대 금지 사항

- 메시지 자동 송신 (사용자 직접 담당)
- 카카오 ID/PW 자동 입력
- 인증번호 자동 추출
- DLL 인젝션 / 메모리 후킹
- 다른 사람 메시지 무단 전송

---

**다음 작업**: Step 1 — `desktop/` 디렉토리 골격 생성
