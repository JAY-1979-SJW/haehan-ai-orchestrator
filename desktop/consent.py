"""HaehanAI Desktop 정보 제공 동의 로직 (공유 모듈).

webview_app_pywebview.py 에서 분리 — HAEHAN-DESKTOP-LEGACY-UI-REMOVAL-01.
main_launcher.py 및 향후 진입점에서 공통으로 사용한다.

보안:
    동의 파일에 secret/token/password 저장 금지.
    agreed/agreed_at/version/scope 만 저장.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

CONSENT_VERSION = "1"
CONSENT_SCOPE = "haehan-desktop-default"

CONSENT_PROMPT_TEXT = (
    "HaehanAI Desktop을 사용하려면 아래 항목에 동의해야 합니다.\n\n"
    "■ 수집 항목: 앱 오류 로그, 실행 환경 정보\n"
    "■ 이용 목적: 서비스 품질 개선 및 오류 분석\n"
    "■ 보유 기간: 6개월\n\n"
    "위 내용에 동의하십니까?"
)


def _app_root() -> Path:
    """exe / 소스 모두에서 프로젝트 루트 반환."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent.parent


def _consent_file_path() -> Path:
    return _app_root() / "data" / "consent.json"


def _save_consent(agreed: bool) -> None:
    """동의 결과 저장. agreed/agreed_at/version/scope 만 저장 — secret 금지."""
    from datetime import datetime
    consent_file = _consent_file_path()
    consent_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "agreed": bool(agreed),
        "agreed_at": datetime.now().isoformat(),
        "version": CONSENT_VERSION,
        "scope": CONSENT_SCOPE,
    }
    consent_file.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _default_tk_dialog_runner() -> bool:
    """실제 tkinter 창. HAEHAN_SKIP_GUI=1 환경에서는 호출되지 않아야 한다."""
    import tkinter as tk
    from tkinter import messagebox
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        return bool(messagebox.askyesno(
            "HaehanAI 정보 제공 동의", CONSENT_PROMPT_TEXT, icon="question",
        ))
    finally:
        root.destroy()


def check_consent(dialog_runner=None) -> bool:
    """최초 실행 시 정보 제공 동의 창 표시. 동의하면 True.

    Args:
        dialog_runner: 0-인자 callable -> bool. 주입 시 tkinter 대신 사용 (테스트/CI).
    """
    import os as _os
    consent_file = _consent_file_path()
    if consent_file.exists():
        try:
            data = json.loads(consent_file.read_text(encoding="utf-8"))
            if data.get("agreed") is True:
                return True
            if data.get("agreed") is False:
                pass
        except Exception:
            pass

    skip_gui = _os.environ.get("HAEHAN_SKIP_GUI", "").strip() in ("1", "true", "True")

    if dialog_runner is not None:
        try:
            agreed = bool(dialog_runner())
        except Exception:
            agreed = False
    elif skip_gui:
        agreed = False
    else:
        try:
            agreed = _default_tk_dialog_runner()
        except Exception:
            agreed = False

    _save_consent(agreed)
    return agreed


# 하위 호환 — 기존 코드에서 _check_consent 이름으로 import하는 경우를 위한 별칭
_check_consent = check_consent
