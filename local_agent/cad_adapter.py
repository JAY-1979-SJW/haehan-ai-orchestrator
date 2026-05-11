"""Compatibility wrapper for the modular local CAD adapter."""

from .cad import READ_ONLY_TOOLS, autocad_ping, cad_execute, cad_ping, cad_status, is_read_only_tool

__all__ = [
    "READ_ONLY_TOOLS",
    "autocad_ping",
    "cad_execute",
    "cad_ping",
    "cad_status",
    "is_read_only_tool",
]
