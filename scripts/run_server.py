"""FastAPI 서버 진입점 — PyInstaller 번들 전용.

패키징된 EXE에서 실행될 때:
  - sys._MEIPASS 경로를 sys.path에 추가
  - 번들 Chromium 경로를 PLAYWRIGHT_BROWSERS_PATH로 설정
  - uvicorn으로 ai_orchestrator.server 구동
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _setup_bundle_env() -> None:
    """PyInstaller 번들 환경 초기화."""
    # MEIPASS: 번들 내 리소스 루트
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        meipass_path = Path(meipass)
        # 번들 경로를 sys.path 최상단에 추가
        if str(meipass_path) not in sys.path:
            sys.path.insert(0, str(meipass_path))
        # 번들 Chromium 설정 (Playwright가 이 경로에서 브라우저 탐색)
        chromium_dir = meipass_path / "chromium"
        if chromium_dir.exists():
            os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(chromium_dir))
        # .env 파일: EXE 옆 또는 MEIPASS 내
        exe_dir = Path(sys.executable).parent
        env_candidates = [exe_dir / ".env", meipass_path / ".env"]
        for env_file in env_candidates:
            if env_file.exists():
                os.environ.setdefault("HAEHAN_ENV_FILE", str(env_file))
                break
        # 영속 데이터 경로 기본값 (Electron이 미주입 시) — %APPDATA%\Haehan AI\data
        if not os.environ.get("HAEHAN_DATA_DIR"):
            appdata = os.environ.get("APPDATA") or str(exe_dir)
            os.environ["HAEHAN_DATA_DIR"] = str(Path(appdata) / "Haehan AI" / "data")


def _dispatch_grant_task() -> bool:
    """동결 exe에서 `-m` 대체 — `--grant-task {scan|report|fill}` 처리."""
    if "--grant-task" not in sys.argv:
        return False
    task = sys.argv[sys.argv.index("--grant-task") + 1]
    module = {"scan": "scan", "report": "report", "fill": "form_fill"}.get(task)
    if not module:
        print(f"[run_server] 알 수 없는 grant-task: {task}")
        sys.exit(2)
    import importlib

    mod = importlib.import_module(f"scripts.grant_radar.{module}")
    sys.exit(mod.main())


def _find_port() -> int:
    """환경변수 또는 기본값 8401 반환."""
    return int(os.environ.get("HAEHAN_PORT", "8401"))


def main() -> None:
    _setup_bundle_env()

    # grant_radar 서브태스크 디스패치 (동결 exe에서 -m 대체)
    if _dispatch_grant_task():
        return

    import uvicorn

    host = os.environ.get("HAEHAN_HOST", "127.0.0.1")
    port = _find_port()

    uvicorn.run(
        "ai_orchestrator.server:app",
        host=host,
        port=port,
        log_level="info",
        access_log=False,
    )


if __name__ == "__main__":
    main()
