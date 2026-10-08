"""고객문의 처리 흐름 보조 로직 (L5 Site Module, raw CDP 기반).

`scripts/naver/smartstore/navigation/popup_handler.py`는 Playwright `page`
객체를 쓰는 버전이 이미 있다 — 이 세션의 CDP 문의처리 워크플로는
`scripts.browser.cdp.cdp_helper.CDP`(raw websocket)로 동작해 그 API를 그대로 재사용할
수 없어, 같은 셀렉터/의도를 CDP용으로 다시 구현했다. Playwright 기반
자동화에서는 popup_handler.dismiss_all_popups()를 쓴다.

제공 함수:
- dismiss_notice_popup(cdp): 공지 레이어 팝업을 좌표 계산 없이 JS로 닫는다.
  top document의 button.close를 우선 찾고, 없으면 iframe 안의 class 매칭을
  시도한다. 둘 다 못 찾으면 아무 것도 클릭하지 않고 실패를 반환한다 —
  좌표/크기 추측 클릭은 오작동(엉뚱한 링크 클릭) 위험이 있어 쓰지 않는다.
- set_date_range(cdp, start, end): 문의/주문 조회 화면의 기간 입력을 채운다
  (React 컨트롤드 인풋 — native setter로 값 주입).
- get_order_status(cdp, port, product_order_no): 상품주문번호로 주문 상세
  팝업을 백그라운드 탭으로 열어 텍스트를 읽고 탭을 정리한다(2026-08-23,
  유연호 문의 처리 시 검증된 방식 — 취소/환불 여부를 문의 답변 전에
  실제로 확인하기 위함).
"""

import json
import time

from scripts.browser.cdp.cdp_helper import CDP

_CLOSE_POPUP_JS = """(function(){
  // 팝업은 iframe 안이 아니라 최상위 문서에 오버레이로 렌더링되는 경우가
  // 더 흔했다(2026-08-23 실측: button.class="close") — top document를 먼저 본다.
  var topClose = document.querySelector('button.close');
  if (topClose) { topClose.click(); return 'closed via top-doc button.close'; }

  var f = document.querySelector('iframe');
  var d = f.contentDocument || f.contentWindow.document;
  var iframeClose = d.querySelector('button.close, [class*=close], [class*=Close]');
  if (iframeClose) { iframeClose.click(); return 'closed via iframe class match'; }

  // 좌표/크기 기반 추측은 시도하지 않는다 — 다른 무해해 보이는 작은 링크를
  // 잘못 클릭해 페이지를 이동시킨 사고가 실측됨(2026-08-23, "배송중
  // 목록보기" 오클릭). 못 찾으면 아무것도 하지 않는 편이 안전하다.
  return 'no popup found (button.close 없음)';
})()"""


def dismiss_notice_popup(cdp: CDP) -> str:
    """스마트스토어센터 공지 레이어 팝업을 닫는다. 결과 메시지 반환."""
    return cdp.js(_CLOSE_POPUP_JS)


_SET_DATE_RANGE_JS_TEMPLATE = """(function(){{
  var f = document.querySelector('iframe');
  var d = f.contentDocument || f.contentWindow.document;
  var inputs = Array.from(d.querySelectorAll('input')).filter(function(i){{
    return /^\\d{{4}}-\\d{{2}}-\\d{{2}}$/.test(i.value);
  }});
  if (inputs.length < 2) return 'date inputs not found: ' + inputs.length;
  var setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
  setter.call(inputs[0], {start_json});
  inputs[0].dispatchEvent(new Event('input', {{bubbles:true}}));
  inputs[0].dispatchEvent(new Event('change', {{bubbles:true}}));
  setter.call(inputs[1], {end_json});
  inputs[1].dispatchEvent(new Event('input', {{bubbles:true}}));
  inputs[1].dispatchEvent(new Event('change', {{bubbles:true}}));
  return 'set: ' + inputs[0].value + ' / ' + inputs[1].value;
}})()"""


def set_date_range(cdp: CDP, start: str, end: str) -> str:
    """조회기간 입력 2개(YYYY-MM-DD 형식)를 채운다. 결과 메시지 반환.

    문의/주문 조회 화면 전용 — 페이지가 React 컨트롤드 인풋을 쓰기 때문에
    "검색" 버튼을 직접 클릭해야 실제 반영된다(이 함수는 값만 채움).
    """
    js = _SET_DATE_RANGE_JS_TEMPLATE.format(
        start_json=json.dumps(start, ensure_ascii=False),
        end_json=json.dumps(end, ensure_ascii=False),
    )
    return cdp.js(js)


def get_order_status(cdp: CDP, port: int, product_order_no: str, timeout: float = 5.0) -> str:
    """상품주문번호로 주문 상세를 백그라운드 탭에서 조회해 본문 텍스트를 반환하고 탭을 닫는다."""
    import websocket as _ws  # 지연 임포트 — 이 함수를 안 쓰면 의존성 불필요

    url = f"https://sell.smartstore.naver.com/o/v3/manage/order/popup/{product_order_no}/productOrderDetail"
    r = cdp.send("Target.createTarget", {"url": url})
    target_id = r.get("result", {}).get("targetId")
    if not target_id:
        return f"tab open failed: {r}"

    time.sleep(1.5)
    text = ""
    try:
        ws = _ws.create_connection(f"ws://127.0.0.1:{port}/devtools/page/{target_id}", suppress_origin=True)
        try:
            ws.send(
                json.dumps(
                    {
                        "id": 1,
                        "method": "Runtime.evaluate",
                        "params": {"expression": "document.body.innerText.slice(0,3000)"},
                    }
                )
            )
            deadline = time.time() + timeout
            while time.time() < deadline:
                msg = json.loads(ws.recv())
                if msg.get("id") == 1:
                    text = msg.get("result", {}).get("result", {}).get("value", "")
                    break
        finally:
            ws.close()
    finally:
        cdp.send("Target.closeTarget", {"targetId": target_id})

    return text
