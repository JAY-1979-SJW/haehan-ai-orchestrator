"""site_engine 공통 열거형 및 기본 타입."""
from __future__ import annotations

from enum import Enum


class ExecutionLocation(str, Enum):
    SERVER = "SERVER"
    LOCAL_AGENT = "LOCAL_AGENT"
    USER_DIRECT = "USER_DIRECT"


class GateDecision(str, Enum):
    READ_ONLY_ALLOWED = "READ_ONLY_ALLOWED"
    SERVER_BROWSER_ALLOWED = "SERVER_BROWSER_ALLOWED"
    LOCAL_AGENT_REQUIRED = "LOCAL_AGENT_REQUIRED"
    USER_DIRECT_REQUIRED = "USER_DIRECT_REQUIRED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    BLOCKED = "BLOCKED"


class SiteCapability(str, Enum):
    READ = "READ"
    SEARCH = "SEARCH"
    DOWNLOAD = "DOWNLOAD"
    FORM_FILL = "FORM_FILL"
    SUBMIT = "SUBMIT"
    UPLOAD = "UPLOAD"
    DELETE = "DELETE"
    PUBLISH = "PUBLISH"
    SEND = "SEND"
    SIGN = "SIGN"


class SiteActionKind(str, Enum):
    READ_ONLY = "READ_ONLY"
    WRITE = "WRITE"
    IRREVERSIBLE = "IRREVERSIBLE"


class SiteProfileStatus(str, Enum):
    ACTIVE = "ACTIVE"
    DEPRECATED = "DEPRECATED"
    STUB = "STUB"
