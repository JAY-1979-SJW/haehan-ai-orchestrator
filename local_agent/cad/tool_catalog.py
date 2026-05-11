"""Read-only CAD tool catalog for local agent execution."""

from __future__ import annotations

from typing import Any


READ_ONLY_TOOLS: dict[str, tuple[str, str]] = {
    "active_document.info": ("active_document_tools", "get_active_document_info"),
    "layer.list": ("layer_tools", "list_layers"),
    "block.list": ("block_tools", "list_blocks"),
    "block_reference.list": ("block_tools", "list_block_references"),
    "entity.list": ("entity_tools", "list_modelspace_entities"),
    "text.list": ("text_tools", "list_text_entities"),
    "geometry.list": ("geometry_tools", "list_geometry_entities"),
    "dimension.list": ("dimension_tools", "list_dimension_entities"),
    "drawing.search": ("drawing_file_tools", "search_drawings"),
}


LIMIT_TOOLS = {
    "block_reference.list",
    "entity.list",
    "text.list",
    "geometry.list",
    "dimension.list",
}


def is_read_only_tool(tool_id: str) -> bool:
    return normalize_tool_id(tool_id) in READ_ONLY_TOOLS


def normalize_tool_id(tool_id: str) -> str:
    return (tool_id or "").strip().lower()


def get_tool_binding(tool_id: str) -> tuple[str, str] | None:
    return READ_ONLY_TOOLS.get(normalize_tool_id(tool_id))


def build_call_args(tool_id: str, args: dict[str, Any]) -> list[Any]:
    normalized = normalize_tool_id(tool_id)
    if normalized in LIMIT_TOOLS:
        return [int(args.get("limit", 100))]
    if normalized == "drawing.search":
        return [str(args.get("query", ""))]
    return []
