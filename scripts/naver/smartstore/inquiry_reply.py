"""스마트스토어 고객문의 답변창 자동 입력 로직 (L5 Site Module).

CDP로 열려있는 스마트스토어센터 고객문의 상세 화면(#/naverpay/qnas 상세)에서
답변 textarea를 찾아 초안을 채운다. 실제 전송("답변하기" 클릭)은 포함하지
않는다 — CLAUDE.md 정책상 고객 노출 메시지 전송은 매번 사용자 승인 필요.

사용법:
    from scripts.cdp_helper import CDP
    from scripts.naver.smartstore.inquiry_reply import fill_reply_draft

    cdp = CDP(port=9222)
    fill_reply_draft(cdp, "답변 내용")
"""

import json

from scripts.cdp_helper import CDP

# 문의 상세 화면엔 숨겨진(0x0) textarea가 먼저 잡히는 경우가 있어(2026-08-23 실측),
# 화면에 실제로 렌더된(너비>0) textarea만 후보로 삼는다.
_FILL_JS_TEMPLATE = """(function(){{
  var f = document.querySelector('iframe');
  if (!f) return 'iframe not found';
  var d = f.contentDocument || f.contentWindow.document;
  var tas = Array.from(d.querySelectorAll('textarea')).filter(function(ta){{
    return ta.getBoundingClientRect().width > 50;
  }});
  if (!tas.length) return 'visible textarea not found';
  var ta = tas[0];
  var setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
  setter.call(ta, {text_json});
  ta.dispatchEvent(new Event('input', {{bubbles:true}}));
  ta.dispatchEvent(new Event('change', {{bubbles:true}}));
  return 'ok len=' + ta.value.length;
}})()"""


def fill_reply_draft(cdp: CDP, text: str) -> str:
    """답변 textarea(화면에 실제 렌더된 것)에 초안을 채운다. 결과 메시지 문자열 반환."""
    js = _FILL_JS_TEMPLATE.format(text_json=json.dumps(text, ensure_ascii=False))
    return cdp.js(js)
