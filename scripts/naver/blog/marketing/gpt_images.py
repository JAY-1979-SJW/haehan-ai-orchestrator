"""ChatGPT(웹) 이미지 생성 자동화 — 블로그용 커스텀 사진 확보 (raw CDP 기반, L5).

Unsplash(`images.py`)는 재고 사진이라 우리 글 내용과 딱 맞는 장면을 못 찾을
때가 많다. 이 모듈은 chatgpt.com(사용자의 ChatGPT Plus 구독, API 과금 아님)을
CDP로 열어 프롬프트로 이미지를 생성시키고 로컬에 저장한다.

**승인 필요**: GPT를 쓰는 작업이므로 CLAUDE.md "외부 유료 AI API 호출
승인제" 대상 — 매번 실행 전 사용자 승인을 받는다(2026-08-23 사용자 승인
하에 최초 구현·검증됨).

2026-08-23 실사 검증 — **함정들**:
  1. `fetch()` + `btoa()`로 이미지를 base64 인코딩해 가져오려 했으나
     `cdp.js()`(Runtime.evaluate, awaitPromise 미사용)가 Promise를 기다리지
     않아 실패했다. **대신 이미지 요소의 bounding rect를 구해 그 영역만
     `Page.captureScreenshot`으로 클립 캡처**하는 방식으로 우회한다.
  2. 이 세션에서 원인 불명의 `Emulation` 디바이스 메트릭 오버라이드가 걸려
     있어 스크린샷이 30×30짜리로 나온 적이 있다. `capture_element()` 호출
     전에 항상 `clear_device_metrics()`로 리셋한다.
  3. 이미지가 완전히 로딩되기 전에 캡처하면 검은 사각형만 나온다 — 생성
     완료 후 몇 초 대기하고, `img` 태그의 실제 `src`가 채워졌는지 확인한
     다음 캡처한다.

사용법:
    from scripts.browser.cdp.cdp_helper import CDP
    from scripts.naver.blog.marketing.gpt_images import generate_image

    cdp = CDP(port=9222)
    path = generate_image(cdp, "건설 현장에서 서류를 검토하는 실무자, 사진 같은 느낌, 텍스트 없음",
                           out_path="data/gpt_images/제비율표_01.png")
"""

import json
import time
from pathlib import Path

from scripts.browser.cdp.cdp_helper import CDP
from scripts.naver.blog.marketing.chatgpt_prompt import send_chatgpt_prompt


def clear_device_metrics(cdp: CDP) -> None:
    """디바이스 메트릭 오버라이드를 해제한다 (2026-08-23 실측 함정 참고).

    한때 원인불명의 오버라이드로 스크린샷이 30x30이 된 적이 있어 clear를
    호출한다. 그런데 **고정 크기(1440x900)로 재설정하면 실제 창 크기와
    어긋나 클립 좌표가 틀어지는 재현 안 되는 버그를 한 번 겪었다** — 그
    이후로는 clear만 하고 override를 다시 걸지 않는다(자연 크기 사용).
    """
    cdp.send("Emulation.clearDeviceMetricsOverride")


def _send_prompt(cdp: CDP, prompt: str) -> str:
    return send_chatgpt_prompt(cdp, prompt, 0.5)


_FIND_LARGE_IMAGE_JS = """(function(){
  var imgs = Array.from(document.querySelectorAll('img'));
  var candidates = imgs.filter(function(img){
    var matchesSrc = img.src.indexOf('oaiusercontent') > -1 || img.src.indexOf('backend-api/estuary') > -1;
    if (!matchesSrc) return false;
    var r = img.getBoundingClientRect();
    return r.width > 100 && r.height > 100;
  });
  return candidates.length ? candidates[candidates.length - 1].src : '';
})()"""

# src가 채워진 뒤 실제 픽셀이 렌더될 때까지 걸리는 여유시간(2026-08-23 실측 —
# 2초로는 부족해 회색 스켈레톤이 캡처됐다. 8초로 늘림).
_POST_SRC_SETTLE_S = 8.0


def _wait_for_image(cdp: CDP, timeout: float = 90.0, poll: float = 3.0) -> bool:
    """이미지 생성이 끝나 실제 큰(사이드바 썸네일 아닌) 이미지가 뜰 때까지 대기.

    사이드바 채팅 목록에도 같은 도메인 패턴의 작은 썸네일 img가 떠서
    (2026-08-23 실측 함정) 크기 필터가 없으면 그걸로 오탐한다.

    src가 채워진 시점 ≠ 렌더 완료 시점(2026-08-23 실측 함정) — src가 붙은
    직후엔 로딩 스켈레톤("미리 보기" 라벨의 회색 박스)이 여전히 화면에
    보이고, 실제 사진은 몇 초 뒤에 뜬다. "편집" 버튼 텍스트로 완료를
    감지하려 했으나 안정적으로 안 잡혀(2026-08-23), src 확인 후 고정
    지연(`_POST_SRC_SETTLE_S`)으로 대체했다 — 덜 정교하지만 더 안정적이다.
    호출부에서 캡처 후 결과 이미지가 여전히 회색이면 지연을 늘릴 것.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        src = cdp.js(_FIND_LARGE_IMAGE_JS)
        if src:
            time.sleep(_POST_SRC_SETTLE_S)
            return True
        time.sleep(poll)
    return False


def capture_last_image(cdp: CDP, out_path: str, margin: int = 4) -> str:
    """대화에 마지막으로 생성된 이미지 영역만 클립해 PNG로 저장한다."""
    clear_device_metrics(cdp)
    time.sleep(0.5)

    rect_json = cdp.js("""(function(){
      var imgs = Array.from(document.querySelectorAll('img'));
      var candidates = imgs.filter(function(img){
        var matchesSrc = img.src.indexOf('oaiusercontent') > -1 || img.src.indexOf('backend-api/estuary') > -1;
        if (!matchesSrc) return false;
        var r = img.getBoundingClientRect();
        return r.width > 100 && r.height > 100;
      });
      if (!candidates.length) return '';
      var img = candidates[candidates.length - 1];
      var r = img.getBoundingClientRect();
      return JSON.stringify({x:r.left, y:r.top, w:r.width, h:r.height});
    })()""")
    if not rect_json:
        return "이미지 요소를 찾지 못함"

    rect = json.loads(rect_json)
    if rect["w"] < 50 or rect["h"] < 50:
        return f"이미지 요소가 비정상적으로 작음(w={rect['w']}, h={rect['h']}) — 로딩 미완료 가능성"

    resp = cdp.send(
        "Page.captureScreenshot",
        {
            "format": "png",
            "clip": {
                "x": rect["x"] + margin,
                "y": rect["y"] + margin,
                "width": rect["w"] - margin * 2,
                "height": rect["h"] - margin * 2,
                "scale": 1,
            },
        },
        timeout=15,
    )
    data = resp.get("result", {}).get("data", "")
    if not data:
        return f"캡처 실패: {resp}"

    import base64

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(base64.b64decode(data))
    return f"ok: {out}"


def generate_image(cdp: CDP, prompt: str, out_path: str, new_chat: bool = True) -> str:
    """프롬프트로 이미지 1장을 생성해 out_path에 저장. 결과 메시지 문자열 반환.

    new_chat=True면 매번 '새 채팅'으로 시작해 이전 대화 맥락(다른 글의
    프롬프트 등)이 섞이지 않게 한다.
    """
    if new_chat:
        cdp.js("location.href = 'https://chatgpt.com/';")
        time.sleep(2)

    send_result = _send_prompt(cdp, prompt)
    if send_result != "clicked":
        return f"전송 실패: {send_result}"

    if not _wait_for_image(cdp):
        return "이미지 생성 타임아웃(90초)"

    return capture_last_image(cdp, out_path)
