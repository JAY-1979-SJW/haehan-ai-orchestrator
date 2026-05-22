"""신규 Desktop Shell — 서버 사이드 HTML 생성기 (Phase 2).

실시간 API 값을 서버에서 수집해 단일 HTML 페이지로 렌더링한다.
클라이언트 JS는 새로고침 버튼만 제공 (실행 버튼 없음).
"""
from __future__ import annotations

import json
import time
import urllib.request
import urllib.error
from typing import Any

from .api import url, ENDPOINTS


def _get(key: str, timeout: int = 3) -> dict[str, Any]:
    try:
        req = urllib.request.urlopen(url(key), timeout=timeout)
        return json.loads(req.read())
    except Exception as e:
        return {"ok": False, "error": str(e), "_unreachable": True}


def _safe(val: Any, fallback: str = "—") -> str:
    if val is None or val == "":
        return fallback
    return str(val)


def _bool_badge(val: bool, true_label: str = "정상", false_label: str = "미연결") -> str:
    color = "#16a34a" if val else "#dc2626"
    label = true_label if val else false_label
    return f'<span style="color:{color};font-weight:600">{label}</span>'


def _render(health: dict, agent: dict, la_health: dict, preflight: dict,
            whoami: dict, logs_data: dict) -> str:
    """수집된 데이터 딕셔너리로 HTML을 렌더링한다 (HTTP 호출 없음)."""
    ts = int(time.time())

    server_alive     = health.get("ok") and not health.get("_unreachable")
    server_connected = agent.get("server_connected", False)
    agent_id         = agent.get("agent_id", "")
    la_available     = la_health.get("available", False)
    can_run          = preflight.get("can_run", False)
    user_message     = preflight.get("user_message", "")
    next_actions     = preflight.get("next_actions", [])
    warnings         = preflight.get("warnings", [])
    role             = whoami.get("role", "unknown")
    log_lines        = logs_data.get("lines", [])[-15:]

    # preflight provider 상세
    providers = preflight.get("providers", {})
    blocking  = preflight.get("blocking_reasons", [])

    def _rows(items: list[str]) -> str:
        return "".join(f"<li>{item}</li>" for item in items)

    provider_html = ""
    if providers:
        rows = "".join(
            f"<tr><td>{k}</td><td>{'✅' if v else '❌'}</td></tr>"
            for k, v in providers.items()
        )
        provider_html = f"""
        <table class="tbl">
          <thead><tr><th>Provider</th><th>상태</th></tr></thead>
          <tbody>{rows}</tbody>
        </table>"""

    log_html = ""
    if log_lines:
        lines_html = "".join(
            f'<div class="log-line {"log-err" if "ERROR" in l or "FAIL" in l else "log-warn" if "WARN" in l else ""}">{l}</div>'
            for l in log_lines
        )
        log_html = f'<div class="log-box">{lines_html}</div>'
    else:
        log_html = '<p class="muted">로그 없음</p>'

    html = f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Haehan AI Desktop — 신규 Shell</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: 'Segoe UI', sans-serif; background: #f4f4f5; color: #18181b; font-size: 14px; }}
    header {{ background: #18181b; color: #fff; padding: 16px 32px; display: flex; align-items: center; gap: 16px; }}
    header h1 {{ font-size: 18px; font-weight: 700; letter-spacing: -0.5px; }}
    header .badge {{ font-size: 10px; background: #f97316; color: #fff; padding: 2px 8px; border-radius: 99px; font-weight: 700; }}
    .container {{ max-width: 900px; margin: 0 auto; padding: 24px 16px; }}
    .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 16px; }}
    .card {{ background: #fff; border: 1px solid #e4e4e7; border-radius: 10px; padding: 18px 20px; }}
    .card h2 {{ font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; color: #71717a; margin-bottom: 12px; }}
    .row {{ display: flex; justify-content: space-between; align-items: center; padding: 6px 0; border-bottom: 1px solid #f4f4f5; }}
    .row:last-child {{ border-bottom: none; }}
    .label {{ color: #52525b; font-size: 12px; }}
    .value {{ font-size: 13px; font-weight: 500; }}
    .mono {{ font-family: monospace; font-size: 11px; }}
    .muted {{ color: #a1a1aa; font-size: 12px; }}
    .alert {{ background: #fff7ed; border: 1px solid #fed7aa; border-radius: 8px; padding: 12px 16px; margin-bottom: 12px; }}
    .alert.info {{ background: #eff6ff; border-color: #bfdbfe; }}
    .alert p {{ font-size: 13px; color: #c2410c; }}
    .alert.info p {{ color: #1d4ed8; }}
    ul.actions {{ margin: 8px 0 0 16px; font-size: 12px; color: #7c3aed; }}
    .tbl {{ width: 100%; border-collapse: collapse; font-size: 12px; margin-top: 8px; }}
    .tbl th {{ text-align: left; color: #71717a; padding: 4px 8px; border-bottom: 1px solid #e4e4e7; }}
    .tbl td {{ padding: 4px 8px; border-bottom: 1px solid #f4f4f5; }}
    .log-box {{ font-family: monospace; font-size: 11px; background: #18181b; color: #a1a1aa;
                border-radius: 8px; padding: 12px 16px; max-height: 280px; overflow-y: auto; }}
    .log-line {{ padding: 1px 0; }}
    .log-err {{ color: #f87171; }}
    .log-warn {{ color: #fbbf24; }}
    .btn-refresh {{ background: #f97316; color: #fff; border: none; border-radius: 8px;
                    padding: 8px 20px; font-size: 13px; font-weight: 600; cursor: pointer; }}
    .btn-refresh:hover {{ background: #ea580c; }}
    .btn-disabled {{ background: #d4d4d8; color: #71717a; border: none; border-radius: 8px;
                     padding: 8px 20px; font-size: 13px; cursor: not-allowed; }}
    .footer {{ text-align: center; color: #a1a1aa; font-size: 11px; margin-top: 32px; }}
    @media (max-width: 640px) {{ .grid {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
  <header>
    <h1>Haehan AI Desktop</h1>
    <span class="badge">신규 Shell · Phase 2</span>
    <span style="margin-left:auto;font-size:11px;color:#71717a">
      조회 전용 — 실행 버튼 비활성화
    </span>
  </header>

  <div class="container">

    {"" if not user_message else f'<div class="alert"><p>⚠️ {user_message}</p>' + ("".join([f"<ul class='actions'><li>{a}</li></ul>" for a in next_actions])) + "</div>"}
    {"" if not warnings else "".join([f'<div class="alert info"><p>ℹ️ {w}</p></div>' for w in warnings])}

    <div class="grid">
      <!-- 서버 상태 -->
      <div class="card">
        <h2>서버 상태</h2>
        <div class="row"><span class="label">로컬 서버 (8765)</span><span class="value">{_bool_badge(server_alive)}</span></div>
        <div class="row"><span class="label">원격 서버 연결</span><span class="value">{_bool_badge(server_connected)}</span></div>
        <div class="row"><span class="label">Agent ID</span><span class="value mono">{_safe(agent_id, "(미등록)")}</span></div>
        <div class="row"><span class="label">역할(role)</span><span class="value mono">{_safe(role)}</span></div>
      </div>

      <!-- AI 에이전트 상태 -->
      <div class="card">
        <h2>로컬 AI 에이전트</h2>
        <div class="row"><span class="label">AI 가용</span><span class="value">{_bool_badge(la_available, "가능", "불가")}</span></div>
        <div class="row"><span class="label">실행 가능 (can_run)</span><span class="value">{_bool_badge(can_run, "예", "아니오")}</span></div>
        {provider_html}
        {"".join([f'<div class="row"><span class="label muted">차단 사유</span><span class="value muted">{r}</span></div>' for r in blocking])}
      </div>
    </div>

    <!-- 버튼 영역: 새로고침만 허용 -->
    <div style="display:flex;gap:12px;margin-bottom:20px;align-items:center">
      <button class="btn-refresh" onclick="location.reload()">새로고침</button>
      <button class="btn-disabled" disabled title="Phase 2 조회 전용 — 실행은 Phase 3 이후">AI 실행 (비활성화)</button>
      <button class="btn-disabled" disabled title="Phase 2 조회 전용">CAD 시작 (비활성화)</button>
      <span class="muted" style="margin-left:auto">조회 시각: {time.strftime('%H:%M:%S', time.localtime(ts))}</span>
    </div>

    <!-- 로그 -->
    <div class="card" style="margin-bottom:16px">
      <h2>최근 로그</h2>
      {log_html}
    </div>

    <div class="footer">
      Haehan AI Desktop · 신규 Shell Phase 2 · 조회 전용 · ts={ts}
    </div>
  </div>
</body>
</html>"""
    return html


def build_html_from_data(data: dict[str, Any]) -> str:
    """서버 내부 데이터 딕셔너리로 HTML 렌더링 (HTTP 재진입 없음)."""
    return _render(
        health=data.get("health", {}),
        agent=data.get("agent", {}),
        la_health=data.get("la_health", {}),
        preflight=data.get("preflight", {}),
        whoami=data.get("whoami", {}),
        logs_data=data.get("logs", {}),
    )


def build_html() -> str:
    """독립 실행용: 직접 API 조회 후 렌더링 (서버 외부에서 호출 시 사용)."""
    health = _get("health")
    agent = _get("agent_status")
    la_health = _get("la_health")
    preflight = _get("la_preflight")
    logs_data = _get("logs")
    try:
        whoami = _get("whoami")
    except Exception:
        whoami = {"ok": False, "role": "unknown"}
    return _render(
        health=health,
        agent=agent,
        la_health=la_health,
        preflight=preflight,
        whoami=whoami,
        logs_data=logs_data,
    )
