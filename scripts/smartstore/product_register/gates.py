"""Stage gates for SmartStore product registration."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

READ = "read"
PREPARE = "prepare"
APPROVAL = "approval"

APPROVAL_CONFIRM_TEXT = "SMARTSTORE_APPROVED_SUBMIT"

STAGE_ACTIONS: dict[str, set[str]] = {
    READ: {
        "session.select",
        "page.inspect",
        "product.list",
        "review.list",
        "inquiry.list",
        "category.taxonomy.read",
    },
    PREPARE: {
        "input.load",
        "category.resolve",
        "category.select",
        "detail.write",
        "image.prepare",
        "image.upload.prepare",
        "required_fields.prepare",
        "draft.fill",
        "customer.reply.draft",
    },
    APPROVAL: {
        "product.save",
        "product.update_save",
        "product.delete",
        "product.group_unlink",
        "review.reply.send",
        "inquiry.reply.send",
        "talk.message.send",
    },
}

STATE_CHANGING_TOKENS = (
    "save",
    "submit",
    "send",
    "delete",
    "approve",
    "cancel",
    "저장",
    "등록",
    "발송",
    "삭제",
    "승인",
    "취소",
)

CUSTOMER_COMMUNICATION_ACTIONS = {
    "review.reply.send",
    "inquiry.reply.send",
    "talk.message.send",
}


@dataclass(frozen=True)
class GateResult:
    ok: bool
    stage: str
    action: str
    code: str = "ok"
    requires: list[str] | None = None
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "stage": self.stage,
            "action": self.action,
            "code": self.code,
            "requires": list(self.requires or []),
            "message": self.message,
        }


def classify_action(action: str) -> str:
    for stage, actions in STAGE_ACTIONS.items():
        if action in actions:
            return stage
    lowered = action.lower()
    if any(token.lower() in lowered for token in STATE_CHANGING_TOKENS):
        return APPROVAL
    return PREPARE


def check_action(
    action: str,
    *,
    approved: bool = False,
    confirm: str = "",
) -> GateResult:
    stage = classify_action(action)
    if stage != APPROVAL:
        return GateResult(ok=True, stage=stage, action=action)
    requires = ["--approved", f"--confirm={APPROVAL_CONFIRM_TEXT}"]
    if approved and confirm == APPROVAL_CONFIRM_TEXT:
        return GateResult(ok=True, stage=stage, action=action, requires=requires)
    message = "Approval required for SmartStore state-changing action."
    if action in CUSTOMER_COMMUNICATION_ACTIONS:
        message = "AI may draft customer replies, but final send/register requires approval."
    return GateResult(
        ok=False,
        stage=stage,
        action=action,
        code="approval_required",
        requires=requires,
        message=message,
    )


def require_action(action: str, *, approved: bool = False, confirm: str = "") -> GateResult:
    result = check_action(action, approved=approved, confirm=confirm)
    if not result.ok:
        raise PermissionError(result.message)
    return result


def check_category_resolution(resolution: dict[str, Any]) -> GateResult:
    if resolution.get("auto_select_allowed"):
        return GateResult(ok=True, stage=PREPARE, action="category.resolve")
    return GateResult(
        ok=False,
        stage=PREPARE,
        action="category.resolve",
        code="manual_review_required",
        message="Category confidence is too low for automatic selection.",
    )
