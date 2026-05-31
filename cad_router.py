"""CAD 물량산출 Blueprint — /api/v1/cad/*

CAD 파싱 서버(mcp_server)와 연동해 도면 파싱·연결맵·물량 결과를 제공한다.

엔드포인트:
    GET  /api/v1/cad/projects              — 프로젝트 목록
    GET  /api/v1/cad/<project>/status      — 공종별 파싱 현황
    POST /api/v1/cad/<project>/parse       — 1차 공통 파싱 실행
    GET  /api/v1/cad/<project>/rooms       — 실 목록 + 면적
    GET  /api/v1/cad/<project>/drawing/<no> — 단일 도면 연결맵
    POST /api/v1/cad/<project>/analyze     — GPT-mini AI 분석
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

from flask import Blueprint, jsonify, request

# CAD 파싱 서버 경로 주입
_CAD_SERVER_PATH = os.environ.get("CAD_SERVER_PATH", r"C:\work\03. cad-program")
if _CAD_SERVER_PATH not in sys.path:
    sys.path.insert(0, _CAD_SERVER_PATH)

log = logging.getLogger("cad_router")

cad_bp = Blueprint("cad", __name__, url_prefix="/api/v1/cad")


# ── 헬퍼 ─────────────────────────────────────────────────────────────────────


def _get_cache_dir(project: str, discipline: str) -> Path:
    from mcp_server.data_paths import _normalize_discipline, get_cache_dir

    return get_cache_dir(project, _normalize_discipline(discipline))


def _error(msg: str, code: int = 400):
    return jsonify({"error": msg}), code


# ── 엔드포인트 ────────────────────────────────────────────────────────────────


@cad_bp.get("/projects")
def list_projects():
    """등록된 프로젝트 목록."""
    try:
        from mcp_server.data_paths import DATA_ROOT

        proj_dir = Path(DATA_ROOT) / "프로젝트"
        if not proj_dir.exists():
            return jsonify([])
        projects = [d.name for d in proj_dir.iterdir() if d.is_dir()]
        return jsonify(projects)
    except Exception as e:
        return _error(str(e))


@cad_bp.get("/<project>/status")
def project_status(project: str):
    """공종별 파싱 현황 — 캐시 파일 수 + 상태 파일."""
    discipline = request.args.get("discipline", "건축")
    try:
        cache_dir = _get_cache_dir(project, discipline)
        cache_files = list(cache_dir.rglob("*_cache.json")) if cache_dir.exists() else []

        status_file = cache_dir.parent / "parse_status_common.json"
        status = json.loads(status_file.read_text(encoding="utf-8")) if status_file.exists() else {}

        drawings = status.get("drawings", {})
        ok = sum(1 for v in drawings.values() if v.get("status") == "✅")
        failed = sum(1 for v in drawings.values() if v.get("status") == "❌")
        pending = len(cache_files) - ok - failed

        return jsonify(
            {
                "project": project,
                "discipline": discipline,
                "cache_count": len(cache_files),
                "parsed": ok,
                "failed": failed,
                "pending": pending,
                "updated_at": status.get("updated_at", ""),
            }
        )
    except Exception as e:
        return _error(str(e))


@cad_bp.post("/<project>/parse")
def parse_project(project: str):
    """1차 공통 파싱 실행 (비동기 — 즉시 수락, 백그라운드 실행)."""
    body = request.get_json(force=True, silent=True) or {}
    discipline = body.get("discipline", "건축")
    limit = int(body.get("limit", 0))
    run_ai = bool(body.get("run_ai", True))

    try:
        from mcp_server.data_paths import _normalize_discipline, get_cache_dir
        from mcp_server.tools.architectural.arch_parse_all_tools import (
            _parse_one_common,
        )

        cache_dir = get_cache_dir(project, _normalize_discipline(discipline))
        cache_files = sorted(cache_dir.rglob("*_cache.json")) if cache_dir.exists() else []
        if limit:
            cache_files = cache_files[:limit]

        results = []
        for cf in cache_files:
            no = cf.parent.name if cf.parent != cache_dir else cf.stem.replace("_cache", "")
            r = _parse_one_common(project, no, discipline, run_ai=run_ai)
            results.append({"drawing_no": no, **r})

        ok = sum(1 for r in results if r.get("status") == "✅")
        failed = sum(1 for r in results if r.get("status") == "❌")
        return jsonify(
            {
                "project": project,
                "discipline": discipline,
                "total": len(results),
                "ok": ok,
                "failed": failed,
                "results": results[:20],
            }
        )
    except Exception as e:
        log.exception("parse 실패: %s", e)
        return _error(str(e), 500)


@cad_bp.get("/<project>/rooms")
def list_rooms(project: str):
    """실 목록 + 면적 — trace_rooms 결과."""
    discipline = request.args.get("discipline", "건축")
    drawing_no = request.args.get("drawing_no", "")
    min_area = float(request.args.get("min_area", 0.5))

    try:
        from mcp_server.data_paths import _normalize_discipline, get_cache_dir
        from mcp_server.parsers.architectural.drawing_context_builder import build_context
        from mcp_server.tools.architectural.arch_parse_all_tools import _normalize_cache_format

        cache_dir = get_cache_dir(project, _normalize_discipline(discipline))

        # 캐시 파일 탐색
        cache_file = None
        if drawing_no:
            short = drawing_no.split(" ")[0]
            for sub in cache_dir.iterdir() if cache_dir.exists() else []:
                if sub.is_dir() and sub.name.startswith(short):
                    hits = list(sub.glob("*_cache.json"))
                    if hits:
                        cache_file = hits[0]
                        break
            if not cache_file:
                for f in cache_dir.glob(f"{short}*_cache.json"):
                    cache_file = f
                    break

        if not cache_file:
            return _error("캐시 없음 — drawing_no를 확인하거나 먼저 /parse 실행", 404)

        cache_data = json.loads(cache_file.read_text(encoding="utf-8"))
        if "entities" in cache_data and "lines" not in cache_data:
            cache_data = _normalize_cache_format(cache_data)

        ctx = build_context(project, drawing_no, cache_data, run_ai_inspect=False)
        rooms = [r for r in ctx.get("traced_rooms", []) if r["area_m2"] >= min_area]

        return jsonify(
            {
                "project": project,
                "drawing_no": drawing_no,
                "discipline": discipline,
                "room_count": len(rooms),
                "total_area_m2": round(sum(r["area_m2"] for r in rooms), 2),
                "rooms": [
                    {
                        "label": r.get("label", ""),
                        "area_m2": r["area_m2"],
                        "area_net_m2": r.get("area_m2_net", r["area_m2"]),
                        "wall_thickness_mm": r.get("wall_thickness_mm"),
                        "layer": r.get("layer", ""),
                        "centroid": [r.get("centroid_x", 0), r.get("centroid_y", 0)],
                        "texts": [t["text"] for t in r.get("texts_inside", [])],
                        "blocks": len(r.get("blocks_inside", [])),
                        "dims": len(r.get("dims_inside", [])),
                    }
                    for r in rooms
                ],
            }
        )
    except Exception as e:
        log.exception("rooms 실패: %s", e)
        return _error(str(e), 500)


@cad_bp.post("/<project>/analyze")
def analyze_drawing(project: str):
    """GPT-mini AI 분석."""
    body = request.get_json(force=True, silent=True) or {}
    drawing_no = body.get("drawing_no", "")
    discipline = body.get("discipline", "건축")

    if not drawing_no:
        return _error("drawing_no 필수")

    try:
        from mcp_server.tools.architectural.arch_parse_all_tools import _parse_one_common

        result = _parse_one_common(project, drawing_no, discipline, run_ai=True)
        return jsonify(result)
    except Exception as e:
        return _error(str(e), 500)
