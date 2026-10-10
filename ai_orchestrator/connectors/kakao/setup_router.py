"""L8 — 카카오 앱 등록 실시간 게이트 모니터링 API.

GET  /api/v1/kakao/setup/status   — 현재 게이트 상태 파일 조회
POST /api/v1/kakao/setup/run      — 게이트 실행 + SSE 실시간 스트리밍
POST /api/v1/kakao/setup/gate/:n  — 특정 게이트 단독 실행
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ...paths import repo_root
from ...paths.runtime import data_dir

logger = logging.getLogger(__name__)

ROOT = repo_root()
sys.path.insert(0, str(ROOT))

kakao_setup_router = APIRouter(prefix="/kakao/setup", tags=["kakao-setup"])

STATE_PATH = data_dir() / "kakao_setup_state.json"


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
        except Exception as exc:  # noqa: BLE001
            logger.debug("카카오 설정 상태 파일 로드 실패(무시): %s", type(exc).__name__)
            pass
    return SetupState(gates=[GateState(gate=k, label=v, status="pending") for k, v in GATE_LABELS.items()])


def _save_state(state: SetupState) -> None:
    STATE_PATH.parent.mkdir(exist_ok=True)
    STATE_PATH.write_text(state.model_dump_json(indent=2), encoding="utf-8")


def _now() -> str:
    return datetime.now(UTC).isoformat()


# ── SSE 스트리밍 실행 ─────────────────────────────────────────────────────────


class _GateRun:
    """게이트 실행 1회분의 상태(SSE 이벤트 생성 + 상태 파일 갱신)."""

    def __init__(self, gates_mod) -> None:
        self.gates_mod = gates_mod
        self.state = SetupState(
            running=True,
            started_at=_now(),
            gates=[GateState(gate=k, label=v, status="pending") for k, v in GATE_LABELS.items()],
        )
        _save_state(self.state)
        self.ws_url: str | None = None
        self.app_id: str | None = None

    def event(self, gate: str, status: str, message: str, fix: str = "", **data) -> str:
        payload: dict[str, Any] = {
            "gate": gate,
            "status": status,
            "message": message,
            "fix": fix,
            "data": data,
            "updated_at": _now(),
        }
        # 상태 파일 업데이트
        for g in self.state.gates:
            if g.gate == gate:
                g.status = status
                g.message = message
                g.fix = fix
                g.data = data
                g.updated_at = payload["updated_at"]
                break
        _save_state(self.state)
        return f"event: gate\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

    def info(self, msg: str) -> str:
        return f"event: info\ndata: {json.dumps({'message': msg}, ensure_ascii=False)}\n\n"

    def finish(self, **payload) -> str:
        """실행 종료 처리(상태 파일 저장) 후 done 이벤트 문자열 반환."""
        self.state.running = False
        _save_state(self.state)
        return f"event: done\ndata: {json.dumps(payload)}\n\n"


def _stage_cdp_autostart(run: _GateRun):
    """GATE-1 실패 시 CDP 자동 시작 시도. 성공하면 True."""
    try:
        import subprocess

        subprocess.Popen(
            [sys.executable, str(ROOT / "scripts" / "browser" / "cdp" / "cdp_force_start.py"), "start"],
            cwd=str(ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        import time

        time.sleep(5)
        g1b = run.gates_mod.gate1_cdp()
        if g1b.ok():
            run.ws_url = g1b.data["ws_url"]
            yield run.event("GATE-1", "pass", f"CDP 자동 시작 성공 — {g1b.message}")
            return True
        yield run.event("GATE-1", "fail", "CDP 자동 시작 실패", fix="서버에서 Chrome을 시작할 수 없습니다")
        yield run.finish(success=False)
        return False
    except Exception as e:  # noqa: BLE001 - 카카오 개발자 콘솔 앱 등록 게이트 모니터링(운영규칙상 AI가 직접 수행 가능한 개발자 콘솔 앱 등록 작업) — 상태파일 로드 실패시 초기상태로 폴백(이미 noqa: S110 존재), CDP 자동시작 예외/게이트 5~8 예외는 모두 fail 이벤트로 SSE 스트리밍되어 은폐되지 않음.
        yield run.event("GATE-1", "fail", f"CDP 시작 오류: {e}")
        yield run.finish(success=False)
        return False


def _stage_cdp(run: _GateRun):
    """GATE-1: CDP 연결. 계속 진행 가능하면 True."""
    yield run.event("GATE-1", "running", "CDP 연결 확인 중...")
    g1 = run.gates_mod.gate1_cdp()
    if g1.ok():
        run.ws_url = g1.data["ws_url"]
        yield run.event("GATE-1", "pass", g1.message, ws_url=run.ws_url)
        return True
    yield run.event("GATE-1", "fail", g1.message, fix="CDP 브라우저가 꺼져 있습니다. 잠시 후 자동 재시도합니다.")
    # CDP 자동 시작 시도
    yield run.info("CDP 자동 시작 시도 중...")
    return (yield from _stage_cdp_autostart(run))


def _stage_required(run: _GateRun, gate_id: str, running_msg: str, call, fix: str | None = None):
    """GATE-2~4: 실패 시 중단. 계속 진행 가능하면 True.

    fix 가 None 이면 실패 메시지를 그대로 fix 로 쓴다. GATE-4 는 통과 시 app_id 를 기록한다.
    """
    yield run.event(gate_id, "running", running_msg)
    r = call()
    if r.ok():
        if gate_id == "GATE-4":
            app_id = r.data["app_id"]
            run.app_id = app_id
            run.state.app_id = app_id
            yield run.event(gate_id, "pass", r.message, app_id=run.app_id)
        else:
            yield run.event(gate_id, "pass", r.message)
        return True
    yield run.event(gate_id, "fail", r.message, fix=fix if fix is not None else r.message)
    yield run.finish(success=False, stopped_at=gate_id)
    return False


def _stage_optional(run: _GateRun):
    """GATE-5~8: 실패해도 계속 진행."""
    gates = run.gates_mod
    for gate_id, label, fn in [
        ("GATE-5", "플랫폼 Web", lambda: gates.gate5_platform(run.ws_url, run.app_id)),
        ("GATE-6", "카카오 로그인", lambda: gates.gate6_login_activate(run.ws_url, run.app_id)),
        ("GATE-7", "Redirect URI", lambda: gates.gate7_redirect_uri(run.ws_url, run.app_id)),
        ("GATE-8", "API 키 추출", lambda: gates.gate8_api_key(run.ws_url, run.app_id)),
    ]:
        yield run.event(gate_id, "running", f"{label} 처리 중...")
        try:
            r = fn()
            if r.ok():
                yield run.event(gate_id, "pass", r.message, **r.data)
                if gate_id == "GATE-8" and r.data.get("rest_api_key"):
                    run.state.rest_api_key_found = True
                    _save_state(run.state)
            else:
                yield run.event(gate_id, "fail", r.message, fix=r.message)
        except Exception as e:  # noqa: BLE001 - 카카오 개발자 콘솔 앱 등록 게이트 모니터링(운영규칙상 AI가 직접 수행 가능한 개발자 콘솔 앱 등록 작업) — 상태파일 로드 실패시 초기상태로 폴백(이미 noqa: S110 존재), CDP 자동시작 예외/게이트 5~8 예외는 모두 fail 이벤트로 SSE 스트리밍되어 은폐되지 않음.
            yield run.event(gate_id, "fail", f"오류: {e}", fix="로그 확인 후 재시도")


def _run_gates_stream():
    """게이트를 순서대로 실행하며 SSE 이벤트를 yield한다."""
    from scripts.kakao import setup_haehan_app as gates

    run = _GateRun(gates)

    if not (yield from _stage_cdp(run)):
        return
    gate2_fix = "브라우저에서 카카오 계정으로 로그인하세요 (SMS/앱 인증 필요)"
    if not (
        yield from _stage_required(
            run,
            "GATE-2",
            "카카오 로그인 세션 확인 중... (최대 5분 대기)",
            lambda: gates.gate2_login(run.ws_url, timeout_s=300),
            fix=gate2_fix,
        )
    ):
        return
    if not (
        yield from _stage_required(
            run, "GATE-3", "개발자 콘솔 접근 중...", lambda: gates.gate3_console_access(run.ws_url)
        )
    ):
        return
    if not (
        yield from _stage_required(run, "GATE-4", "앱 등록/확인 중...", lambda: gates.gate4_app_register(run.ws_url))
    ):
        return

    yield from _stage_optional(run)
    yield run.finish(success=True, app_id=run.app_id)


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
