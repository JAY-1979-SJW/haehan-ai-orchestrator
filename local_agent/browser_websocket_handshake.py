"""Read-only WebSocket handshake protocol for browser agent.

정의된 handshake flow:
  agent.hello → server.ack → server.policy → agent.ready → heartbeat loop

- read-only mode 전용 (execute_click/execute_type 금지)
- 민감 정보 제거 (hostname/user/IP 원문 금지, hash만 사용)
- approval token / token hash 절대 포함 금지
- password / OTP 절대 포함 금지
- cookie / session / storage 절대 포함 금지
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class HandshakeMessageType(str, Enum):
    """Handshake message type enumeration."""

    AGENT_HELLO = "agent.hello"
    AGENT_READY = "agent.ready"
    AGENT_HEARTBEAT = "agent.heartbeat"
    SERVER_ACK = "server.ack"
    SERVER_POLICY = "server.policy"
    SERVER_NOOP = "server.noop"
    AGENT_STATUS = "agent.status"


class HandshakeMode(str, Enum):
    """Agent operational mode."""

    READ_ONLY = "read_only"
    FULL = "full"


class Capability(str, Enum):
    """Agent capabilities in read-only mode."""

    BROWSER_INSPECT = "browser.inspect"
    BROWSER_PLAN_CLICK = "browser.plan_click"
    BROWSER_PLAN_TYPE = "browser.plan_type"
    SYSTEM_INFO = "system.info"
    LIST_ALLOWED_APPS = "list.allowed_apps"
    OPEN_URL = "open.url"


def safe_dict(data: dict) -> dict:
    """Remove forbidden fields from dict recursively.

    Forbidden fields:
      - approval_token, final_approval_token
      - token_hash
      - password, otp
      - cookie, session, authorization
      - localStorage, sessionStorage
      - typed_text, raw base64, full_dom
      - hostname, username, ip (raw values only; hashes are safe)
      - machine_id (raw value; hash is safe)
    """
    forbidden_patterns = {
        "approval_token",
        "final_approval_token",
        "token_hash",
        "password",
        "otp",
        "cookie",
        "session",
        "authorization",
        "localstorage",
        "sessionstorage",
        "typed_text",
        "base64",
        "full_dom",
        "raw_html",
        "raw_dom",
        "hostname",
        "username",
        "user_name",
        "ip_address",
        "machine_id",
        "device_id",
    }

    def _clean(obj: Any) -> Any:
        if isinstance(obj, dict):
            return {k: _clean(v) for k, v in obj.items() if k.lower() not in forbidden_patterns}
        elif isinstance(obj, (list, tuple)):
            return type(obj)(_clean(item) for item in obj)
        return obj

    return _clean(data)


def _iso8601_now() -> str:
    """Return current UTC time in ISO 8601 format."""
    return datetime.now(UTC).isoformat()


@dataclass
class AgentHelloMessage:
    """Agent handshake hello message.

    Fields:
      - message_type: always "agent.hello"
      - agent_id: unique agent identifier
      - agent_version: agent software version
      - host_name_hash: SHA256 hash of hostname (never raw hostname)
      - capabilities: list of capabilities in read_only mode
      - mode: operational mode (read_only only)
      - audit_enabled: whether audit logging is enabled
      - approval_required: whether approval is required for high-risk tasks
      - organization_id: (TENANT-3) agent organization scope
      - registration_user_id: (TENANT-3) optional, agent registration user
      - timestamp: UTC ISO 8601 timestamp
    """

    message_type: str = HandshakeMessageType.AGENT_HELLO.value
    agent_id: str = ""
    agent_version: str = ""
    host_name_hash: str = ""
    capabilities: list[str] = field(
        default_factory=lambda: [
            Capability.BROWSER_INSPECT.value,
            Capability.BROWSER_PLAN_CLICK.value,
            Capability.BROWSER_PLAN_TYPE.value,
        ]
    )
    mode: str = HandshakeMode.READ_ONLY.value
    audit_enabled: bool = True
    approval_required: bool = True
    organization_id: str = ""  # TENANT-3: organization scope
    registration_user_id: str | None = None  # TENANT-3: optional registration user
    timestamp: str = field(default_factory=_iso8601_now)

    def to_dict(self) -> dict:
        """Convert to dict."""
        return asdict(self)

    def to_json_str(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict())

    def safe_dict(self) -> dict:
        """Return dict with sensitive fields removed."""
        d = self.to_dict()
        return safe_dict(d)


@dataclass
class ServerPolicyMessage:
    """Server policy message (read-only).

    Fields:
      - message_type: always "server.policy"
      - mode: operational mode (read_only only)
      - allow_execute: whether to allow browser execute (always False)
      - allow_submit: whether to allow form submit (always False)
      - allow_password_input: whether to allow password input (always False)
      - allow_otp_input: whether to allow OTP input (always False)
      - require_approval: whether approval is required (always True)
      - heartbeat_interval_sec: recommended heartbeat interval in seconds
      - organization_id: (TENANT-3) agent organization scope (echo from agent.hello)
      - agent_id: (TENANT-3) agent identifier (echo from agent.hello)
      - timestamp: UTC ISO 8601 timestamp
    """

    message_type: str = HandshakeMessageType.SERVER_POLICY.value
    mode: str = HandshakeMode.READ_ONLY.value
    allow_execute: bool = False
    allow_submit: bool = False
    allow_password_input: bool = False
    allow_otp_input: bool = False
    require_approval: bool = True
    heartbeat_interval_sec: int = 30
    organization_id: str = ""  # TENANT-3: echo from agent.hello
    agent_id: str = ""  # TENANT-3: echo from agent.hello
    timestamp: str = field(default_factory=_iso8601_now)

    def to_dict(self) -> dict:
        """Convert to dict."""
        return asdict(self)

    def to_json_str(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict())

    def safe_dict(self) -> dict:
        """Return dict with sensitive fields removed."""
        return safe_dict(self.to_dict())


@dataclass
class AgentHeartbeatMessage:
    """Agent heartbeat message.

    Fields:
      - message_type: always "agent.heartbeat"
      - agent_id: agent identifier
      - status: current agent status (ready, busy, error)
      - mode: operational mode (read_only only)
      - pending_tasks: number of pending tasks
      - last_error: last error message (safe summary only, no secrets)
      - timestamp: UTC ISO 8601 timestamp
    """

    message_type: str = HandshakeMessageType.AGENT_HEARTBEAT.value
    agent_id: str = ""
    status: str = "ready"
    mode: str = HandshakeMode.READ_ONLY.value
    pending_tasks: int = 0
    last_error: str | None = None
    timestamp: str = field(default_factory=_iso8601_now)

    def to_dict(self) -> dict:
        """Convert to dict."""
        return asdict(self)

    def to_json_str(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict())

    def safe_dict(self) -> dict:
        """Return dict with sensitive fields removed."""
        return safe_dict(self.to_dict())


def _validate_hello_details(msg: dict) -> tuple[bool, str | None]:
    """agent.hello 의 capabilities / tenant 필드 / raw hostname 검사 (순서 고정)."""
    capabilities = msg.get("capabilities") or []
    if not isinstance(capabilities, list):
        return False, "capabilities must be list"

    # TENANT-3: Check organization_id (recommended but optional for backward compatibility)
    org_id = msg.get("organization_id", "")
    if org_id and not isinstance(org_id, str):
        return False, "organization_id must be string"

    # TENANT-3: Check registration_user_id (optional)
    reg_user_id = msg.get("registration_user_id")
    if reg_user_id and not isinstance(reg_user_id, str):
        return False, "registration_user_id must be string"

    # Check that no raw hostname/user/IP is present
    msg_str = json.dumps(msg).lower()
    if any(x in msg_str for x in ["hostname=", "user=", "ip="] if "hash" not in msg_str):
        # Simple check: if we find hostname= but not hostname_hash, flag it
        if "hostname=" in msg_str and "hostname_hash" not in msg_str:
            return False, "raw hostname not allowed; use host_name_hash"

    return True, None


def validate_agent_hello_message(msg: dict) -> tuple[bool, str | None]:
    """Validate agent.hello message.

    TENANT-3: Validate organization_id and registration_user_id fields.

    Returns:
      (is_valid, error_message)
    """
    if not isinstance(msg, dict):
        return False, "message must be dict"

    if msg.get("message_type") != HandshakeMessageType.AGENT_HELLO.value:
        return False, f"invalid message_type: {msg.get('message_type')}"

    # Check for forbidden fields FIRST (before mode check)
    forbidden = {
        "approval_token",
        "final_approval_token",
        "token_hash",
        "password",
        "otp",
        "cookie",
        "session",
        "authorization",
        "localstorage",
        "sessionstorage",
        "typed_text",
        "base64",
    }
    for key in msg:
        if key.lower() in forbidden:
            return False, f"forbidden field: {key}"

    if not msg.get("agent_id"):
        return False, "agent_id required"

    if not msg.get("agent_version"):
        return False, "agent_version required"

    mode = msg.get("mode", HandshakeMode.READ_ONLY.value)
    if mode != HandshakeMode.READ_ONLY.value:
        return False, f"only read_only mode supported: {mode}"

    return _validate_hello_details(msg)


def validate_server_policy_message(msg: dict) -> tuple[bool, str | None]:
    """Validate server.policy message for read-only mode.

    Returns:
      (is_valid, error_message)
    """
    if not isinstance(msg, dict):
        return False, "message must be dict"

    if msg.get("message_type") != HandshakeMessageType.SERVER_POLICY.value:
        return False, f"invalid message_type: {msg.get('message_type')}"

    mode = msg.get("mode")
    if mode != HandshakeMode.READ_ONLY.value:
        return False, f"only read_only mode supported: {mode}"

    # Read-only mode: these must all be False/True as specified
    if msg.get("allow_execute") is not False:
        return False, "allow_execute must be False in read_only mode"

    if msg.get("allow_submit") is not False:
        return False, "allow_submit must be False in read_only mode"

    if msg.get("allow_password_input") is not False:
        return False, "allow_password_input must be False in read_only mode"

    if msg.get("allow_otp_input") is not False:
        return False, "allow_otp_input must be False in read_only mode"

    if msg.get("require_approval") is not True:
        return False, "require_approval must be True in read_only mode"

    heartbeat_interval = msg.get("heartbeat_interval_sec", 30)
    if not isinstance(heartbeat_interval, int) or heartbeat_interval < 5:
        return False, "heartbeat_interval_sec must be int >= 5"

    return True, None


def validate_agent_heartbeat_message(msg: dict) -> tuple[bool, str | None]:
    """Validate agent.heartbeat message.

    Returns:
      (is_valid, error_message)
    """
    if not isinstance(msg, dict):
        return False, "message must be dict"

    if msg.get("message_type") != HandshakeMessageType.AGENT_HEARTBEAT.value:
        return False, f"invalid message_type: {msg.get('message_type')}"

    if not msg.get("agent_id"):
        return False, "agent_id required"

    status = msg.get("status", "")
    if status not in ("ready", "busy", "error"):
        return False, f"invalid status: {status}"

    mode = msg.get("mode")
    if mode != HandshakeMode.READ_ONLY.value:
        return False, f"only read_only mode supported: {mode}"

    pending = msg.get("pending_tasks", 0)
    if not isinstance(pending, int) or pending < 0:
        return False, "pending_tasks must be non-negative int"

    last_error = msg.get("last_error")
    if last_error is not None and not isinstance(last_error, str):
        return False, "last_error must be string or null"

    # Check for forbidden fields in error message
    if last_error:
        forbidden = {
            "approval_token",
            "final_approval_token",
            "token_hash",
            "password",
            "otp",
            "cookie",
            "session",
            "authorization",
        }
        if any(f in last_error.lower() for f in forbidden):
            return False, "forbidden field in last_error"

    return True, None


def validate_handshake_message(msg: dict) -> tuple[bool, str | None]:
    """Validate any handshake message.

    Returns:
      (is_valid, error_message)
    """
    if not isinstance(msg, dict):
        return False, "message must be dict"

    msg_type = msg.get("message_type", "")
    if msg_type == HandshakeMessageType.AGENT_HELLO.value:
        return validate_agent_hello_message(msg)
    elif msg_type == HandshakeMessageType.SERVER_POLICY.value:
        return validate_server_policy_message(msg)
    elif msg_type == HandshakeMessageType.AGENT_HEARTBEAT.value:
        return validate_agent_heartbeat_message(msg)
    else:
        return False, f"unknown message_type: {msg_type}"


__all__ = [
    "AgentHeartbeatMessage",
    "AgentHelloMessage",
    "Capability",
    "HandshakeMessageType",
    "HandshakeMode",
    "ServerPolicyMessage",
    "safe_dict",
    "validate_agent_heartbeat_message",
    "validate_agent_hello_message",
    "validate_handshake_message",
    "validate_server_policy_message",
]
