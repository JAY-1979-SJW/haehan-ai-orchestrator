"""grant_radar_router.py — 정부 지원사업 레이더 API (Phase 1).

GET  /api/v1/grant-radar/report  — 최신 보고서 JSON 반환 (read-only)
POST /api/v1/grant-radar/scan    — 스캔+보고서 생성 트리거 (별도 헤드리스 subprocess)

L8 Server API 계층. 업무 로직은 scripts/grant_radar/* (L6/L10)에 위임.
보안: secret 미출력. mutation은 로컬 파일 생성뿐(외부 발행/제출 없음).
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
REPORT_FILE = ROOT / "data" / "grant_radar" / "report_latest.json"

grant_radar_router = APIRouter(prefix="/grant-radar", tags=["grant-radar"])

_scan_running = False


@grant_radar_router.get("/report")
def get_report():
    """최신 지원사업 보고서 반환. 없으면 빈 결과."""
    if not REPORT_FILE.exists():
        return {"ok": False, "reason": "no_report", "items": [], "message": "아직 스캔 전입니다. 스캔을 실행하세요."}
    try:
        data = json.loads(REPORT_FILE.read_text(encoding="utf-8"))
        return data
    except Exception as e:
        logger.error("보고서 로드 실패: %s", e)
        return {"ok": False, "reason": "read_error", "items": []}


@grant_radar_router.post("/scan")
def trigger_scan():
    """스캔 → 보고서 생성을 동기 실행. (별도 헤드리스 Chromium, 메인 Chrome 무관)"""
    global _scan_running
    if _scan_running:
        return {"ok": False, "reason": "already_running"}
    _scan_running = True
    try:
        scan = subprocess.run(
            [sys.executable, "-m", "scripts.grant_radar.scan"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
        )
        rep = subprocess.run(
            [sys.executable, "-m", "scripts.grant_radar.report"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        ok = scan.returncode == 0 and rep.returncode == 0
        if not ok:
            logger.warning("스캔/보고서 실패 scan=%s report=%s", scan.returncode, rep.returncode)
        return {"ok": ok, "scan_rc": scan.returncode, "report_rc": rep.returncode}
    except subprocess.TimeoutExpired:
        return {"ok": False, "reason": "timeout"}
    except Exception as e:
        logger.error("스캔 실행 오류: %s", e)
        return {"ok": False, "reason": "exec_error"}
    finally:
        _scan_running = False
