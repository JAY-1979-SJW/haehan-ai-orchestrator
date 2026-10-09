"""CDP 상시 클릭 감시 — 사용자가 브라우저에서 클릭/이동할 때마다 변화를 stdout으로 알린다.

Monitor 도구로 stdout을 스트리밍하면, URL이나 화면 텍스트가 바뀔 때마다
한 줄씩 이벤트가 찍혀 AI가 실시간으로 따라가며 처리할 수 있다.

사용법:
    python tools/runtime/cdp_click_watch.py [--interval 1.5]
"""

import argparse
import hashlib
import re
import sys
import time
from pathlib import Path

sys.path.insert(
    0, str(next(p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()))
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다

from scripts.browser.cdp.cdp_helper import CDP

CATEGORY_RULES = [
    ("고객문의", ("문의", "qna", "inquiry"), ("미답변", "고객문의", "1:1문의")),
    ("리뷰관리", ("review",), ("리뷰관리", "리뷰 답글")),
    ("주문관리", ("order", "delivery", "claim"), ("발주확인", "배송준비", "취소", "교환", "반품")),
    ("정산", ("settle",), ("정산", "지급대상")),
    ("상품관리", ("product", "goods"), ("상품관리", "상품등록", "판매중지")),
    ("알림", ("notification",), ("알림", "공지사항")),
    ("대시보드", ("dashboard", "home"), ("판매실적", "오늘의 통계")),
]


def classify(href: str, text: str) -> str:
    href_l = href.lower()
    for category, url_keys, text_keys in CATEGORY_RULES:
        if any(k in href_l for k in url_keys):
            return category
    for category, _url_keys, text_keys in CATEGORY_RULES:
        if any(k in text for k in text_keys):
            return category
    return "기타"


_COUNT_LINE_RE = re.compile(r"^([0-9,]+)\s*(건|원)$")
_NOISE_LINES = {"도움말", "배송중 목록보기"}

# 카테고리별로 의미있는 라벨만 추출 (화면 잡음 텍스트 제외)
# 주의: 상품관리 화면은 배지 라벨이 CSS 의사요소(pseudo-content)로 렌더링돼
# innerText로 읽히지 않는다(2026-08-23 실측, textContent엔 CSS 텍스트까지
# 섞여 오염됨) — 카운트 추출 대상에서 제외, classify()의 화면 분류만 적용.
COUNT_LABELS = {
    "고객문의": {"미답변", "답변대기", "답변완료", "문의종료", "전체"},
    "주문관리": {
        "신규주문(발주 전)",
        "신규주문(발주 후)",
        "발송기한 초과",
        "자동처리 예정",
        "발송전 취소요청",
        "발송전 배송지 변경",
        "발송마감 D-1",
        "발송마감 D-day",
    },
    # 오늘정산/정산예정 배지는 정산 상세 화면이 아니라 대시보드 위젯에 있다
    # (2026-08-23 실측) — 두 카테고리 모두에 등록해 어느 진입 경로든 잡는다.
    "정산": {"오늘정산", "정산예정"},
    "대시보드": {"오늘정산", "정산예정"},
}


_INNER_TEXT_JS = """(function(){
  var parts = [document.body ? document.body.innerText : ''];
  var frames = document.querySelectorAll('iframe');
  for (var i=0;i<frames.length;i++){
    try {
      var doc = frames[i].contentDocument || frames[i].contentWindow.document;
      if (doc && doc.body) parts.push(doc.body.innerText);
    } catch (e) {}
  }
  return parts.join('\\n');
})()"""


def extract_counts(cdp: CDP, category: str) -> dict:
    labels = COUNT_LABELS.get(category)
    if not labels:
        return {}
    text = cdp.js(_INNER_TEXT_JS) or ""
    lines = [ln.strip() for ln in text.splitlines()]
    found = {}
    for i, line in enumerate(lines):
        if line not in labels or line in found:
            continue
        for look in lines[i + 1 : i + 5]:
            if look in _NOISE_LINES or look == "":
                continue
            m = _COUNT_LINE_RE.match(look)
            if m:
                found[line] = int(m.group(1).replace(",", ""))
            break
    return found


def _fingerprint(cdp: CDP) -> tuple[str, str, str]:
    href = cdp.js("location.href") or ""
    text = (cdp.js(_INNER_TEXT_JS) or "")[:4000]
    # 페이지 변경 감지용 지문일 뿐 보안 용도 아님(bandit B324, 2026-09-29 확인).
    digest = hashlib.sha1(text.encode("utf-8", "ignore"), usedforsecurity=False).hexdigest()[:12]
    return href, digest, text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=float, default=1.5)
    args = ap.parse_args()

    cdp = CDP(port=9222)
    last_href, last_digest, last_text = _fingerprint(cdp)
    print(f"[watch:start] category={classify(last_href, last_text)} url={last_href}", flush=True)
    counts_reported_for = None  # SPA 리렌더가 늦게 끝나는 화면 대비, href당 1회만 카운트 보고

    try:
        while True:
            time.sleep(args.interval)
            try:
                href, digest, text = _fingerprint(cdp)
            except Exception as e:  # noqa: BLE001 - CDP 페이지 상태를 주기적으로 출력하는 읽기전용 관찰 도구 — 한 번의 fingerprint 조회 실패를 로그로 남기고 continue로 다음 루프 계속.
                print(f"[watch:error] {e}", flush=True)
                continue
            category = classify(href, text)
            if href != last_href:
                print(f"[watch:navigate] category={category} {last_href} -> {href}", flush=True)
                last_href, last_digest, last_text = href, digest, text
                counts_reported_for = None
            elif digest != last_digest:
                # 같은 화면 안에서의 텍스트 변화는 스피너/배너 깜빡임 등
                # 무해한 노이즈가 대부분이라(2026-08-23 실측) 이벤트로 보고하지
                # 않는다. digest는 카운트 재추출 판단용으로만 갱신한다.
                last_digest, last_text = digest, text

            # SPA 화면 전환/리렌더 타이밍이 들쭉날쭉해 navigate 시점 배지 텍스트가
            # 비어있을 수 있다(2026-08-23 실측) — href가 바뀌지 않는 한 계속 재시도.
            if counts_reported_for != href:
                counts = extract_counts(cdp, category)
                if counts:
                    kv = " ".join(f"{k}={v}" for k, v in counts.items())
                    print(f"[watch:counts] category={category} {kv}", flush=True)
                    counts_reported_for = href
    except KeyboardInterrupt:
        pass
    finally:
        cdp.close()


if __name__ == "__main__":
    main()
