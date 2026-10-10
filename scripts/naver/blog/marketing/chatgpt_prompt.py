"""ChatGPT 탭(CDP)에 프롬프트를 넣고 전송 버튼을 누르는 공용 함수.

gpt_images._send_prompt·gpt_writer._send_prompt 가 입력 뒤 대기 시간(0.5초/0.8초)만 다르게
똑같이 복사해 쓰던 본문을 한 곳으로 모았다. 대기 시간은 호출하는 쪽이 넘긴다.
"""

from __future__ import annotations

import time

from scripts.browser.cdp.cdp_helper import CDP


def send_chatgpt_prompt(cdp: CDP, prompt: str, settle_s: float) -> str:
    """입력창 포커스 → 프롬프트 입력 → settle_s 초 대기 → 전송 버튼 클릭. 결과 문자열('clicked' 또는 실패 사유)."""
    focus_result = cdp.js("""(function(){
      var ta = document.querySelector('#prompt-textarea');
      if (!ta) return 'textarea not found';
      ta.focus();
      return 'focused';
    })()""")
    if focus_result != "focused":
        return focus_result
    time.sleep(0.3)
    cdp.send("Input.insertText", {"text": prompt})
    time.sleep(settle_s)
    return cdp.js("""(function(){
      var btn = document.querySelector('button[data-testid="send-button"]');
      if (!btn) return 'send button not found';
      btn.click();
      return 'clicked';
    })()""")
