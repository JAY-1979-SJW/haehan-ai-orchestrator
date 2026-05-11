"""AutoCAD backend ping using the verified local pywin32 subprocess path."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any
from .http_agent_client import _ping_local_http_agent


DEFAULT_PROGID = "AutoCAD.Application.24.3"

def autocad_ping(timeout_seconds: int = 20, progid: str = DEFAULT_PROGID) -> dict[str, Any]:
    """Ping AutoCAD through the local CAD agent, falling back to direct subprocess."""
    agent_result = _ping_local_http_agent(timeout_seconds=min(max(1, int(timeout_seconds)), 5))
    if agent_result.get("ok"):
        return agent_result

    fallback = _ping_verified_subprocess(timeout_seconds=timeout_seconds, progid=progid)
    fallback["local_agent_attempt"] = agent_result
    return fallback


def _ping_verified_subprocess(timeout_seconds: int = 20, progid: str = DEFAULT_PROGID) -> dict[str, Any]:
    timeout = max(8, int(timeout_seconds))
    result_path = str(Path(tempfile.gettempdir()) / f"haehan_cad_ping_{uuid.uuid4().hex}.json")
    script = f"""
import json
import time
import pythoncom
import win32com.client

pythoncom.CoInitialize()
p = {progid!r}
acad = win32com.client.Dispatch(p)
acad.Visible = True
time.sleep(5)
documents_count = int(getattr(acad.Documents, 'Count', 0))
active_document = None
if documents_count:
    try:
        active_document = str(getattr(acad.ActiveDocument, 'Name', ''))
    except Exception:
        active_document = None
payload = {{
    'ok': True,
    'backend': 'pywin32_com_subprocess_verified',
    'progid': p,
    'status': 'OK',
    'name': str(getattr(acad, 'Name', '')),
    'version': str(getattr(acad, 'Version', '')),
    'documents_count': documents_count,
    'active_document': active_document,
}}
open({result_path!r}, 'w', encoding='utf-8').write(json.dumps(payload, ensure_ascii=False))
"""
    try:
        started = time.monotonic()
        completed = subprocess.run(
            [sys.executable, "-c", script],
            timeout=timeout,
            shell=False,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "backend": "pywin32_com_subprocess_verified",
            "progid": progid,
            "status": "TIMEOUT",
            "error_code": "CAD_AUTOCAD_PING_TIMEOUT",
            "message": f"AutoCAD COM ping exceeded {timeout}s.",
        }

    if completed.returncode != 0:
        return {
            "ok": False,
            "backend": "pywin32_com_subprocess_verified",
            "progid": progid,
            "status": "FAILED",
            "error_code": "CAD_AUTOCAD_PING_FAILED",
            "returncode": completed.returncode,
        }

    try:
        with open(result_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except (IndexError, json.JSONDecodeError) as exc:
        return {
            "ok": False,
            "backend": "pywin32_com_subprocess_verified",
            "progid": progid,
            "status": "FAILED",
            "error_code": "CAD_AUTOCAD_PING_BAD_OUTPUT",
            "message": str(exc),
        }
    except OSError as exc:
        return {
            "ok": False,
            "backend": "pywin32_com_subprocess_verified",
            "progid": progid,
            "status": "FAILED",
            "error_code": "CAD_AUTOCAD_PING_RESULT_MISSING",
            "message": str(exc),
            "result_path": result_path,
        }

    payload["elapsed_seconds"] = round(time.monotonic() - started, 3)
    return payload
