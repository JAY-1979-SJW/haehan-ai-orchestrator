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


def _find_port() -> int:
    """환경변수 또는 기본값 8401 반환."""
    return int(os.environ.get("HAEHAN_PORT", "8401"))


def main() -> None:
    _setup_bundle_env()

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
