# 네이버 블로그 글쓰기 파이프라인 설계서

작성일: 2026-05-19  
검증일: 2026-05-19 (실브라우저 전수 검증 완료)  
대상 모듈: `scripts/naver/blog/writer.py`

---

## 1. 개요

네이버 SmartEditor3(SE3) 기반 블로그 글쓰기 자동화 파이프라인.  
"블로그 작성해줘" 요청 시 로그인 확인 → 편집기 열기 → 내용 작성 → 편집 도구 적용 → 발행까지 전 단계를 자동 처리한다.

### 핵심 변경사항 (2026-05-19)

| 항목 | 이전 | 현재 |
|------|------|------|
| iframe 구조 | mainFrame iframe 탐색 | iframe 없음 — 메인 페이지 직접 렌더링 |
| 글쓰기 URL | `PostWriteForm.naver` (blogId 없음) | `PostWriteForm.naver?blogId=skyjwsin` 필수 |
| 제목 셀렉터 | `.se-title-input` (구버전) | `.se-section-documentTitle` |
| 본문 셀렉터 | `.se-text-paragraph` | `.se-section-text` |
| 발행 버튼 | `button:has-text("발행")` | `get_by_role("button", name="발행", exact=True)` |
| 최종발행 버튼 | `.btn_confirm` | `[class*="confirm_btn"]` |
| 공개설정 값 | public=0 (오류) | public=2 (실검증) |

---

## 2. 파이프라인 단계

```
[요청] 주제 / 직접 작성 내용 (title, body, tags)
  ↓
[1] 로그인 확인 (ensure_naver_login)
      └→ 미로그인 시 자동 로그인
  ↓
[2] blog_id 감지 (_detect_blog_id)
      └→ section.blog.naver.com의 admin 링크에서 추출
      └→ 또는 명시 전달 (blog_id='skyjwsin')
  ↓
[3] 편집기 열기 (open)
      └→ PostWriteForm.naver?blogId=skyjwsin
      └→ .se-section-documentTitle 로드 대기 (최대 15초)
      └→ 임시저장 복원 다이얼로그 자동 취소
  ↓
[4] 제목 입력 (set_title)
      └→ .se-section-documentTitle 클릭 → keyboard.type
  ↓
[5] 본문 작성 (write_body)
      └→ .se-section-text 클릭 → 단락 단위 입력
      └→ \n\n = Enter(단락), \n = Shift+Enter(줄바꿈)
  ↓
[6] 편집 도구 적용 (선택)
      └→ 구분선 / 인용구 / 이미지 / 코드블록 / 링크카드
      └→ 텍스트 서식 (굵게 / 기울이기 / 글자크기 / 정렬)
  ↓
[7] 임시저장 OR 발행 패널 열기
      └→ 임시저장: button:has-text("저장")
      └→ 발행: get_by_role("button", name="발행", exact=True)
  ↓
[8] 발행 패널 옵션 설정 (발행 시에만)
      └→ 카테고리 / 태그 / 공개설정 / 댓글허용
  ↓
[9] 최종 발행 ([class*="confirm_btn"])
  ↓
[10] 발행 검증 (verify_published)
       └→ URL 패턴 매칭 → blog_id + log_no 추출
```

---

## 3. SE3 편집 도구 (data-name 기준, 실검증 완료)

### 3-1. 삽입 도구

| 도구 | 메서드 | data-name | 검증 | 비고 |
|------|--------|-----------|------|------|
| 사진 | `insert_image(path/url)` | `image` | ✅ | 로컬파일/URL 분기 |
| 인용구 | `insert_quote(text, style=0)` | `quotation` | ✅ | style=0~N |
| 구분선 | `insert_divider(style=0)` | `horizontal-line` | ✅ | style=0~N |
| OG 링크 카드 | `insert_link(url)` | `oglink` | ✅ | floating-search 입력창 |
| 텍스트 링크 | `insert_text_link(url, text)` | `text-link` | — | 선택된 텍스트에 적용 |
| 소스코드 | `insert_code_block(code, lang)` | `code` | ✅ | language 선택 지원 |
| 표 | — | `table` | — | 미구현 |
| 동영상 | — | `video` | — | 미구현 |

### 3-2. 텍스트 서식 도구

| 도구 | 메서드 | data-name | 검증 |
|------|--------|-----------|------|
| 굵게 | `set_bold()` | `bold` | — |
| 기울이기 | `set_italic()` | `italic` | — |
| 밑줄 | `set_underline()` | `underline` | — |
| 취소선 | `set_strikethrough()` | `strikethrough` | — |
| 글자 크기 | `set_font_size(n)` | `font-size` | — |
| 문단 서식 | `set_text_format(name)` | `text-format` | — |
| 정렬 | `set_align(left/center/right/justify)` | `align-drop-down-with-justify` | — |
| 맞춤법 | `spellcheck()` | `speller` | — |

### 3-3. 공통 헬퍼

```python
def _toolbar_click(self, data_name: str, wait_s: float = 0.5) -> bool:
    """data-name 기준 툴바 버튼 클릭."""
    self.page.locator(f'button[data-name="{data_name}"]').first.click(timeout=3000)
```

---

## 4. 발행 패널 실검증 값

### 공개설정 라디오 (input[name="open_type"])

| 값 | 의미 | VISIBILITY_MAP 키 |
|----|------|-------------------|
| `2` | 전체공개 (기본값) | `"public"` |
| `1` | 이웃공개 | `"neighbors"` |
| `3` | 서로이웃공개 | `"mutual"` |
| `0` | 비공개 | `"private"` |

> ⚠️ 이전 설계서의 값(public=0)은 오류였음. 2026-05-19 실검증으로 수정.

### 버튼 클래스 (해시 포함, 변경 가능성 있음)

| 버튼 | 클래스 | 셀렉터 전략 |
|------|--------|------------|
| 저장 | `save_btn__bzc5B` | `button:has-text("저장")` |
| 발행 (상단) | `publish_btn__m9KHH` | `get_by_role("button", name="발행", exact=True)` |
| 발행 (패널 확인) | `confirm_btn__WEaBq` | `[class*="confirm_btn"]` |
| 예약 발행 | `reserve_btn__Km5Xh` | 미사용 (not visible) |

### 태그 입력

```
input[placeholder*="태그"]  →  placeholder="태그 입력 (최대 30개)"
Enter 키로 태그 구분
```

---

## 5. 편의 함수

```python
from scripts.naver.blog.writer import write_post

result = write_post(
    page,
    title="제목",
    body="본문\n\n단락2",          # \n\n = 단락 구분
    tags=["태그1", "태그2"],
    category="카테고리명",
    visibility="public",           # public/neighbors/mutual/private
    images=["data/images/a.jpg"],  # 본문 시작 이미지
    save_draft_only=False,         # True = 임시저장만
    schedule_at=None,              # datetime 지정 시 예약 발행
)
# 반환: {"ok": True, "url": "...", "blog_id": "...", "log_no": "..."}
```

---

## 6. 발행 패널 열기 순서 (중요)

태그/공개설정은 **발행 패널 열기 이후**에 나타남.  
`write_post()`는 아래 순서를 강제한다.

```
1. set_title()
2. write_body()
3. [save_draft_only=True] → save_draft() 즉시 반환
4. [발행 시] 발행 버튼 클릭 (패널 열기)
5. set_category / set_tags / set_visibility / set_comments_allowed
6. publish() → confirm_btn 클릭 → verify_published()
```

---

## 7. blog_id 자동 감지 로직

```
section.blog.naver.com 접속
  ↓
a[href*="admin.blog.naver.com/"] 링크 탐색
  ↓
admin.blog.naver.com/{blog_id}/stat/today 패턴에서 추출
  ↓
"stat" / "category" / "manage" 제외 후 반환
```

---

## 8. 제약사항 및 보안 정책

- **외부 공개 발행**: CLAUDE.md 기준 매번 사용자 승인 필수
- **쿠키/session 추출 금지**: storage_state 서버 전송 불가
- **자격증명 출력 금지**: ID/PW 로그 기록 없음
- **임시저장 다이얼로그**: open() 시 항상 "취소" 클릭 → 기존 임시저장 무시하고 새 글 시작
- **편집기 대기**: `.se-section-documentTitle` 최대 15초 대기 후 실패 처리

---

## 9. 파일 위치

| 역할 | 파일 |
|------|------|
| 핵심 작성기 | `scripts/naver/blog/writer.py` |
| CLI 진입점 | `scripts/naver/blog/_runner.py` |
| AI 초안 생성 | `scripts/naver/blog/ai_writer.py` |
| SEO 분석 | `scripts/naver/blog/seo.py` |
| 고도화 워크플로 | `scripts/naver/blog/writer_pro.py` |
| 로그인 | `scripts/naver/auth.py` |
