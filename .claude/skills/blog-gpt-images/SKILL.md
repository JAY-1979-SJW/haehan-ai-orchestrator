---
name: blog-gpt-images
description: 네이버 블로그용 커스텀 사진을 ChatGPT 웹(chatgpt.com)으로 생성해 로컬에 다운로드하는 CDP 자동화. "GPT로 이미지 만들어줘", "블로그 사진 GPT로 생성해" 같은 요청에 사용. Unsplash 재고사진 대신 글 내용에 정확히 맞는 장면이 필요할 때. 2026-08-23 사용자 승인 하 구현·실전 검증 완료.
---

# ChatGPT 웹 이미지 생성 → 네이버 블로그 첨부

## ⚠️ 매번 사용자 승인 필요

GPT(ChatGPT)를 쓰는 작업이라 CLAUDE.md "외부 유료 AI API 호출 승인제"
대상이다. 코드는 이미 있지만, **실제 실행(이미지 생성 요청)은 매번
사용자에게 확인받은 뒤에 한다** — 사전 승인이 이 스킬 자체를 만들어도
된다는 뜻이지, 매 호출을 영구 승인한다는 뜻이 아니다.

비용은 API 과금이 아니라 사용자의 **ChatGPT Plus 구독**(정액제) 사용량이다.

## 언제 쓰나

- Unsplash(`images.py`, 기본 경로)는 재고 사진이라 글 내용과 정확히
  맞는 장면(예: "하도급 계약서에 도장 찍는 손")을 못 찾을 때가 많다.
- 이 스킬은 **그 장면을 정확히 지정해서 새로 생성**한다.
- 기본은 여전히 Unsplash — 이 스킬은 Unsplash로 안 되는 특정 장면이
  필요할 때만 쓰는 보조 경로다.

## 사용법

```python
from scripts.browser.cdp.cdp_helper import CDP
from scripts.naver.blog.marketing.gpt_images import generate_image

cdp = CDP(port=9222)
result = generate_image(
    cdp,
    "건설 하도급 계약서에 도장을 찍는 손, 서류 위 계약서와 인감, "
    "사무적이고 신뢰감 있는 분위기, 사진 같은 느낌, 텍스트 없음",
    out_path="data/gpt_images/draft02_img1.png",
)
print(result)  # "ok: data/gpt_images/draft02_img1.png" 또는 에러 메시지
```

생성된 파일을 원고 JSON의 `"images"` 배열에 넣어
`blog_publish_manual.py --check`로 확인하면 된다 — 이 부분은 Unsplash
경로와 동일하다.

## 프롬프트 작성 요령 (실전 검증됨)

- **"텍스트 없음"을 항상 넣는다** — 안 넣으면 이미지 안에 글자가 생겨서
  블로그에 못 쓴다.
- **"사진 같은 느낌"을 넣는다** — 안 넣으면 일러스트/3D 렌더 느낌이 나서
  다른 톤과 안 맞을 수 있다.
- 인물 사진은 **직업·상황을 구체적으로** 지정한다("건설 현장에서 서류를
  검토하는 실무자" 같은 식). 막연하면 결과가 산으로 간다.
- GPT 이미지는 **정확한 치수·구조를 반영하지 못한다**
  ([[apartment-lighting-plan]] 스킬에서도 같은 한계 확인됨) — "분위기
  렌더"로만 쓰고 "정확한 도면"이라고 표현하지 않는다.

## 실측 함정 (코드에 이미 반영됨, 참고용)

1. **이미지 다운로드는 `fetch()`+`btoa()`로 안 된다** — `cdp.js()`가
   내부적으로 `Runtime.evaluate`를 쓰는데 Promise를 기다리지 않아서
   base64 인코딩이 항상 실패한다. 대신 이미지 요소의
   `getBoundingClientRect()`로 좌표를 구해서 `Page.captureScreenshot`의
   `clip` 옵션으로 그 영역만 스크린샷 찍는 방식으로 우회했다.
2. **사이드바 채팅 목록에도 같은 도메인 패턴의 작은 썸네일 `<img>`가
   있다** — src만 보고 찾으면 20×20짜리 썸네일을 오탐한다. 반드시
   `width > 100 && height > 100` 크기 필터를 같이 건다
   (`gpt_images.py::_FIND_LARGE_IMAGE_JS`).
3. **`src`가 채워진 시점 ≠ 렌더 완료 시점** — src가 붙은 직후엔 회색
   로딩 스켈레톤("미리 보기" 라벨)이 여전히 화면에 있고, 실제 사진은
   몇 초 뒤에야 뜬다. "편집" 버튼 텍스트로 완료를 감지하려 했으나
   안정적으로 안 잡혀서, **src 확인 후 고정 지연(8초)**으로 대체했다.
4. **`Emulation.setDeviceMetricsOverride`로 고정 크기를 강제하면 클립
   좌표가 실제 창 크기와 어긋난다** — `clear_device_metrics()`는
   `clearDeviceMetricsOverride`만 호출하고 재설정하지 않는다. 재설정을
   했다가 캡처 결과가 새까맣게 나오는 문제를 실제로 겪었다.

## 관련 스킬

- [[naver-blog-publish]] — 원고 작성·SEO 점검·발행 본체. 이 스킬은 그
  파이프라인의 이미지 소스 중 하나(Unsplash 대체용)일 뿐이다.
- [[apartment-lighting-plan]] — GPT 이미지의 "치수 부정확" 한계를 먼저
  실측한 스킬. 같은 한계가 여기도 적용된다.
