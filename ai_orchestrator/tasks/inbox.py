import json
import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

from ..core.config import INBOX_PATH as _INBOX_PATH

logger = logging.getLogger(__name__)


@dataclass
class InboxItem:
    item_id: str
    source_type: str  # telegram_command | email | manual | ...
    source_account: str  # telegram_user_id, email address, etc.
    external_id: str  # token_id, message_id, etc.
    sender: str  # actor name
    title: str
    body_raw: str
    body_summary: str
    received_at: str
    saved_at: str
    status: str  # new | reviewed | task_created | archived
    linked_task_id: str
    metadata: dict = field(default_factory=dict)


def create_inbox_item(  # noqa: PLR0913 - 공개 시그니처 유지(호출부 다수, 인자 묶음 변경 시 API 영향)
    source_type: str,
    source_account: str = "",
    external_id: str = "",
    sender: str = "",
    title: str = "",
    body_raw: str = "",
    body_summary: str = "",
    linked_task_id: str = "",
    metadata: dict | None = None,
) -> InboxItem:
    now = datetime.now(UTC).isoformat()
    item = InboxItem(
        item_id=str(uuid.uuid4()),
        source_type=source_type,
        source_account=source_account,
        external_id=external_id,
        sender=sender,
        title=title,
        body_raw=body_raw,
        body_summary=body_summary,
        received_at=now,
        saved_at=now,
        status="new",
        linked_task_id=linked_task_id,
        metadata=metadata or {},
    )
    _append(item)
    return item


def get_inbox_item(item_id: str) -> InboxItem | None:
    for d in _read_all():
        if d.get("item_id") == item_id:
            return InboxItem(**d)
    return None


def exists_by_external_id(external_id: str, source_type: str = "") -> bool:
    """외부 ID 중복 여부 확인. source_type 지정 시 해당 타입 내에서만 검사."""
    for d in _read_all():
        if d.get("external_id") == external_id and (not source_type or d.get("source_type") == source_type):
            return True
    return False


def read_recent_inbox(limit: int = 20) -> list[dict]:
    all_items = _read_all()
    return all_items[-limit:] if len(all_items) > limit else all_items


def _append(item: InboxItem) -> None:
    try:
        _INBOX_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _INBOX_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(item), ensure_ascii=False) + "\n")
    except OSError as e:
        logger.error("inbox 저장 실패: %s", e)


def _read_all() -> list[dict]:
    if not _INBOX_PATH.exists():
        return []
    try:
        lines = _INBOX_PATH.read_text(encoding="utf-8").strip().splitlines()
    except OSError as e:
        logger.error("inbox 읽기 실패: %s", e)
        return []
    result = []
    for line in lines:
        if not line.strip():
            continue
        try:
            result.append(json.loads(line))
        except json.JSONDecodeError as e:
            logger.warning("inbox 파싱 실패: %s", e)
    return result
