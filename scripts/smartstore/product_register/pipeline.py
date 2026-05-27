"""Pipeline description for SmartStore product registration."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from scripts.smartstore.product_register.gates import APPROVAL_CONFIRM_TEXT, APPROVAL, PREPARE, READ


@dataclass(frozen=True)
class PipelineStep:
    step: str
    module: str
    stage: str
    action: str
    final_submit_blocked: bool = True
    requires: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_product_register_pipeline() -> dict[str, Any]:
    steps = [
        PipelineStep(
            "input_data",
            "scripts.smartstore.product_register.input_data",
            PREPARE,
            "input.load",
            notes=["Requires --data=<utf8-json-file>; inline/stdin Korean product data is blocked."],
        ),
        PipelineStep("session", "scripts.smartstore.product_register.session", READ, "session.select"),
        PipelineStep(
            "category_taxonomy",
            "scripts.smartstore.product_register.category_taxonomy",
            READ,
            "category.taxonomy.read",
            notes=["Offline cache first; live discovery may extend the same schema."],
        ),
        PipelineStep(
            "category_resolver",
            "scripts.smartstore.product_register.category_resolver",
            PREPARE,
            "category.resolve",
            notes=["Scores candidates and blocks low-confidence automatic selection."],
        ),
        PipelineStep("category", "scripts.smartstore.product_register.category", PREPARE, "category.select"),
        PipelineStep("detail_page", "scripts.smartstore.detail_page", PREPARE, "detail.write"),
        PipelineStep("image", "scripts.smartstore.product_register.image", PREPARE, "image.upload.prepare"),
        PipelineStep("required_fields", "scripts.smartstore.approved_product_workflow", PREPARE, "required_fields.prepare"),
        PipelineStep("draft", "scripts.smartstore.product_register.draft", PREPARE, "draft.fill"),
        PipelineStep(
            "approval",
            "scripts.smartstore.product_register.approval",
            APPROVAL,
            "product.save",
            final_submit_blocked=False,
            requires=["--approved", f"--confirm={APPROVAL_CONFIRM_TEXT}"],
        ),
    ]
    return {
        "workflow": "smartstore_product_register",
        "stage_order": [READ, PREPARE, APPROVAL],
        "steps": [step.to_dict() for step in steps],
        "gates": {
            "read": "page/session inspection only",
            "prepare": "may type, select, upload, and draft without final save/send/delete",
            "approval": f"requires --approved --confirm={APPROVAL_CONFIRM_TEXT}",
        },
    }
