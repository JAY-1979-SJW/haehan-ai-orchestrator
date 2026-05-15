#!/usr/bin/env python3
"""EUM 폼 필드 자동 분석.

WEBMAN381M00 (신규 등록)과 WEBMAN382M00 (철거)의 폼 구조를 분석하여
정확한 selector와 필드 정보를 추출합니다.

사용:
    python scripts/analyze_eum_forms.py
"""
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


def analyze_form_fields(page, url: str, form_name: str) -> dict:
    """페이지의 폼 필드를 분석."""
    log.info(f"[분석] {form_name} 폼 분석 시작")

    page.goto(url, wait_until="networkidle")
    import time
    time.sleep(2)

    # 모든 입력 필드 추출
    result = {
        "page": form_name,
        "url": url,
        "fields": [],
        "buttons": [],
    }

    # 입력 필드 (input, select, textarea)
    fields_script = """
    () => {
        const fields = [];

        // input 필드
        document.querySelectorAll('input').forEach(el => {
            if (el.type !== 'hidden') {
                fields.push({
                    type: el.type,
                    name: el.name,
                    id: el.id,
                    placeholder: el.placeholder,
                    value: el.value,
                    selector: el.id ? `#${el.id}` :
                             el.name ? `input[name="${el.name}"]` :
                             null,
                });
            }
        });

        // select 필드
        document.querySelectorAll('select').forEach(el => {
            fields.push({
                type: 'select',
                name: el.name,
                id: el.id,
                options: Array.from(el.options).map(o => o.text),
                selector: el.id ? `#${el.id}` :
                         el.name ? `select[name="${el.name}"]` :
                         null,
            });
        });

        // textarea 필드
        document.querySelectorAll('textarea').forEach(el => {
            fields.push({
                type: 'textarea',
                name: el.name,
                id: el.id,
                placeholder: el.placeholder,
                selector: el.id ? `#${el.id}` :
                         el.name ? `textarea[name="${el.name}"]` :
                         null,
            });
        });

        return fields;
    }
    """

    # 버튼 추출
    buttons_script = """
    () => {
        const buttons = [];

        document.querySelectorAll('button, input[type="submit"], input[type="button"]').forEach(el => {
            if (el.offsetParent !== null) {  // 보이는 요소만
                buttons.push({
                    type: el.type,
                    text: el.textContent?.trim() || el.value,
                    id: el.id,
                    class: el.className,
                    selector: el.id ? `#${el.id}` :
                             el.type === 'submit' ? 'button[type="submit"]' :
                             `button:has-text('${el.textContent?.trim() || el.value}')`,
                });
            }
        });

        return buttons;
    }
    """

    try:
        fields = page.evaluate(fields_script)
        result["fields"] = fields
        log.info(f"[분석] {form_name}: {len(fields)}개 필드 발견")

        buttons = page.evaluate(buttons_script)
        result["buttons"] = buttons
        log.info(f"[분석] {form_name}: {len(buttons)}개 버튼 발견")

    except Exception as e:
        log.error(f"[분석] 폼 분석 실패: {e}")

    return result


def main():
    """메인 함수."""
    import json

    print("=" * 80)
    print("  EUM 폼 필드 자동 분석")
    print("=" * 80)

    # 페이지 접근
    page = get_page()
    ensure_logged_in(page)

    EUM_BASE = "https://eum.cw.or.kr"

    # 분석 대상
    forms = [
        (f"{EUM_BASE}/web/man/WEBMAN381M00", "WEBMAN381M00_신규등록"),
        (f"{EUM_BASE}/web/man/WEBMAN382M00", "WEBMAN382M00_철거"),
    ]

    results = {}
    for url, name in forms:
        print(f"\n[{name}] 분석 중...")
        result = analyze_form_fields(page, url, name)
        results[name] = result

        # 화면에 출력
        print(f"\n  필드 ({len(result['fields'])}개):")
        for i, field in enumerate(result["fields"], 1):
            field_type = field.get("type", "unknown")
            name_str = field.get("name", field.get("id", "unnamed"))
            selector = field.get("selector", "")
            print(f"    {i}. [{field_type}] {name_str}")
            if selector:
                print(f"       selector: {selector}")

        print(f"\n  버튼 ({len(result['buttons'])}개):")
        for i, btn in enumerate(result["buttons"], 1):
            text = btn.get("text", "")
            selector = btn.get("selector", "")
            print(f"    {i}. {text}")
            if selector:
                print(f"       selector: {selector}")

    # 결과 저장
    output_file = ROOT / "data" / "form_analysis.json"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"\n✓ 분석 결과 저장: {output_file}")
    print("=" * 80)


if __name__ == "__main__":
    main()
