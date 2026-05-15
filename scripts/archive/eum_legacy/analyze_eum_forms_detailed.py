#!/usr/bin/env python3
"""EUM 폼 구조 상세 분석."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.logger import get_logger
from scripts.web_connector import get_page
from scripts.eum.auth import ensure_logged_in

log = get_logger(__name__)


def analyze_page_structure(page, url: str, name: str) -> dict:
    """페이지 구조 상세 분석."""
    log.info(f"[상세분석] {name} 분석 중")

    page.goto(url, wait_until="networkidle")
    import time
    time.sleep(2)

    result = {
        "page": name,
        "url": url,
        "html_structure": "",
        "forms": [],
        "iframes": [],
    }

    # 1. form 요소 찾기
    try:
        forms_script = """
        () => {
            const forms = [];
            document.querySelectorAll('form').forEach((form, idx) => {
                const inputs = form.querySelectorAll('input, select, textarea');
                forms.push({
                    index: idx,
                    id: form.id,
                    name: form.name,
                    method: form.method,
                    action: form.action,
                    inputs_count: inputs.length,
                });
            });
            return forms;
        }
        """
        forms = page.evaluate(forms_script)
        result["forms"] = forms
        log.info(f"[상세분석] {len(forms)}개 form 발견")
    except Exception as e:
        log.warning(f"[상세분석] form 분석 실패: {e}")

    # 2. iframe 찾기
    try:
        iframes_script = """
        () => {
            const iframes = [];
            document.querySelectorAll('iframe').forEach((iframe, idx) => {
                iframes.push({
                    index: idx,
                    id: iframe.id,
                    src: iframe.src,
                    name: iframe.name,
                });
            });
            return iframes;
        }
        """
        iframes = page.evaluate(iframes_script)
        result["iframes"] = iframes
        log.info(f"[상세분석] {len(iframes)}개 iframe 발견")
    except Exception as e:
        log.warning(f"[상세분석] iframe 분석 실패: {e}")

    # 3. div 기반 폼(Angular, React 등) 찾기
    try:
        divform_script = """
        () => {
            const divForms = [];

            // 특정 클래스 패턴 찾기
            const patterns = ['form', 'modal', 'dialog', 'panel', 'container', 'content'];

            patterns.forEach(pattern => {
                const elements = document.querySelectorAll(`[class*="${pattern}"]`);
                elements.forEach(el => {
                    const inputs = el.querySelectorAll('input, select, textarea, button');
                    if (inputs.length > 0 && el.offsetHeight > 100) {
                        divForms.push({
                            class: el.className,
                            id: el.id,
                            inputs: inputs.length,
                            visible: el.offsetParent !== null,
                        });
                    }
                });
            });

            return divForms.slice(0, 10);  // 최대 10개
        }
        """
        divforms = page.evaluate(divform_script)
        result["div_forms"] = divforms
        log.info(f"[상세분석] {len(divforms)}개 div 기반 폼 발견")
    except Exception as e:
        log.warning(f"[상세분석] div 폼 분석 실패: {e}")

    # 4. 페이지 HTML 일부 출력 (디버그용)
    try:
        body_html = page.evaluate("() => document.body.innerHTML.substring(0, 2000)")
        result["html_sample"] = body_html
    except:
        pass

    return result


def main():
    """메인 함수."""
    print("=" * 80)
    print("  EUM 폼 구조 상세 분석")
    print("=" * 80)

    page = get_page()
    ensure_logged_in(page)

    EUM_BASE = "https://eum.cw.or.kr"

    forms = [
        (f"{EUM_BASE}/web/man/WEBMAN381M00", "WEBMAN381M00_신규등록"),
        (f"{EUM_BASE}/web/man/WEBMAN382M00", "WEBMAN382M00_철거"),
    ]

    results = {}
    for url, name in forms:
        print(f"\n[{name}]")
        result = analyze_page_structure(page, url, name)
        results[name] = result

        print(f"  Form 요소: {len(result.get('forms', []))}개")
        for form in result.get('forms', []):
            print(f"    - id={form['id']}, method={form['method']}, inputs={form['inputs_count']}")

        print(f"  iFrame: {len(result.get('iframes', []))}개")
        for iframe in result.get('iframes', []):
            print(f"    - id={iframe['id']}, src={iframe['src']}")

        print(f"  Div 기반 폼: {len(result.get('div_forms', []))}개")
        for divform in result.get('div_forms', [])[:5]:
            print(f"    - class={divform['class']}, inputs={divform['inputs']}")

    # 결과 저장
    output_file = ROOT / "data" / "form_structure_detailed.json"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"\n✓ 상세 분석 결과: {output_file}")
    print("=" * 80)


if __name__ == "__main__":
    main()
