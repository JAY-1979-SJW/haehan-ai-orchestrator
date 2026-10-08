"""스마트스토어 고객문의 답변 자동 입력/제출 로직 (L5 Site Module).

CDP로 열려있는 스마트스토어센터 고객문의 상세 화면(#/naverpay/qnas 상세)에서
답변을 채우고 제출한다.

- fill_reply_draft(): 답변 textarea에 초안만 채운다 (read-only 성격, 승인 불필요).
- submit_reply(): 실제 "답변하기" 클릭까지 수행 — 고객 노출 메시지 전송이므로
  CLAUDE.md 정책상 사용자가 매번 명시적으로 승인한 뒤에만 호출한다.

배경(2026-08-23 실측): 이 페이지는 답변 textarea에 실제 키보드로 타이핑하면
자동으로 "문의유형=직접입력, 답변템플릿=답변직접입력(제목없음)"으로 전환되는데,
JS로 값만 주입하면 이 전환이 발생하지 않아 제출 시 "제목을 선택해 주세요"
alert로 막힌다. submit_reply()는 페이지의 $Form/$Element 프레임워크 함수를
직접 호출해 이 전환을 재현한 뒤 제출한다. 문의유형 select를 사람이 직접
바꾸면 프레임워크가 답변 내용을 지우는 부작용이 있으므로, fill 이후에만
호출해야 한다.

사용법:
    from scripts.browser.cdp.cdp_helper import CDP
    from scripts.naver.smartstore.inquiry_reply import fill_reply_draft, submit_reply

    cdp = CDP(port=9222)
    fill_reply_draft(cdp, "답변 내용")
    # 사용자 승인 후에만:
    message = submit_reply(cdp)  # "답변처리가 완료되었습니다." 등 결과 alert 메시지 반환
"""

import json
import time

from scripts.browser.cdp.cdp_helper import CDP
from scripts.common.publish_guard import guarded

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

_SET_DIRECT_INPUT_JS = """(function(){
  var f = document.querySelector('iframe');
  var w = f.contentWindow;
  w.$Form('answerForm').value('inquiryAnswerTempleteType','NONE_SELECTED');
  w.$Element('inquiryAnswerTempleteNo').empty();
  w.$Element('inquiryAnswerTempleteNo').appendHTML('<option value="NONE_SELECTED">답변직접입력(제목없음)</option>');
  w.$Element('inquiryAnswerTempleteNo').attr('disabled', true);
  w.$Element('inquiryAnswerTempleteNo').attr('disabled', false);
  return 'templateType=' + w.$Form('answerForm').value('inquiryAnswerTempleteType')
    + ' templateNo=' + w.$Form('answerForm').value('inquiryAnswerTempleteNo')
    + ' content_len=' + w.$Form('answerForm').value('content').length;
})()"""

_CLICK_SUBMIT_JS = """(function(){
  var f = document.querySelector('iframe');
  var d = f.contentDocument || f.contentWindow.document;
  var links = Array.from(d.querySelectorAll('a'));
  var link = links.find(a => a.textContent.trim() === '답변하기' || a.textContent.trim() === '답변수정');
  if (!link) return 'not found';
  link.click();
  return 'clicked';
})()"""


def fill_reply_draft(cdp: CDP, text: str) -> str:
    """답변 textarea(화면에 실제 렌더된 것)에 초안을 채운다. 결과 메시지 문자열 반환."""
    js = _FILL_JS_TEMPLATE.format(text_json=json.dumps(text, ensure_ascii=False))
    return cdp.js(js)


@guarded("smartstore_inquiry_reply", ok_fn=lambda msg: "완료" in msg)
def submit_reply(cdp: CDP, timeout: float = 5.0, approval: str | None = None) -> str:
    """채워진 답변을 실제로 전송한다 ("답변하기" 클릭). 고객 노출 액션 — 매번 사용자 승인 후 호출.

    approval: 사용자가 직접 입력한 승인 문구. 없거나 다르면 GateBlocked(전송하지 않는다). 자동으로 채우지 않는다.

    반환값: 결과 alert 메시지 (성공 시 "답변처리가 완료되었습니다.", 검증 실패 시
    "제목을 선택해 주세요." 등). alert가 없으면 마지막 JS 반환값을 그대로 준다.
    """
    from scripts.common.gate import require_approved

    require_approved("smartstore_reply", approval, via="smartstore_inquiry_reply")
    cdp.send("Page.enable")
    dialog_info: dict = {}

    def on_dialog(params):
        dialog_info.update(params)

    cdp.on("Page.javascriptDialogOpening", on_dialog)
    try:
        setup_result = cdp.js(_SET_DIRECT_INPUT_JS)
        click_result = cdp.js(_CLICK_SUBMIT_JS)
        if click_result != "clicked":
            return f"setup={setup_result} click={click_result}"

        waited = 0.0
        while not dialog_info and waited < timeout:
            time.sleep(0.5)
            waited += 0.5

        if dialog_info:
            cdp.send("Page.handleJavaScriptDialog", {"accept": True})
            return dialog_info.get("message", "")
        return "no dialog (timeout)"
    finally:
        cdp.off("Page.javascriptDialogOpening")
