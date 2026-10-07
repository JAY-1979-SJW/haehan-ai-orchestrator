"""
정부공고 첨부파일 자동분석 실행 API

GET  /api/v1/notices/daily-sites
POST /api/v1/notices/analyze-current-browser
POST /api/v1/notices/analyze-url
POST /api/v1/notices/analyze-folder
GET  /api/v1/notices/health
"""

from __future__ import annotations

import os
from pathlib import Path

from flask import Blueprint, jsonify, request

from notice_radar import analyze_current_browser_notice, analyze_notice_folder, analyze_notice_url
from notice_radar.site_profiles import get_daily_briefing_sites, get_site_profile

notice_bp = Blueprint("notices", __name__, url_prefix="/api/v1/notices")

_BASE_DIR = Path(__file__).resolve().parent
_DEFAULT_OUTPUT_ROOT = _BASE_DIR / "storage" / "notices"
_ALLOWED_LOCAL_ROOTS = [
    _BASE_DIR / "storage" / "notices",
    _BASE_DIR / "storage" / "uploads",
    _BASE_DIR / "storage" / "inbox_attachments",
]
_DEFAULT_CDP_URL = os.environ.get("NOTICE_RADAR_CDP_URL", "http://127.0.0.1:9222")


def _ok(payload: dict, code: int = 200):
    return jsonify({"status": "ok", **payload}), code


def _error(message: str, code: int = 400):
    return jsonify({"status": "error", "message": message}), code


def _safe_output_root(value: str | None) -> Path:
    if not value:
        return _DEFAULT_OUTPUT_ROOT
    path = Path(value)
    if not path.is_absolute():
        path = _BASE_DIR / path
    path = path.resolve()
    storage_root = (_BASE_DIR / "storage").resolve()
    if storage_root not in path.parents and path != storage_root:
        raise ValueError("output_root must be inside storage/")
    return path


def _safe_local_folder(value: str) -> Path:
    if not value:
        raise ValueError("folder is required")
    path = Path(value)
    if not path.is_absolute():
        path = _BASE_DIR / path
    path = path.resolve()
    allowed = [root.resolve() for root in _ALLOWED_LOCAL_ROOTS]
    if not any(path == root or root in path.parents for root in allowed):
        raise ValueError("folder must be inside storage/notices, storage/uploads, or storage/inbox_attachments")
    if not path.exists() or not path.is_dir():
        raise ValueError(f"folder not found: {path}")
    return path


@notice_bp.route("/health", methods=["GET"])
def health():
    return _ok({"service": "notice_radar", "output_root": str(_DEFAULT_OUTPUT_ROOT), "cdp_url": _DEFAULT_CDP_URL})


@notice_bp.route("/daily-sites", methods=["GET"])
def daily_sites():
    return _ok({"sites": get_daily_briefing_sites()})


@notice_bp.route("/analyze-current-browser", methods=["POST"])
def analyze_current_browser_route():
    data = request.get_json(silent=True) or {}
    site_key = data.get("site_key") or ""
    site = get_site_profile(site_key) if site_key else None
    try:
        output_root = _safe_output_root(data.get("output_root"))
        analysis = analyze_current_browser_notice(
            cdp_url=data.get("cdp_url") or _DEFAULT_CDP_URL,
            source=data.get("source") or (site.name if site else "current-browser"),
            title=data.get("title") or None,
            output_root=output_root,
            target_url_contains=data.get("target_url_contains") or (site.target_url_contains if site else None),
            click_downloads=bool(data.get("click_downloads", True)),
            max_clicks=int(data.get("max_clicks", 20)),
        )
    except Exception as exc:  # noqa: BLE001 - 공고 분석 FastAPI 라우터 — 분석 실패 시 500 에러 응답(_error)으로 안전하게 반환할 뿐 쓰기/승인 우회 없음
        return _error(f"current browser notice analysis failed: {type(exc).__name__}: {exc}", 500)

    return _ok({"analysis": analysis.to_dict(), "summary_markdown": analysis.to_markdown()})


@notice_bp.route("/analyze-url", methods=["POST"])
def analyze_url_route():
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    if not url.startswith(("http://", "https://")):
        return _error("valid http(s) url is required", 400)

    source = data.get("source") or "public-notice"
    title = data.get("title") or None
    try:
        output_root = _safe_output_root(data.get("output_root"))
        analysis = analyze_notice_url(url, source=source, title=title, output_root=output_root)
    except Exception as exc:  # noqa: BLE001 - 공고 분석 FastAPI 라우터 — 분석 실패 시 500 에러 응답(_error)으로 안전하게 반환할 뿐 쓰기/승인 우회 없음
        return _error(f"notice analysis failed: {type(exc).__name__}: {exc}", 500)

    return _ok({"analysis": analysis.to_dict(), "summary_markdown": analysis.to_markdown()})


@notice_bp.route("/analyze-folder", methods=["POST"])
def analyze_folder_route():
    data = request.get_json(silent=True) or {}
    folder = data.get("folder") or ""
    title = data.get("title") or ""
    if not title.strip():
        return _error("title is required", 400)

    try:
        folder_path = _safe_local_folder(folder)
        analysis = analyze_notice_folder(
            folder_path,
            title=title,
            source=data.get("source") or "local-folder",
            url=data.get("url") or "local://notice-folder",
        )
    except Exception as exc:  # noqa: BLE001 - 공고 분석 FastAPI 라우터 — 분석 실패 시 500 에러 응답(_error)으로 안전하게 반환할 뿐 쓰기/승인 우회 없음
        return _error(f"notice folder analysis failed: {type(exc).__name__}: {exc}", 500)

    return _ok({"analysis": analysis.to_dict(), "summary_markdown": analysis.to_markdown()})
