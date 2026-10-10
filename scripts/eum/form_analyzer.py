"""WEBMAN381M00(신규등록) + WEBMAN382M00(철거) 폼 구조 분석."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from scripts.common.logger import get_logger  # noqa: E402

log = get_logger(__name__)

EUM_BASE = "https://eum.cw.or.kr"

# ── JavaScript 폼 분석 코드 ────────────────────────────────────────────
_JS_FORM_EXTRACT = """
() => {
    const result = {
        url: window.location.href,
        title: document.title,
        forms: [],
        inputs: [],
        selects: [],
        buttons: [],
        textareas: [],
    };

    // 1. 모든 폼 정보
    document.querySelectorAll('form').forEach((form, i) => {
        result.forms.push({
            id: form.id || `form${i}`,
            name: form.name || '',
            action: form.action || '',
            method: form.method || 'GET',
            fields: [],
        });
    });

    // 2. 입력 필드들
    document.querySelectorAll('input').forEach((inp) => {
        result.inputs.push({
            id: inp.id || '',
            name: inp.name || '',
            type: inp.type || 'text',
            value: inp.value || '',
            placeholder: inp.placeholder || '',
            required: inp.required || false,
            disabled: inp.disabled || false,
            label: document.querySelector(`label[for="${inp.id}"]`)?.innerText || '',
        });
    });

    // 3. Select 선택박스
    document.querySelectorAll('select').forEach((sel) => {
        result.selects.push({
            id: sel.id || '',
            name: sel.name || '',
            required: sel.required || false,
            disabled: sel.disabled || false,
            options: Array.from(sel.options).map(opt => ({
                value: opt.value,
                text: opt.innerText.trim(),
            })),
            label: document.querySelector(`label[for="${sel.id}"]`)?.innerText || '',
        });
    });

    // 4. 버튼들
    document.querySelectorAll('button, input[type="button"], input[type="submit"]').forEach((btn) => {
        result.buttons.push({
            id: btn.id || '',
            text: btn.innerText?.trim() || btn.value || '',
            type: btn.type || '',
            name: btn.name || '',
            onclick: btn.onclick?.toString() || '',
            disabled: btn.disabled || false,
        });
    });

    // 5. 텍스트 영역
    document.querySelectorAll('textarea').forEach((ta) => {
        result.textareas.push({
            id: ta.id || '',
            name: ta.name || '',
            required: ta.required || false,
            disabled: ta.disabled || false,
            placeholder: ta.placeholder || '',
            label: document.querySelector(`label[for="${ta.id}"]`)?.innerText || '',
        });
    });

    return result;
}
"""


def analyze_page(url: str) -> dict[str, Any]:
    """페이지의 폼 구조를 분석."""
    log.info(f"폼 분석 시작: {url}")

    try:
        # CDP 클라이언트 사용 (기존 세션 재사용)
        # eval_js/goto_url 실제 없음(2026-09-29 defect_index #39 확인) — EUM 관련 작업은
        # 사용자 지시(#13)로 보류 중. 바로 아래 except Exception 이 안전하게 {"error":...}
        # 를 반환해 크래시하지 않음(읽기전용 폼 분석, 쓰기·제출 없음). (주의: 설명 줄이
        # "# type:"로 시작하면 mypy 가 독립된 type-comment 로 잘못 해석해 구문오류를 내므로
        # — defect_index — 절대 "# type:"으로 문장을 시작하지 않는다.)
        from scripts.browser.cdp_client import eval_js, goto_url  # type: ignore[attr-defined]

        goto_url(url)
        time.sleep(1)

        # 폼 추출
        form_data = eval_js(_JS_FORM_EXTRACT)
        form_data["extracted_at"] = str(__import__("datetime").datetime.now())
        return form_data
    except Exception as e:  # noqa: BLE001 - EUM 폼 필드 추출 실패를 로그로 남기고 에러 딕셔너리 반환 - 읽기전용 폼 분석, 쓰기·제출 동작 없음
        log.error(f"폼 추출 실패: {e}")
        return {"error": str(e), "url": url}


def main() -> None:
    """두 페이지의 폼 구조 분석."""
    print("\n" + "=" * 70)
    print("  EUM 폼 분석 (WEBMAN381M00 + WEBMAN382M00)")
    print("=" * 70)

    pages = {
        "WEBMAN381M00": "https://eum.cw.or.kr/web/man/WEBMAN381M00",
        "WEBMAN382M00": "https://eum.cw.or.kr/web/man/WEBMAN382M00",
        "WEBMAN383M00": "https://eum.cw.or.kr/web/man/WEBMAN383M00",
    }

    results = {}
    for name, url in pages.items():
        print(f"\n[분석 중] {name}...")
        result = analyze_page(url)
        results[name] = result

        # 요약 출력
        if "error" not in result:
            print(f"  ✓ 폼: {len(result['forms'])}개")
            print(f"  ✓ 입력: {len(result['inputs'])}개")
            print(f"  ✓ Select: {len(result['selects'])}개")
            print(f"  ✓ 버튼: {len(result['buttons'])}개")
            print(f"  ✓ TextArea: {len(result['textareas'])}개")
        else:
            print(f"  ✗ 오류: {result['error']}")

    # 결과 저장
    output_file = ROOT / "data" / "form_analysis.json"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n" + "=" * 70)
    print(f"📋 분석 결과: {output_file}")
    print("=" * 70)


if __name__ == "__main__":
    main()
