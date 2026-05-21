"""Local agent CAD adapter package."""

from .controller_loader import cad_ping, cad_status
from .executor import cad_execute
from .tool_catalog import READ_ONLY_TOOLS, is_read_only_tool
from .backend_ping import autocad_ping
# CAD-AGENT-CAD-CONTROL-COMMAND-CONTRACT-01 — schema/contract only.
from .command_contract import (
    CadAgentCommand,
    CadCommandValidator,
    DEFAULT_REGISTRY as CAD_COMMAND_REGISTRY,
    RiskLevel,
)
from .command_approval import DEFAULT_APPROVAL_STORE as CAD_APPROVAL_STORE

__all__ = [
    "READ_ONLY_TOOLS",
    "autocad_ping",
    "cad_execute",
    "cad_ping",
    "cad_status",
    "is_read_only_tool",
    # Command contract layer (실행 0건 — schema only)
    "CadAgentCommand",
    "CadCommandValidator",
    "CAD_COMMAND_REGISTRY",
    "RiskLevel",
    "CAD_APPROVAL_STORE",
]
