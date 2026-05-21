"""Haehan AI 데스크탑 앱 — pywebview 기반.

실행:
    python -m desktop.webview_app_pywebview

구조:
    - 로컬 FastAPI 서버(8765)가 이미 실행 중이면 재사용
    - 실행 중이 아니면 별도 스레드에서 기동 후 대기
    - pywebview 네이티브 창에서 http://127.0.0.1:8765 표시
    - 창 닫으면 본 프로세스 서버도 함께 종료 (외부 서버는 유지)

보안 정책:
    - device_token / registration_code / API key 원문 출력 금지
    - console.log 에서 secret 패턴 필터링
"""
from __future__ import annotations

import json
import logging
import sys
import threading
import time
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

from desktop.app_config import LOCAL_HOST, LOCAL_PORT, LOCAL_URL as _LOCAL_URL  # noqa: E402
_SERVER_PORT = LOCAL_PORT
_SERVER_READY_TIMEOUT = 10


def _is_server_up() -> bool:
    try:
        urllib.request.urlopen(_LOCAL_URL, timeout=1)
        return True
    except Exception:
        return False


def _wait_for_server(timeout: float = _SERVER_READY_TIMEOUT) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _is_server_up():
            return True
        time.sleep(0.3)
    return False


_server_thread: threading.Thread | None = None
_server_owned = False  # 본 프로세스가 서버를 띄웠는지


def _start_embedded_server() -> None:
    global _server_owned
    try:
        import uvicorn
        from desktop.local_server import app as _app
        _server_owned = True
        uvicorn.run(_app, host=LOCAL_HOST, port=_SERVER_PORT, log_level="warning",
                    log_config=None)
    except Exception as exc:
        import traceback
        logger.error("embedded server error: %s\n%s", type(exc).__name__, traceback.format_exc())


def ensure_server() -> bool:
    """서버가 없으면 임베디드로 기동. 준비되면 True 반환."""
    global _server_thread
    if _is_server_up():
        logger.info("외부 서버 감지 — 재사용")
        return True
    logger.info("서버 기동 중…")
    _server_thread = threading.Thread(target=_start_embedded_server, daemon=True)
    _server_thread.start()
    return _wait_for_server()


def run_pywebview(title: str = "Haehan AI", width: int = 1200, height: int = 800) -> None:
    import webview

    window = webview.create_window(
        title,
        _LOCAL_URL,
        width=width,
        height=height,
        min_size=(800, 560),
        resizable=True,
        text_select=True,
    )
    webview.start(debug=False)


def _app_root() -> Path:
    """exe / 소스 모두에서 프로젝트 루트 반환."""
    if getattr(sys, "frozen", False):
        # onefolder exe: HaehanAI-Desktop.exe 옆 디렉터리
        return Path(sys.executable).parent
    return Path(__file__).parent.parent


def _setup_logging() -> None:
    """콘솔 + 파일 동시 로깅 설정. exe / 소스 모두 동작."""
    import logging.handlers
    log_dir = _app_root() / "data" / "logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "desktop_app.log"
        file_handler = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        file_handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        ))
        logging.root.addHandler(file_handler)
    except Exception:
        pass
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def _check_consent() -> bool:
    """최초 실행 시 정보 제공 동의 창 표시. 동의하면 True 반환."""
    consent_file = _app_root() / "data" / "consent.json"
    if consent_file.exists():
        try:
            data = json.loads(consent_file.read_text(encoding="utf-8"))
            if data.get("agreed"):
                return True
        except Exception:
            pass

    # tkinter 동의 창
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        agreed = messagebox.askyesno(
            "HaehanAI 정보 제공 동의",
            "HaehanAI Desktop을 사용하려면 아래 항목에 동의해야 합니다.\n\n"
            "■ 수집 항목: 앱 오류 로그, 실행 환경 정보\n"
            "■ 이용 목적: 서비스 품질 개선 및 오류 분석\n"
            "■ 보유 기간: 6개월\n\n"
            "위 내용에 동의하십니까?",
            icon="question"
        )
        root.destroy()
    except Exception:
        agreed = True  # GUI 없는 환경에서는 동의로 처리

    consent_file.parent.mkdir(parents=True, exist_ok=True)
    import json as _json
    from datetime import datetime
    consent_file.write_text(
        _json.dumps({"agreed": agreed, "ts": datetime.now().isoformat()}, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    return agreed


def main() -> None:
    _setup_logging()
    logger.info("=== HaehanAI Desktop 시작 ===")

    if not _check_consent():
        logger.info("사용자가 동의를 거부하여 종료합니다.")
        sys.exit(0)

    if not ensure_server():
        logger.error("로컬 서버 준비 실패 — 그래도 창을 엽니다.")

    try:
        run_pywebview()
    except ImportError:
        logger.error("pywebview 미설치: pip install pywebview")
        sys.exit(1)
    except Exception as exc:
        import traceback
        logger.error("pywebview 실행 오류: %s\n%s", type(exc).__name__, traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()
