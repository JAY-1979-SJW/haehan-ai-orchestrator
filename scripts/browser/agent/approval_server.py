"""브라우저 팝업 승인 UI 서버.

터미널 input() 대신 로컬 Flask 서버 + 브라우저 팝업으로 승인 처리.

동작 방식
=========
1. 백그라운드 스레드에서 Flask 서버 시작 (포트 7722)
2. 승인 요청 발생 → request_approval() 호출
3. 브라우저에서 http://localhost:7722/ 자동 오픈
4. 사용자가 승인/거부 클릭 → threading.Event로 결과 반환
5. 결과를 호출자에게 반환 (blocking)

사용법
======
    from scripts.browser.agent.approval_server import request_approval

    approved = request_approval(
        action="submit",
        label="민원 접수 제출",
        category="LEGAL",
        detail={"title": "건축허가 신청", "service": "국민신문고"},
    )
    if approved:
        ...실행...
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
import webbrowser
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from flask import Flask, Response, jsonify, request

# ── 설정 ────────────────────────────────────────────────────────────────────

_PORT = 7722
_HOST = "127.0.0.1"
_TIMEOUT_SECONDS = 120  # 승인 대기 최대 시간


def _local_ui_fallback_enabled() -> bool:
    return os.getenv("HAEHAN_LOCAL_APPROVAL_UI_FALLBACK", "").strip().lower() in {"1", "true", "yes", "on"}


# ── 상태 ────────────────────────────────────────────────────────────────────


@dataclass
class ApprovalRequest:
    request_id: str
    action: str
    label: str
    category: str
    detail: dict
    created_at: str
    result: str = "pending"  # pending / approved / rejected / timeout
    event: threading.Event = field(default_factory=threading.Event, repr=False)


_pending: dict[str, ApprovalRequest] = {}
_history: list[dict] = []
_lock = threading.Lock()
_server_started = False
_server_thread: threading.Thread | None = None

# ── Flask 앱 ─────────────────────────────────────────────────────────────────

app = Flask(__name__)
app.config["PROPAGATE_EXCEPTIONS"] = True


_HTML = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta http-equiv="refresh" content="3">
<title>AI 브라우저 승인</title>
<style>
  body{font-family:'Malgun Gothic',sans-serif;background:#f5f5f5;margin:0;padding:20px}
  h1{color:#1a1a2e;font-size:1.4em;border-bottom:2px solid #e94560;padding-bottom:8px}
  .card{background:#fff;border-radius:10px;padding:20px;margin:16px 0;
        box-shadow:0 2px 8px rgba(0,0,0,.08)}
  .badge{display:inline-block;padding:3px 10px;border-radius:12px;font-size:.8em;font-weight:bold}
  .CREDENTIAL{background:#fff3cd;color:#856404}
  .MONEY{background:#f8d7da;color:#721c24}
  .LEGAL{background:#d1ecf1;color:#0c5460}
  .ACCOUNT{background:#fce8e8;color:#8b0000}
  .SEND{background:#d4edda;color:#155724}
  .SUBMIT{background:#e2d9f3;color:#4a235a}
  .OTHER{background:#e2e3e5;color:#383d41}
  .detail{background:#f8f9fa;border-radius:6px;padding:10px;margin:10px 0;font-size:.9em}
  .detail dt{font-weight:bold;color:#555}
  .detail dd{margin:2px 0 8px 12px;color:#333}
  .btn{border:none;border-radius:6px;padding:10px 28px;font-size:1em;
       cursor:pointer;font-weight:bold;margin:4px}
  .btn-approve{background:#28a745;color:#fff}
  .btn-approve:hover{background:#218838}
  .btn-reject{background:#dc3545;color:#fff}
  .btn-reject:hover{background:#c82333}
  .empty{color:#888;text-align:center;padding:40px}
  .history{font-size:.85em;color:#666}
  .approved{color:#28a745;font-weight:bold}
  .rejected{color:#dc3545;font-weight:bold}
  .ts{color:#999;font-size:.8em}
</style>
</head>
<body>
<h1>🔐 AI 브라우저 승인 대기</h1>

{% if pending %}
{% for r in pending %}
<div class="card">
  <div style="display:flex;justify-content:space-between;align-items:center">
    <span><strong>{{ r.action.upper() }}</strong> &nbsp;
      <span class="badge {{ r.category }}">{{ r.category }}</span>
    </span>
    <span class="ts">{{ r.created_at }}</span>
  </div>
  <p style="font-size:1.1em;margin:10px 0">{{ r.label }}</p>
  <dl class="detail">
  {% for k, v in r.detail.items() %}
    <dt>{{ k }}</dt><dd>{{ v }}</dd>
  {% endfor %}
  </dl>
  <form method="post" action="/decide/{{ r.request_id }}" style="margin-top:12px">
    <button class="btn btn-approve" name="result" value="approved">✓ 승인</button>
    <button class="btn btn-reject" name="result" value="rejected">✗ 거부</button>
  </form>
</div>
{% endfor %}
{% else %}
<div class="card empty">대기 중인 승인 요청이 없습니다.</div>
{% endif %}

{% if history %}
<h2 style="font-size:1em;color:#555;margin-top:24px">처리 이력</h2>
<div class="card history">
{% for h in history[-10:]|reverse %}
  <div style="padding:4px 0;border-bottom:1px solid #eee">
    <span class="{{ h.result }}">
      {{ '✓' if h.result == 'approved' else '✗' }}
    </span>
    {{ h.action }} — {{ h.label }}
    <span class="ts">&nbsp;{{ h.created_at }}</span>
  </div>
{% endfor %}
</div>
{% endif %}

<p style="color:#aaa;font-size:.75em;text-align:center;margin-top:20px">
  AI 브라우저 자동화 승인 게이트 | 3초마다 자동 새로고침
</p>
</body>
</html>"""


@app.route("/", methods=["GET"])
def index():
    from flask import render_template_string

    with _lock:
        pending = [
            {
                "request_id": r.request_id,
                "action": r.action,
                "label": r.label,
                "category": r.category,
                "detail": r.detail,
                "created_at": r.created_at,
            }
            for r in _pending.values()
            if r.result == "pending"
        ]
    return render_template_string(_HTML, pending=pending, history=_history)


@app.route("/decide/<request_id>", methods=["POST"])
def decide(request_id: str):
    result = request.form.get("result", "rejected")
    with _lock:
        req = _pending.get(request_id)
    if req:
        req.result = result
        _history.append(
            {
                "request_id": request_id,
                "action": req.action,
                "label": req.label,
                "category": req.category,
                "result": result,
                "created_at": req.created_at,
            }
        )
        req.event.set()
    return '<meta http-equiv="refresh" content="0;url=/">'


@app.route("/api/status", methods=["GET"])
def api_status():
    with _lock:
        return jsonify(
            {
                "pending": len([r for r in _pending.values() if r.result == "pending"]),
                "history": len(_history),
            }
        )


@app.route("/api/audit/stream", methods=["GET"])
def audit_stream():
    """SSE 감사 로그 실시간 스트림 (5번 보완).

    curl http://localhost:7722/api/audit/stream
    """

    def _generate():
        import time as _time

        from scripts.browser.agent.audit_log import get_audit_path

        path = get_audit_path()
        last_size = path.stat().st_size if path.exists() else 0
        yield f"data: {json.dumps({'event': 'connected', 'path': str(path)}, ensure_ascii=False)}\n\n"
        while True:
            _time.sleep(1)
            if not path.exists():
                continue
            current_size = path.stat().st_size
            if current_size > last_size:
                with path.open(encoding="utf-8") as f:
                    f.seek(last_size)
                    new_lines = f.read()
                last_size = current_size
                for line in new_lines.splitlines():
                    line = line.strip()
                    if line:
                        yield f"data: {line}\n\n"

    return Response(
        _generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.route("/api/audit/recent", methods=["GET"])
def audit_recent():
    """최근 감사 로그 N건 반환."""
    from flask import request as freq

    from scripts.browser.agent.audit_log import read_log

    n = int(freq.args.get("n", 50))
    entries = read_log()
    return jsonify({"entries": entries[-n:], "total": len(entries)})


@app.route("/api/audit/summary", methods=["GET"])
def audit_summary():
    """감사 로그 요약 통계."""
    from scripts.browser.agent.audit_log import summarize_log

    return jsonify(summarize_log())


# ── 서버 시작 ────────────────────────────────────────────────────────────────


def _run_server():
    import logging

    log = logging.getLogger("werkzeug")
    log.setLevel(logging.ERROR)
    app.run(host=_HOST, port=_PORT, debug=False, use_reloader=False)


def ensure_server_running() -> bool:
    """서버가 실행 중이 아니면 백그라운드 스레드로 시작."""
    global _server_started, _server_thread
    if _server_started:
        return True
    t = threading.Thread(target=_run_server, daemon=True, name="approval-server")
    t.start()
    _server_thread = t
    # 서버 기동 대기
    for _ in range(20):
        time.sleep(0.2)
        try:
            import urllib.request

            urllib.request.urlopen(f"http://{_HOST}:{_PORT}/api/status", timeout=1)
            _server_started = True
            return True
        except Exception:  # noqa: BLE001, S112
            continue
    return False


# ── 공개 API ─────────────────────────────────────────────────────────────────


def request_approval(
    action: str,
    label: str,
    *,
    category: str = "OTHER",
    detail: dict[str, Any] | None = None,
    timeout: int = _TIMEOUT_SECONDS,
    auto_open_browser: bool = True,
) -> bool:
    """승인 요청 → 브라우저 팝업에서 사용자가 승인/거부.

    Parameters
    ----------
    action : 액션 타입 (navigate, click, submit 등)
    label  : 사람이 읽을 설명
    category : APPROVE 카테고리 (MONEY, LEGAL, CREDENTIAL 등)
    detail : 추가 정보 dict (민원 제목, 금액 등)
    timeout : 최대 대기 초 (기본 120초)
    auto_open_browser : 자동으로 승인 UI 열기

    Returns
    -------
    bool : True = 승인, False = 거부/타임아웃
    """
    if not _local_ui_fallback_enabled():
        from scripts.browser.agent.approval_api_client import request_approval_via_api

        result = request_approval_via_api(
            action=action,
            label=label,
            category=category,
            detail=detail or {},
            timeout=timeout,
        )
        return result.approved

    ensure_server_running()

    req_id = f"apr_{uuid.uuid4().hex[:8]}"
    req = ApprovalRequest(
        request_id=req_id,
        action=action,
        label=label,
        category=category,
        detail=detail or {},
        created_at=datetime.now(UTC).strftime("%H:%M:%S"),
    )
    with _lock:
        _pending[req_id] = req

    url = f"http://{_HOST}:{_PORT}/"
    if auto_open_browser:
        webbrowser.open(url)

    print(f"\n[승인 요청] {action.upper()}: {label}")
    print(f"  카테고리: {category}")
    print(f"  브라우저에서 승인해주세요 → {url}")

    finished = req.event.wait(timeout=timeout)
    with _lock:
        _pending.pop(req_id, None)

    if not finished:
        req.result = "timeout"
        print(f"[승인] 타임아웃 ({timeout}초) → 자동 거부")
        return False

    approved = req.result == "approved"
    print(f"[승인] {'✓ 승인됨' if approved else '✗ 거부됨'}")
    return approved


def approval_url() -> str:
    return f"http://{_HOST}:{_PORT}/"


# ── 비동기 승인 큐 (3번 보완) ─────────────────────────────────────────────────
# request_approval()은 결과를 blocking 대기하지만,
# request_approval_async()는 즉시 반환 → AUTO 액션 계속 진행 가능.


class AsyncApprovalHandle:
    """비동기 승인 핸들. poll() 또는 wait()로 결과 확인."""

    def __init__(self, req: ApprovalRequest):
        self._req = req

    @property
    def request_id(self) -> str:
        return self._req.request_id

    @property
    def is_pending(self) -> bool:
        return self._req.result == "pending"

    def poll(self) -> str | None:
        """현재 상태 반환. 'approved' / 'rejected' / 'timeout' / None(대기중)."""
        r = self._req.result
        return None if r == "pending" else r

    def wait(self, timeout: int = _TIMEOUT_SECONDS) -> bool:
        """결과를 blocking 대기. True=승인."""
        finished = self._req.event.wait(timeout=timeout)
        with _lock:
            _pending.pop(self._req.request_id, None)
        if not finished:
            self._req.result = "timeout"
            print(f"[승인] 타임아웃 ({timeout}초) → 자동 거부")
            return False
        approved = self._req.result == "approved"
        print(f"[승인] {'✓ 승인됨' if approved else '✗ 거부됨'}")
        return approved

    def cancel(self) -> None:
        """승인 요청을 취소(거부)로 처리."""
        self._req.result = "rejected"
        self._req.event.set()
        with _lock:
            _pending.pop(self._req.request_id, None)


def request_approval_async(
    action: str,
    label: str,
    *,
    category: str = "OTHER",
    detail: dict[str, Any] | None = None,
    auto_open_browser: bool = True,
) -> AsyncApprovalHandle:
    """비동기 승인 요청. 호출 즉시 반환 → AUTO 액션 계속 가능.

    사용 예
    -------
    handle = request_approval_async("submit", "민원 접수", category="LEGAL")
    # ... AUTO 액션 계속 실행 ...
    approved = handle.wait()   # 필요 시점에 blocking 대기
    """
    if not _local_ui_fallback_enabled():
        approved = request_approval(
            action,
            label,
            category=category,
            detail=detail or {},
            timeout=1,
            auto_open_browser=False,
        )
        req = ApprovalRequest(
            request_id=f"api_{uuid.uuid4().hex[:8]}",
            action=action,
            label=label,
            category=category,
            detail=detail or {},
            created_at=datetime.now(UTC).strftime("%H:%M:%S"),
            result="approved" if approved else "rejected",
        )
        req.event.set()
        return AsyncApprovalHandle(req)

    ensure_server_running()

    req_id = f"apr_{uuid.uuid4().hex[:8]}"
    req = ApprovalRequest(
        request_id=req_id,
        action=action,
        label=label,
        category=category,
        detail=detail or {},
        created_at=datetime.now(UTC).strftime("%H:%M:%S"),
    )
    with _lock:
        _pending[req_id] = req

    url = f"http://{_HOST}:{_PORT}/"
    if auto_open_browser:
        webbrowser.open(url)

    print(f"\n[비동기 승인 요청] {action.upper()}: {label}")
    print(f"  카테고리: {category}")
    print(f"  브라우저에서 승인해주세요 → {url}")
    print("  (작업 계속 진행 중... handle.wait()로 결과 확인)")

    return AsyncApprovalHandle(req)
