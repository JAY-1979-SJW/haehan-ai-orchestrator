"""상세설명 생성·렌더링·템플릿 엔드포인트."""

from __future__ import annotations

import datetime
import json
import re
import sys

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from tools.gates.auth import require_role

from ...audit.audit_logger import log_event
from ._helpers import ROOT, tmpl_dir

router = APIRouter()


# ── 섹션 ─────────────────────────────────────────────────────────────────────


@router.get("/description/sections")
def api_description_sections(user: dict = Depends(require_role("admin", "owner"))) -> dict:
    sys.path.insert(0, str(ROOT))
    from scripts.naver.smartstore.product.page_builder import DEFAULT_SECTIONS, SECTION_REGISTRY

    return {
        "ok": True,
        "sections": [
            {"key": k, "label": v["label"], "required": v["required"], "data_keys": v["data_keys"]}
            for k, v in SECTION_REGISTRY.items()
        ],
        "default_sections": DEFAULT_SECTIONS,
    }


# ── 렌더링 ────────────────────────────────────────────────────────────────────


class DescriptionRenderRequest(BaseModel):
    sections: list[str]
    data: dict


@router.post("/description/render")
def api_description_render(
    body: DescriptionRenderRequest, user: dict = Depends(require_role("admin", "owner"))
) -> dict:
    sys.path.insert(0, str(ROOT))
    from scripts.naver.smartstore.product.page_builder import ProductPageBuilder

    try:
        builder = ProductPageBuilder()
        builder.select(body.sections)
        html = builder.render(body.data)
        log_event(
            "SMARTSTORE_DESCRIPTION_RENDER",
            task_id="-",
            actor=user["actor"],
            role=user["role"],
            decision="ok",
            note=f"sections={body.sections}",
        )
        return {"ok": True, "html": html, "sections": builder.sections}
    except Exception as e:  # noqa: BLE001 - 상세설명 렌더링/템플릿 관리 엔드포인트 — 렌더링/템플릿조회 실패 시 {ok: False, error}를 반환, 손상된 템플릿 파일은 건너뜀(이미 noqa: S112 존재). 템플릿 저장/삭제는 로컬 앱 데이터 파일(운영 DB 아님)이며 명시적 API 호출로만 수행됨.
        return {"ok": False, "error": str(e)}


# ── AI 생성 ───────────────────────────────────────────────────────────────────


class AIDescriptionRequest(BaseModel):
    data: dict
    model: str | None = None


@router.post("/description/ai-generate")
def api_description_ai_generate(
    body: AIDescriptionRequest, user: dict = Depends(require_role("admin", "owner"))
) -> dict:
    """앱 런타임 AI 생성 없음 — Claude Code(MCP)가 문구를 작성해 /description/render 로 렌더링하세요."""
    return {
        "ok": False,
        "error": "앱 런타임 AI 생성 없음 — Claude Code(MCP)가 문구를 작성해 /description/render 또는 templates/save 로 저장하세요.",
    }


class GptDescriptionRequest(BaseModel):
    data: dict
    images: list[str] = []
    model: str | None = None
    base: str | None = None  # 표준 템플릿 베이스(있으면 템플릿 기반 수정 모드)


@router.post("/description/gpt-generate")
def api_description_gpt_generate(
    body: GptDescriptionRequest, user: dict = Depends(require_role("admin", "owner"))
) -> dict:
    """삭제됨(GPT 전용 경로) — Claude Code(MCP)가 문구를 작성해 /description/render 로 렌더링하세요."""
    return {
        "ok": False,
        "error": "앱 런타임 AI 생성 없음 — Claude Code(MCP)가 문구를 작성해 /description/render 또는 templates/save 로 저장하세요.",
    }


# ── 템플릿 ────────────────────────────────────────────────────────────────────


class TemplateSaveRequest(BaseModel):
    name: str
    category: str
    sections: list[str]
    data: dict
    html: str
    source: str = "manual"


@router.get("/description/templates")
def api_templates_list(user: dict = Depends(require_role("admin", "owner"))) -> dict:
    d = tmpl_dir()
    templates = []
    for f in sorted(d.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            t = json.loads(f.read_text(encoding="utf-8"))
            templates.append(
                {
                    "id": f.stem,
                    "name": t.get("name", f.stem),
                    "category": t.get("category", ""),
                    "sections": t.get("sections", []),
                    "source": t.get("source", "manual"),
                    "created_at": t.get("created_at", ""),
                    "data": t.get("data", {}),
                }
            )
        except Exception:  # noqa: BLE001, S112 — 손상된 템플릿 파일은 조용히 건너뜀
            continue
    log_event(
        "SMARTSTORE_TEMPLATES_LIST",
        task_id="-",
        actor=user["actor"],
        role=user["role"],
        decision="ok",
        note=f"count={len(templates)}",
    )
    return {"ok": True, "templates": templates, "count": len(templates)}


@router.post("/description/templates/save")
def api_templates_save(body: TemplateSaveRequest, user: dict = Depends(require_role("admin", "owner"))) -> dict:
    d = tmpl_dir()
    safe = re.sub(r"[^\w가-힣]", "_", body.name)[:40]
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    tid = f"{safe}_{ts}"
    payload = {
        "id": tid,
        "name": body.name,
        "category": body.category,
        "sections": body.sections,
        "data": body.data,
        "html": body.html,
        "source": body.source,
        "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "created_by": user["actor"],
    }
    (d / f"{tid}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    log_event(
        "SMARTSTORE_TEMPLATE_SAVE",
        task_id="-",
        actor=user["actor"],
        role=user["role"],
        decision="ok",
        note=f"id={tid} name={body.name}",
    )
    return {"ok": True, "id": tid, "name": body.name}


@router.get("/description/templates/{template_id}")
def api_templates_get(template_id: str, user: dict = Depends(require_role("admin", "owner"))) -> dict:
    f = tmpl_dir() / f"{template_id}.json"
    if not f.exists():
        return {"ok": False, "error": "template_not_found"}
    try:
        t = json.loads(f.read_text(encoding="utf-8"))
        log_event(
            "SMARTSTORE_TEMPLATE_GET",
            task_id="-",
            actor=user["actor"],
            role=user["role"],
            decision="ok",
            note=f"id={template_id}",
        )
        return {"ok": True, **t}
    except Exception as e:  # noqa: BLE001 - 상세설명 렌더링/템플릿 관리 엔드포인트 — 렌더링/템플릿조회 실패 시 {ok: False, error}를 반환, 손상된 템플릿 파일은 건너뜀(이미 noqa: S112 존재). 템플릿 저장/삭제는 로컬 앱 데이터 파일(운영 DB 아님)이며 명시적 API 호출로만 수행됨.
        return {"ok": False, "error": str(e)}


@router.delete("/description/templates/{template_id}")
def api_templates_delete(template_id: str, user: dict = Depends(require_role("admin", "owner"))) -> dict:
    f = tmpl_dir() / f"{template_id}.json"
    if not f.exists():
        return {"ok": False, "error": "template_not_found"}
    f.unlink()
    log_event(
        "SMARTSTORE_TEMPLATE_DELETE",
        task_id="-",
        actor=user["actor"],
        role=user["role"],
        decision="ok",
        note=f"id={template_id}",
    )
    return {"ok": True, "id": template_id}
