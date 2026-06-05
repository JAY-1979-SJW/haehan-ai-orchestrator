"""로컬 CDP + AI 브라우저 에이전트.

사용자 PC의 로그인된 CDP 브라우저를 AI가 운전한다(관찰→결정→실행→반복).
서버 헤드리스가 아니라 '진짜 로그인된 로컬 브라우저'라 봇탐지/로그인 벽을 통과.

안전: 파괴적 동작(결제/구매/삭제/발송/제출/투찰/송금 등)은 실행 차단 → 승인 필요로 중단.
읽기·탐색·추출·검색은 자유.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from typing import Any

# 로그인 페이지 감지 (이 URL이면 로그인 필요 → 사용자에게 요청)
_LOGIN_RE = re.compile(r"nidlogin|/login|accounts\.|auth\.|/signin|/sso/|loginform|로그인", re.IGNORECASE)


def _is_login_page(url: str) -> bool:
    return bool(_LOGIN_RE.search(url or ""))


def _show_cdp_window() -> None:
    """CDP 크롬 창을 복원·앞으로 — 사용자가 직접 로그인하도록. win32 best-effort."""
    if sys.platform != "win32":
        return
    ps = (
        "$ErrorActionPreference='SilentlyContinue';"
        "Add-Type -Name U -Namespace W -MemberDefinition "
        '\'[DllImport("user32.dll")] public static extern bool ShowWindowAsync(System.IntPtr h,int n);'
        '[DllImport("user32.dll")] public static extern bool SetForegroundWindow(System.IntPtr h);\';'
        "Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | "
        "Where-Object { $_.CommandLine -like '*--remote-debugging-port=9222*' } | ForEach-Object { "
        "$p=Get-Process -Id $_.ProcessId -ErrorAction SilentlyContinue; "
        "if($p -and $p.MainWindowHandle -ne 0){ [W.U]::ShowWindowAsync($p.MainWindowHandle,9)|Out-Null;"
        "[W.U]::SetForegroundWindow($p.MainWindowHandle)|Out-Null } }"
    )
    try:
        subprocess.Popen(["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps])
    except Exception:
        pass


# 파괴적 동작 키워드 (클릭 대상 텍스트에 포함되면 차단)
_DESTRUCTIVE = re.compile(
    r"결제|구매|주문하기|입금|송금|이체|삭제|탈퇴|투찰|입찰|낙찰|발송|전송|보내기|"
    r"제출|등록완료|최종|승인|확정|저장하기|게시|발행|업로드|신청완료|환불|취소하기|"
    r"buy|pay|checkout|delete|remove|submit|send|publish|withdraw|confirm\s*payment",
    re.IGNORECASE,
)

# 관찰 JS — 보이는 상호작용 요소 목록 + 본문 일부
_OBSERVE_JS = r"""() => {
  const els = [];
  let idx = 0;
  const nodes = document.querySelectorAll(
    'a, button, input, textarea, select, [role=button], [role=link], [onclick]'
  );
  for (const n of nodes) {
    const rect = n.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) continue;
    if (rect.bottom < 0 || rect.top > (window.innerHeight + 1200)) continue;
    const tag = n.tagName.toLowerCase();
    const text = (n.innerText || n.value || n.getAttribute('placeholder') ||
                  n.getAttribute('aria-label') || n.getAttribute('title') || '').trim().slice(0, 70);
    n.setAttribute('data-agent-idx', String(idx));
    els.push({ idx, tag, type: n.getAttribute('type') || '', text, href: n.href || '' });
    idx++;
    if (idx >= 120) break;
  }
  return {
    url: location.href,
    title: document.title,
    elements: els,
    bodyText: (document.body.innerText || '').replace(/\s+/g, ' ').slice(0, 2500),
  };
}"""


def _observe(page) -> dict:
    try:
        return page.evaluate(_OBSERVE_JS)
    except Exception as e:
        return {"url": getattr(page, "url", ""), "title": "", "elements": [], "bodyText": f"(관찰 실패: {e})"}


def _wait_for_login(page, target_url: str | None, timeout: int = 100) -> bool:
    """사용자가 로그인할 때까지 폴링 대기. 로그인 페이지를 벗어나면(사이트 리다이렉트)
    원래 목표 URL로 이동해 작업을 재개할 수 있게 True 반환. 시간초과면 False.

    로그인 진행을 방해하지 않도록, 로그인 완료 전에는 페이지를 건드리지 않고 url만 관찰한다.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(3)
        try:
            cur = page.url or ""
        except Exception:
            cur = ""
        if cur and not _is_login_page(cur):
            # 로그인 완료 → 원래 목표 페이지로 이동해 작업 재개
            try:
                if target_url and target_url not in cur:
                    page.goto(target_url, wait_until="domcontentloaded", timeout=20000)
                    time.sleep(1.5)
            except Exception:
                pass
            return True
    return False


def _is_destructive(text: str) -> bool:
    return bool(_DESTRUCTIVE.search(text or ""))


def _decide(instruction: str, obs: dict, history: list[dict]) -> dict:
    """AI에게 현재 상태+지시를 주고 다음 동작 1개를 JSON으로 받는다."""
    from ai_orchestrator.openai_proxy_caller import call_openai_chat

    els = "\n".join(
        f"  [{e['idx']}] <{e['tag']}{('/' + e['type']) if e['type'] else ''}> {e['text'][:50]}"
        + (f"  → {e['href'][:45]}" if e.get("href") else "")
        for e in obs.get("elements", [])[:50]
    )
    hist = "\n".join(
        f"  {i + 1}. {h.get('action')}({h.get('index', h.get('url', h.get('text', '')))})"
        for i, h in enumerate(history[-8:])
    )
    prompt = (
        "당신은 로그인된 웹 브라우저를 운전하는 에이전트입니다. 사용자 지시를 달성하기 위해 "
        "다음 동작 1개만 JSON으로 출력하세요(설명·마크다운 금지).\n"
        '동작: {"action":"goto","url":"..."} | {"action":"click","index":N} | '
        '{"action":"type","index":N,"text":"..."} | {"action":"scroll","dir":"down|up"} | '
        '{"action":"extract"} | {"action":"done","result":"최종 답/요약"}\n'
        "규칙: 지시가 끝나면 done. 같은 동작 반복 금지. 결제/구매/삭제/발송 등 위험한 클릭은 하지 말고 done으로 보고.\n\n"
        f"[사용자 지시]\n{instruction}\n\n"
        f"[현재 페이지] {obs.get('title', '')[:80]} — {obs.get('url', '')}\n"
        f"[상호작용 요소]\n{els or '  (없음)'}\n\n"
        f"[본문 일부]\n{obs.get('bodyText', '')[:1200]}\n\n"
        f"[지금까지 한 동작]\n{hist or '  (없음)'}\n\n"
        "다음 동작 JSON:"
    )
    # 입력 한도(8000자) 안전 클램프
    if len(prompt) > 7500:
        prompt = prompt[:7500] + "\n다음 동작 JSON:"
    res = call_openai_chat(message=prompt, max_tokens=400)
    if not res.ok:
        return {"action": "done", "result": f"AI 결정 실패: {res.error_code}"}
    m = re.search(r"\{.*\}", res.text, re.S)
    if not m:
        return {"action": "done", "result": "동작 파싱 실패"}
    try:
        return json.loads(m.group(0))
    except Exception:
        return {"action": "done", "result": "동작 JSON 오류"}


def _element_text(obs: dict, index: Any) -> str:
    for e in obs.get("elements", []):
        if e["idx"] == index:
            return e.get("text", "")
    return ""


def _execute(page, decision: dict, obs: dict) -> str:
    action = decision.get("action")
    try:
        if action == "goto":
            page.goto(decision["url"], wait_until="domcontentloaded", timeout=30000)
            time.sleep(2)
            return f"이동: {decision['url']}"
        if action == "click":
            page.click(f'[data-agent-idx="{decision["index"]}"]', timeout=8000)
            time.sleep(1.5)
            return f"클릭: [{decision['index']}] {_element_text(obs, decision['index'])[:40]}"
        if action == "type":
            page.fill(f'[data-agent-idx="{decision["index"]}"]', decision.get("text", ""), timeout=8000)
            time.sleep(0.5)
            return f"입력: [{decision['index']}] '{decision.get('text', '')[:30]}'"
        if action == "scroll":
            dy = 800 if decision.get("dir") != "up" else -800
            page.evaluate(f"window.scrollBy(0, {dy})")
            time.sleep(0.8)
            return f"스크롤: {decision.get('dir', 'down')}"
        if action == "extract":
            return "추출(본문 갱신)"
    except Exception as e:
        return f"실행 오류: {str(e)[:80]}"
    return f"알 수 없는 동작: {action}"


def run_browser_task(page, instruction: str, start_url: str | None = None, max_steps: int = 12) -> dict:
    """AI가 로컬 CDP 브라우저를 운전해 지시를 수행. 동작 기록 + 결과 반환."""
    steps: list[dict] = []
    # 잘못된 시작 URL(http로 시작 안 함)은 무시 — 현재 페이지/지시로 진행.
    if start_url and not start_url.lower().startswith("http"):
        start_url = None
    if start_url:
        try:
            page.goto(start_url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(2)
        except Exception as e:
            return {"ok": False, "result": f"시작 URL 이동 실패: {e}", "steps": steps}

    login_waited = False  # 로그인 대기는 작업당 1회만 (무한 대기 방지)
    for _ in range(max(1, min(max_steps, 25))):
        obs = _observe(page)

        # 로그인 페이지면: 브라우저를 띄워 사용자 로그인을 유도하고, 완료될 때까지 대기 후
        # 그 자리에서 작업을 자동으로 이어간다(재입력 불필요). 시간초과면 사용자에게 요청.
        if _is_login_page(obs.get("url", "")):
            try:
                page.bring_to_front()
            except Exception:
                pass
            _show_cdp_window()
            if not login_waited and _wait_for_login(page, start_url, timeout=100):
                login_waited = True
                steps.append({"action": "logged_in", "note": "로그인 완료 — 작업 자동 계속"})
                continue  # 재관찰 → 로그인된 상태로 작업 진행
            steps.append({"action": "needs_login", "url": obs.get("url")})
            return {
                "ok": False,
                "needs_login": True,
                "result": "로그인이 필요합니다 — 화면에 뜬 브라우저에서 해당 사이트에 로그인해 주세요. "
                "로그인하면 작업이 자동으로 이어집니다(시간초과 시 다시 [실행]).",
                "login_url": obs.get("url"),
                "steps": steps,
            }

        decision = _decide(instruction, obs, steps)
        action = decision.get("action")

        if action == "done":
            steps.append({"action": "done", "result": decision.get("result", "")})
            return {"ok": True, "result": decision.get("result", ""), "steps": steps, "url": obs.get("url")}

        # 안전 게이트: 파괴적 클릭 차단
        if action == "click":
            tgt = _element_text(obs, decision.get("index"))
            if _is_destructive(tgt):
                steps.append(
                    {"action": "blocked", "target": tgt, "reason": "파괴적 동작(결제/삭제/발송 등) — 사용자 승인 필요"}
                )
                return {
                    "ok": False,
                    "blocked": True,
                    "result": f"위험 동작 차단: '{tgt[:40]}' — 직접 승인 후 진행하세요",
                    "steps": steps,
                    "url": obs.get("url"),
                }

        outcome = _execute(page, decision, obs)
        steps.append(
            {"action": action, "detail": {k: v for k, v in decision.items() if k != "action"}, "outcome": outcome}
        )

    return {"ok": True, "result": "최대 단계 도달 — 부분 수행", "steps": steps, "url": _observe(page).get("url")}
