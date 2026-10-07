"""Mock HTTP task server (B안 3단계 — 로컬 에이전트 live 검증용).

FastAPI 로 최소 구현. 인메모리 큐 + 결과 저장소. 상용 서버 구현이 준비되기
전 로컬 에이전트와의 HTTP 계약(GET /tasks/poll, POST /tasks/result) 을
검증하기 위해서만 쓴다.

실행:
    python scripts/archive/one_off/mock_task_server.py --port 8765 --token test-token

엔드포인트:
    GET  /tasks/poll         — Bearer auth. 큐 head 를 pop, 비어있으면 {}
    POST /tasks/result       — Bearer auth. 결과 dict 저장
    POST /tasks/enqueue      — 검증용. 익명 허용. body = task dict
    GET  /tasks/results      — 검증용. 익명 허용. 저장된 결과 덤프
    GET  /healthz            — 간단 liveness

큐/결과는 프로세스 메모리에만 저장된다. 서버 재시작 시 초기화됨.
"""

from __future__ import annotations

import argparse
import logging
import os
import threading
from collections import deque

try:
    import uvicorn
    from fastapi import FastAPI, Header, HTTPException, Request
except ImportError as e:  # pragma: no cover - dev env 필수 dep
    raise SystemExit("fastapi / uvicorn 이 필요합니다. requirements.txt 를 설치하세요.") from e


def _verify_bearer(expected_token: str, authorization: str | None) -> None:
    if not expected_token:
        return  # 토큰 미설정이면 anonymous 허용 (개발 편의)
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing_bearer")
    supplied = authorization.split(" ", 1)[1].strip()
    if supplied != expected_token:
        raise HTTPException(status_code=403, detail="bad_token")


def _require_object_body(body) -> dict:
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="body_must_be_object")
    return body


def build_app(expected_token: str) -> FastAPI:
    app = FastAPI(title="local-agent-mock-api")
    pending: deque[dict] = deque()
    results: list[dict] = []
    lock = threading.Lock()

    def _check_auth(authorization: str | None) -> None:
        _verify_bearer(expected_token, authorization)

    @app.get("/healthz")
    def healthz():
        return {"ok": True, "pending": len(pending), "results": len(results)}

    @app.get("/tasks/poll")
    def poll(authorization: str | None = Header(default=None)):
        _check_auth(authorization)
        with lock:
            if pending:
                task = pending.popleft()
                return {"task": task}
        return {}

    @app.post("/tasks/result")
    async def result(
        request: Request,
        authorization: str | None = Header(default=None),
    ):
        _check_auth(authorization)
        body = _require_object_body(await request.json())
        with lock:
            results.append(body)
        return {"stored": True, "count": len(results)}

    # ── 검증 helper (익명) ─────────────────────────────────────────
    @app.post("/tasks/enqueue")
    async def enqueue(request: Request):
        body = _require_object_body(await request.json())
        with lock:
            pending.append(body)
        return {"queued": True, "pending": len(pending)}

    @app.get("/tasks/results")
    def dump_results():
        with lock:
            return {"count": len(results), "results": list(results)}

    @app.get("/tasks/pending")
    def dump_pending():
        with lock:
            return {"count": len(pending), "pending": list(pending)}

    return app


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Mock task API server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--token",
        default=os.environ.get("AGENT_TOKEN", "test-token"),
        help="기대할 Bearer 토큰. 빈 문자열이면 anonymous 허용.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    app = build_app(args.token)
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
