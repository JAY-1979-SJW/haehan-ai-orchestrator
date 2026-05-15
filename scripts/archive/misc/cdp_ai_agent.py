"""CDP AI 에이전트 — DOM/접근성 트리 기반 자율 브라우저 조작.

스크린샷 없이 접근성 트리(Accessibility Tree)와 페이지 텍스트를 읽어
Claude Haiku가 다음 액션을 JSON으로 결정 → CDP로 실행하는 ReAct 루프.

흐름:
  1. 현재 페이지 접근성 트리 + 텍스트 추출
  2. Claude Haiku에 작업 + 현재 상태 전달
  3. AI가 JSON 액션 반환 (click/type/press/navigate/upload/done/fail)
  4. 액션 실행 후 1로 반복
  5. done/fail 또는 max_steps 도달 시 종료
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


# ── 페이지 상태 추출 ───────────────────────────────────────────

def _accessibility_tree_text(tree: Any, depth: int = 0, max_depth: int = 8) -> str:
    """접근성 트리를 읽기 쉬운 텍스트로 직렬화 (토큰 절약)."""
    if not tree or depth > max_depth:
        return ""
    indent = "  " * depth
    role = tree.get("role", "")
    name = tree.get("name", "")
    value = tree.get("value", "")
    desc = tree.get("description", "")

    parts = [role]
    if name:
        parts.append(f'"{name}"')
    if value:
        parts.append(f'= "{value}"')
    if desc and desc != name:
        parts.append(f'({desc})')

    line = indent + " ".join(parts)
    children_text = ""
    for child in tree.get("children", []) or []:
        children_text += _accessibility_tree_text(child, depth + 1, max_depth)

    return (line + "\n" if line.strip() else "") + children_text


def _simplified_html(page: Any, max_chars: int = 3000) -> str:
    """script/style 제거 후 의미있는 텍스트만 추출."""
    try:
        return page.evaluate(r"""() => {
            const clone = document.body.cloneNode(true);
            clone.querySelectorAll('script,style,noscript,svg,iframe,canvas').forEach(e => e.remove());
            const text = clone.innerText || clone.textContent || "";
            // 연속 공백/줄바꿈 정리
            return text.replace(/\s{3,}/g, "\n").trim();
        }""") or ""
    except Exception:
        return ""


def _interactive_elements(page: Any) -> list[dict]:
    """클릭/입력 가능한 요소 목록 추출 (selector + 레이블)."""
    try:
        return page.evaluate(r"""() => {
            const elems = [];
            const seen = new Set();
            const query = 'button, input, textarea, select, a[href], [role="button"], ' +
                          '[role="menuitem"], [role="option"], [contenteditable="true"]';
            for (const el of document.querySelectorAll(query)) {
                const label = (
                    el.getAttribute("aria-label") ||
                    el.getAttribute("placeholder") ||
                    el.getAttribute("title") ||
                    el.textContent?.trim() ||
                    el.value ||
                    ""
                ).slice(0, 80).trim();
                if (!label || seen.has(label)) continue;
                seen.add(label);

                // 간단한 고유 selector 생성
                let sel = el.tagName.toLowerCase();
                if (el.id) sel = "#" + el.id;
                else if (el.getAttribute("aria-label"))
                    sel = `[aria-label="${el.getAttribute("aria-label").replace(/"/g, "'")}"]`;
                else if (el.getAttribute("name"))
                    sel = `[name="${el.getAttribute("name")}"]`;
                else if (el.getAttribute("type"))
                    sel = `${sel}[type="${el.getAttribute("type")}"]`;

                elems.push({ label, selector: sel, tag: el.tagName.toLowerCase() });
                if (elems.length >= 40) break;
            }
            return elems;
        }""") or []
    except Exception:
        return []


def get_page_snapshot(page: Any) -> dict:
    """AI에게 전달할 현재 페이지 상태 딕셔너리."""
    url = page.url
    try:
        title = page.title()
    except Exception:
        title = ""

    # 접근성 트리 (interesting_only로 노이즈 제거)
    try:
        tree = page.accessibility.snapshot(interesting_only=True)
        tree_text = _accessibility_tree_text(tree)[:4000]
    except Exception:
        tree_text = ""

    # 상호작용 요소 목록
    interactive = _interactive_elements(page)

    # 텍스트 폴백 (트리가 비어있을 때)
    page_text = _simplified_html(page, 2000) if not tree_text else ""

    # Drive 파일 목록 명시 추출 (AI에게 aria-label 정보 직접 제공)
    drive_files: list[str] = []
    if "drive.google.com" in url:
        try:
            drive_files = page.evaluate(r"""() => {
                const labels = [];
                for (const el of document.querySelectorAll('[aria-label][role="gridcell"], [aria-label][data-id]')) {
                    const label = el.getAttribute("aria-label") || "";
                    const cleaned = label.replace(/\s*(More info|추가 정보).*$/i, "").trim();
                    if (cleaned.length > 2 && cleaned.length < 150) labels.push(cleaned);
                }
                return [...new Set(labels)].slice(0, 30);
            }""") or []
        except Exception:
            pass

    return {
        "url": url,
        "title": title,
        "accessibility_tree": tree_text,
        "interactive_elements": interactive,
        "page_text": page_text,
        "drive_files": drive_files,  # Drive 파일 목록 (선택자 생성용)
    }


# ── AI 판단 ────────────────────────────────────────────────────

_SYSTEM_PROMPT = """당신은 웹 브라우저를 조작하는 AI 에이전트입니다.
현재 페이지 상태(접근성 트리, 상호작용 요소)를 보고 주어진 작업의 다음 단계를 JSON으로 반환합니다.

반환 형식 (JSON만, 다른 텍스트 없음):
{
  "action": "click|type|press|navigate|upload|right_click|scroll|done|fail",
  "selector": "CSS 선택자 (click/type/right_click/upload 시 필수)",
  "value": "텍스트 또는 URL 또는 키이름 (type/press/navigate 시 필수)",
  "file_path": "절대 경로 (upload 시 필수)",
  "reason": "이 액션을 선택한 이유 한 줄"
}

액션 설명:
- click: selector 요소 클릭
- right_click: selector 요소 우클릭 (컨텍스트 메뉴 열기)
- type: selector 요소에 value 텍스트 입력 후 자동으로 Enter
- press: 키보드 키 입력 (value = "Enter", "Escape", "F2", "Control+s" 등)
- navigate: value URL로 직접 이동 (가장 빠른 방법, URL을 알면 항상 우선 사용)
- upload: selector input[type=file]에 file_path 파일 업로드
- scroll: value = "down"|"up"|"top"|"bottom"
- done: 작업 완료 (결과 요약을 reason에 작성)
- fail: 작업 불가 (reason에 이유)

핵심 규칙:
1. URL을 알고 있으면 navigate를 먼저 사용 (클릭 탐색보다 빠름)
   - Google Drive 내 드라이브: https://drive.google.com/drive/my-drive
   - Google Drive 검색: https://drive.google.com/drive/search?q=검색어
   - Gmail: https://mail.google.com
2. 이전 스텝과 URL이 같고 동일 액션을 반복하면 다른 방법 시도
3. 작업이 여러 단계면 한 번에 한 단계만 반환

Google Drive 파일 조작 패턴:
- 파일 이름 변경: 파일 우클릭 → 컨텍스트 메뉴에서 "이름 바꾸기" 클릭 → 이름 입력 → Enter
  * 파일 selector 예시: [aria-label*="파일명"]
  * "이름 바꾸기" 메뉴 selector: [aria-label*="이름 바꾸기"], [data-action*="rename"]
- 검색: [aria-label*='드라이브에서 검색'] 클릭 → type으로 검색어 입력 (자동 Enter)

페이지 정보 수집:
- 접근성 트리 또는 page_text에서 정보를 읽고 done으로 결과 요약
- JSON만 반환, 마크다운 코드블록 없음
"""


def _build_client() -> tuple[Any, str]:
    """환경변수에서 AI API 클라이언트와 모델명 반환.

    우선순위:
      1. OPENAI_API_KEY  → openai.OpenAI()  (gpt-4o-mini)
      2. AI_AGENT 환경변수 = "openai:<model>" 등 명시 설정
    """
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")

    openai_key  = os.environ.get("OPENAI_API_KEY", "")
    # CDP_AI_PROVIDER: "openai:gpt-4o-mini" 형식으로 명시 오버라이드
    cdp_ai      = os.environ.get("CDP_AI_PROVIDER", "")

    if cdp_ai:
        provider, _, model = cdp_ai.partition(":")
        model = model or "gpt-4o-mini"
        if provider.lower() == "openai":
            from openai import OpenAI
            return OpenAI(api_key=openai_key), model
        raise RuntimeError(f"CDP_AI_PROVIDER 프로바이더 미지원: {provider}")

    if openai_key:
        from openai import OpenAI
        return OpenAI(api_key=openai_key), "gpt-4o-mini"

    raise RuntimeError(
        "AI API 키가 없습니다. .env에 OPENAI_API_KEY 또는 AI_AGENT=openai:<model> 설정하세요."
    )


def ai_decide(client: Any, model: str, task: str, snapshot: dict, history: list[dict]) -> dict:
    """AI에게 다음 액션 결정 요청 (OpenAI 호환 인터페이스)."""
    messages: list[dict] = [{"role": "system", "content": _SYSTEM_PROMPT}]

    # 히스토리 (최근 4쌍)
    for h in history[-4:]:
        messages.append({"role": "user",      "content": h["user"]})
        messages.append({"role": "assistant",  "content": h["assistant"]})

    # 현재 상태
    interactive_text = "\n".join(
        f"  {e['selector']} — {e['label']}" for e in snapshot["interactive_elements"][:25]
    ) or "  (없음)"

    current = f"""작업: {task}

현재 URL: {snapshot['url']}
페이지 제목: {snapshot['title']}

── 접근성 트리 ──
{snapshot['accessibility_tree'] or '(비어있음)'}

── 상호작용 요소 ──
{interactive_text}

{f"── 페이지 텍스트 ──{chr(10)}{snapshot['page_text'][:1500]}" if snapshot['page_text'] else ""}
"""
    messages.append({"role": "user", "content": current})

    response = client.chat.completions.create(
        model=model,
        max_tokens=400,
        messages=messages,
    )

    raw = response.choices[0].message.content.strip()
    # 코드블록 제거
    raw = re.sub(r"^```[a-z]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw)

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            return json.loads(m.group(0))
        raise ValueError(f"AI 응답을 JSON으로 파싱 실패: {raw[:200]}")


# ── 액션 실행 ──────────────────────────────────────────────────

def execute_action(page: Any, action: dict) -> str:
    """AI가 결정한 액션을 Playwright로 실행."""
    act      = action.get("action", "")
    selector = action.get("selector", "")
    value    = action.get("value", "")
    file_path = action.get("file_path", "")

    if act == "click":
        _click(page, selector)
        page.wait_for_timeout(1200)
        return f"클릭: {selector}"

    elif act == "right_click":
        el = _find_element(page, selector)
        el.click(button="right")
        page.wait_for_timeout(800)
        return f"우클릭: {selector}"

    elif act == "type":
        el = _find_element(page, selector)
        el.fill(value)
        page.wait_for_timeout(500)
        page.keyboard.press("Enter")
        page.wait_for_timeout(1500)
        return f"입력+Enter: {selector} ← '{value}'"

    elif act == "press":
        page.keyboard.press(value)
        page.wait_for_timeout(800)
        return f"키: {value}"

    elif act == "navigate":
        page.goto(value, timeout=30000, wait_until="domcontentloaded")
        page.wait_for_timeout(4000)  # SPA 렌더링 대기
        return f"이동: {value}"

    elif act == "upload":
        # input[type=file]이 숨겨진 경우 강제 노출
        file_input = page.query_selector('input[type="file"]')
        if not file_input:
            file_input = _find_element(page, selector)
        if not file_input:
            raise RuntimeError("파일 입력 요소를 찾을 수 없음")
        file_input.set_input_files(file_path)
        page.wait_for_timeout(2000)
        return f"업로드: {file_path}"

    elif act == "scroll":
        direction = value.lower() if value else "down"
        if direction == "down":
            page.mouse.wheel(0, 600)
        elif direction == "up":
            page.mouse.wheel(0, -600)
        elif direction == "bottom":
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        elif direction == "top":
            page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_timeout(500)
        return f"스크롤: {direction}"

    else:
        raise ValueError(f"알 수 없는 액션: {act}")


def _find_element(page: Any, selector: str) -> Any:
    """selector로 요소 탐색 — 없으면 텍스트 기반 폴백."""
    el = page.query_selector(selector)
    if el:
        return el
    # aria-label 값으로 텍스트 검색
    label = re.search(r'aria-label=["\']([^"\']+)["\']', selector)
    if label:
        el = page.get_by_label(label.group(1)).first
        if el:
            return el
    # 텍스트로 검색
    el = page.get_by_text(selector, exact=False).first
    if el:
        return el
    raise RuntimeError(f"요소를 찾을 수 없음: {selector}")


def _click(page: Any, selector: str) -> None:
    """클릭 — selector 우선, 없으면 텍스트/레이블 폴백."""
    try:
        el = _find_element(page, selector)
        el.click()
        return
    except Exception:
        pass
    # 마지막 시도: page.click with force
    try:
        page.click(selector, timeout=3000)
    except Exception as e:
        raise RuntimeError(f"클릭 실패 ({selector}): {e}")


# ── 메인 루프 ──────────────────────────────────────────────────

def run_ai_task(page: Any, task: str, max_steps: int = 12) -> None:
    """AI 브라우저 에이전트 메인 실행 루프."""
    try:
        client, model = _build_client()
    except Exception as e:
        print(f"  [오류] AI 클라이언트 초기화 실패: {e}")
        return

    print(f"\n[AI 에이전트] 작업: {task}")
    print(f"  모델: {model}  최대 스텝: {max_steps}\n")

    history: list[dict] = []
    prev_url = ""
    same_url_count = 0

    for step in range(1, max_steps + 1):
        print(f"  ── Step {step}/{max_steps} ─────────────────────")

        # 1. 현재 상태 수집
        try:
            snapshot = get_page_snapshot(page)
        except Exception as e:
            print(f"  [오류] 페이지 상태 수집 실패: {e}")
            break

        print(f"  URL   : {snapshot['url']}")
        print(f"  제목  : {snapshot['title']}")

        # URL 변화 추적 — 반복 감지
        if snapshot['url'] == prev_url:
            same_url_count += 1
        else:
            same_url_count = 0
        prev_url = snapshot['url']

        # 같은 URL에서 3번 이상 같은 상태면 히스토리에 경고 추가
        stuck_feedback = ""
        if same_url_count >= 2:
            stuck_feedback = f"\n\n[시스템] URL이 {same_url_count+1}번째 동일합니다 ({snapshot['url']}). 이전 액션이 페이지를 변경하지 못했습니다. navigate 액션으로 URL을 직접 입력하거나 다른 방법을 시도하세요."

        # 2. AI 판단
        try:
            snap_with_feedback = dict(snapshot)
            if stuck_feedback:
                snap_with_feedback['page_text'] = stuck_feedback + "\n" + (snapshot.get('page_text') or '')
            action = ai_decide(client, model, task, snap_with_feedback, history)
        except Exception as e:
            print(f"  [오류] AI 판단 실패: {e}")
            break

        act    = action.get("action", "?")
        reason = action.get("reason", "")
        print(f"  AI 결정: {act}  —  {reason}")

        # 3. 종료 조건
        if act == "done":
            print(f"\n  ✓ 작업 완료")
            if reason:
                print(f"  결과: {reason}")
            break
        elif act == "fail":
            print(f"\n  ✗ 작업 실패: {reason}")
            break

        # 4. 액션 실행
        try:
            result = execute_action(page, action)
            print(f"  실행  : {result}")
        except Exception as e:
            print(f"  [오류] 액션 실행 실패: {e}")
            history.append({
                "user": f"Step {step} (URL: {snapshot['url']})",
                "assistant": json.dumps(action, ensure_ascii=False),
            })
            history.append({
                "user": f"오류: {e}. selector가 잘못되었을 수 있습니다. navigate나 다른 selector를 사용하세요.",
                "assistant": '{"action":"fail","reason":"오류 피드백"}',
            })
            continue

        # 5. 히스토리 기록
        history.append({
            "user": f"Step {step} — URL: {snapshot['url']}, 제목: {snapshot['title']}",
            "assistant": json.dumps(action, ensure_ascii=False),
        })

    else:
        print(f"\n  [경고] 최대 스텝({max_steps}) 도달 — 작업 미완료일 수 있음")

    print(f"\n  완료 스텝: {min(step, max_steps)}")
