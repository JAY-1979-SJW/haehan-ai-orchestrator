"""L8 — 카카오 앱 등록 실시간 게이트 모니터링 API.

GET  /api/v1/kakao/setup/status   — 현재 게이트 상태 파일 조회
POST /api/v1/kakao/setup/run      — 게이트 실행 + SSE 실시간 스트리밍
POST /api/v1/kakao/setup/gate/:n  — 특정 게이트 단독 실행
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

kakao_setup_router = APIRouter(prefix="/kakao/setup", tags=["kakao-setup"])

STATE_PATH = ROOT / "data" / "kakao_setup_state.json"


# ── 상태 모델 ─────────────────────────────────────────────────────────────────


class GateState(BaseModel):
    gate: str
    label: str
    status: str  # pending | running | pass | fail | skip
    message: str = ""
    fix: str = ""
    data: dict = {}
    updated_at: str = ""


class SetupState(BaseModel):
    running: bool = False
    started_at: str = ""
    gates: list[GateState] = []
    app_id: str = ""
    rest_api_key_found: bool = False


GATE_LABELS = {
    "GATE-1": "CDP 브라우저 연결",
    "GATE-2": "카카오 로그인 세션",
    "GATE-3": "개발자 콘솔 접근",
    "GATE-4": "앱 등록/확인",
    "GATE-5": "플랫폼 Web 등록",
    "GATE-6": "카카오 로그인 활성화",
    "GATE-7": "Redirect URI 등록",
    "GATE-8": "REST API 키 추출",
}


def _load_state() -> SetupState:
    if STATE_PATH.exists():
        try:
            return SetupState(**json.loads(STATE_PATH.read_text(encoding="utf-8")))
        except Exception:  # noqa: S110
            pass
    return SetupState(gates=[GateState(gate=k, label=v, status="pending") for k, v in GATE_LABELS.items()])


def _save_state(state: SetupState) -> None:
    STATE_PATH.parent.mkdir(exist_ok=True)
    STATE_PATH.write_text(state.model_dump_json(indent=2), encoding="utf-8")


def _now() -> str:
    return datetime.now(UTC).isoformat()


# ── SSE 스트리밍 실행 ─────────────────────────────────────────────────────────


def _run_gates_stream():
    """게이트를 순서대로 실행하며 SSE 이벤트를 yield한다."""
    from scripts.kakao.setup_haehan_app import (
        gate1_cdp,
        gate2_login,
        gate3_console_access,
        gate4_app_register,
        gate5_platform,
        gate6_login_activate,
        gate7_redirect_uri,
        gate8_api_key,
    )

    state = SetupState(
        running=True,
        started_at=_now(),
        gates=[GateState(gate=k, label=v, status="pending") for k, v in GATE_LABELS.items()],
    )
    _save_state(state)

    def event(gate: str, status: str, message: str, fix: str = "", **data) -> str:
        payload = {"gate": gate, "status": status, "message": message, "fix": fix, "data": data, "updated_at": _now()}
        # 상태 파일 업데이트
        for g in state.gates:
            if g.gate == gate:
                g.status = status
                g.message = message
                g.fix = fix
                g.data = data
                g.updated_at = payload["updated_at"]
                break
        _save_state(state)
        return f"event: gate\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

    def info(msg: str) -> str:
        return f"event: info\ndata: {json.dumps({'message': msg}, ensure_ascii=False)}\n\n"

    ws_url = None
    app_id = None

    # ── GATE-1 ──
    yield event("GATE-1", "running", "CDP 연결 확인 중...")
    g1 = gate1_cdp()
    if g1.ok():
        ws_url = g1.data["ws_url"]
        yield event("GATE-1", "pass", g1.message, ws_url=ws_url)
    else:
        yield event("GATE-1", "fail", g1.message, fix="CDP 브라우저가 꺼져 있습니다. 잠시 후 자동 재시도합니다.")
        # CDP 자동 시작 시도
        yield info("CDP 자동 시작 시도 중...")
        try:
            import subprocess

            subprocess.Popen(
                [sys.executable, str(ROOT / "scripts" / "cdp_force_start.py"), "start"],
                cwd=str(ROOT),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            import time

            time.sleep(5)
            g1b = gate1_cdp()
            if g1b.ok():
                ws_url = g1b.data["ws_url"]
                yield event("GATE-1", "pass", f"CDP 자동 시작 성공 — {g1b.message}")
            else:
                yield event("GATE-1", "fail", "CDP 자동 시작 실패", fix="서버에서 Chrome을 시작할 수 없습니다")
                state.running = False
                _save_state(state)
                yield f"event: done\ndata: {json.dumps({'success': False})}\n\n"
                return
        except Exception as e:
            yield event("GATE-1", "fail", f"CDP 시작 오류: {e}")
            state.running = False
            _save_state(state)
            yield f"event: done\ndata: {json.dumps({'success': False})}\n\n"
            return

    # ── GATE-2 ──
    yield event("GATE-2", "running", "카카오 로그인 세션 확인 중... (최대 5분 대기)")
    g2 = gate2_login(ws_url, timeout_s=300)
    if g2.ok():
        yield event("GATE-2", "pass", g2.message)
    else:
        yield event("GATE-2", "fail", g2.message, fix="브라우저에서 카카오 계정으로 로그인하세요 (SMS/앱 인증 필요)")
        state.running = False
        _save_state(state)
        yield f"event: done\ndata: {json.dumps({'success': False, 'stopped_at': 'GATE-2'})}\n\n"
        return

    # ── GATE-3 ──
    yield event("GATE-3", "running", "개발자 콘솔 접근 중...")
    g3 = gate3_console_access(ws_url)
    if g3.ok():
        yield event("GATE-3", "pass", g3.message)
    else:
        yield event("GATE-3", "fail", g3.message, fix=g3.message)
        state.running = False
        _save_state(state)
        yield f"event: done\ndata: {json.dumps({'success': False, 'stopped_at': 'GATE-3'})}\n\n"
        return

    # ── GATE-4 ──
    yield event("GATE-4", "running", "앱 등록/확인 중...")
    g4 = gate4_app_register(ws_url)
    if g4.ok():
        app_id = g4.data["app_id"]
        state.app_id = app_id
        yield event("GATE-4", "pass", g4.message, app_id=app_id)
    else:
        yield event("GATE-4", "fail", g4.message, fix=g4.message)
        state.running = False
        _save_state(state)
        yield f"event: done\ndata: {json.dumps({'success': False, 'stopped_at': 'GATE-4'})}\n\n"
        return

    # ── GATE-5~8: 실패해도 계속 진행 ──
    for gate_id, label, fn in [
        ("GATE-5", "플랫폼 Web", lambda: gate5_platform(ws_url, app_id)),
        ("GATE-6", "카카오 로그인", lambda: gate6_login_activate(ws_url, app_id)),
        ("GATE-7", "Redirect URI", lambda: gate7_redirect_uri(ws_url, app_id)),
        ("GATE-8", "API 키 추출", lambda: gate8_api_key(ws_url, app_id)),
    ]:
        yield event(gate_id, "running", f"{label} 처리 중...")
        try:
            r = fn()
            if r.ok():
                yield event(gate_id, "pass", r.message, **r.data)
                if gate_id == "GATE-8" and r.data.get("rest_api_key"):
                    state.rest_api_key_found = True
                    _save_state(state)
            else:
                yield event(gate_id, "fail", r.message, fix=r.message)
        except Exception as e:
            yield event(gate_id, "fail", f"오류: {e}", fix="로그 확인 후 재시도")

    state.running = False
    _save_state(state)
    yield f"event: done\ndata: {json.dumps({'success': True, 'app_id': app_id})}\n\n"


# ── 엔드포인트 ────────────────────────────────────────────────────────────────


@kakao_setup_router.get("/status", response_model=SetupState)
def get_status():
    return _load_state()


@kakao_setup_router.post("/run")
def run_setup():
    state = _load_state()
    if state.running:
        return StreamingResponse(
            iter([f"event: error\ndata: {json.dumps({'message': '이미 실행 중'})}\n\n"]),
            media_type="text/event-stream",
        )

    def stream():
        yield from _run_gates_stream()

    return StreamingResponse(
        stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
    )


@kakao_setup_router.post("/reset")
def reset_state():
    state = SetupState(gates=[GateState(gate=k, label=v, status="pending") for k, v in GATE_LABELS.items()])
    _save_state(state)
    return {"ok": True}
