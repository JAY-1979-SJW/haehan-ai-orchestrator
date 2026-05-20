"""폴더 수집 정책 — 코드 하드코딩 분리.

폴더 발견(folder_discovery)과 수집 대상 결정(policy)을 분리한다.
정책은 dataclass 로 표현하며 JSON 직렬화 가능.

기본 정책:
  - 받은편지함, 스마트메일함 → 수집
  - 사용자 폴더, 스팸, 휴지통, 보낸/임시 → 제외
  - unknown 폴더 → 제외 (안전)
이 기본값은 사용자가 config 객체/파일로 덮어쓸 수 있다.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from pathlib import Path


# kind 상수
KIND_INBOX = "inbox"
KIND_SMART = "smart"
KIND_USER = "user"
KIND_SENT = "sent"
KIND_DRAFT = "draft"
KIND_SPAM = "spam"
KIND_TRASH = "trash"
KIND_ARCHIVE = "archive"
KIND_ALL = "all"
KIND_RECEIPT = "receipt"       # 수신확인
KIND_WRITE_TO_ME = "self_mail" # 내게쓴메일함
KIND_VIP = "vip"
KIND_OTHER = "other"
KIND_UNKNOWN = "unknown"

KNOWN_KINDS = frozenset({
    KIND_INBOX, KIND_SMART, KIND_USER, KIND_SENT, KIND_DRAFT,
    KIND_SPAM, KIND_TRASH, KIND_ARCHIVE, KIND_ALL,
    KIND_RECEIPT, KIND_WRITE_TO_ME, KIND_VIP, KIND_OTHER, KIND_UNKNOWN,
})


@dataclass
class FolderPolicy:
    """수집 정책. JSON 직렬화 가능."""
    collect_inbox: bool = True
    collect_smart_folders: bool = True
    collect_user_folders: bool = False
    collect_spam: bool = False
    collect_trash: bool = False
    collect_sent: bool = False
    collect_draft: bool = False
    collect_archive: bool = False
    collect_self_mail: bool = False
    collect_vip: bool = False
    include_folder_names: list[str] = field(default_factory=list)
    exclude_folder_names: list[str] = field(default_factory=list)
    include_unknown_folders: bool = False
    mask_folder_names_in_logs: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "FolderPolicy":
        return cls(**{k: d[k] for k in d if k in cls.__dataclass_fields__})

    @classmethod
    def from_json_file(cls, path: Path) -> "FolderPolicy":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


# 정책 평가 결과
INCLUDED = "included"
EXCLUDED_BY_POLICY = "policy_excluded"
INCLUDED_OVERRIDE = "included_override"
EXCLUDED_OVERRIDE = "excluded_override"
EXCLUDED_ZERO_UNREAD = "policy_excluded_zero_unread"
EXCLUDED_NO_ADAPTER = "excluded_no_adapter"


def _kind_to_flag(policy: FolderPolicy, kind: str) -> bool:
    """policy 의 해당 kind 수집 여부."""
    return {
        KIND_INBOX: policy.collect_inbox,
        KIND_SMART: policy.collect_smart_folders,
        KIND_USER: policy.collect_user_folders,
        KIND_SPAM: policy.collect_spam,
        KIND_TRASH: policy.collect_trash,
        KIND_SENT: policy.collect_sent,
        KIND_DRAFT: policy.collect_draft,
        KIND_ARCHIVE: policy.collect_archive,
        KIND_WRITE_TO_ME: policy.collect_self_mail,
        KIND_VIP: policy.collect_vip,
        KIND_UNKNOWN: policy.include_unknown_folders,
        KIND_OTHER: False,
        KIND_RECEIPT: False,
        KIND_ALL: False,  # 전체메일은 다른 폴더와 중복 — 별도 정책
    }.get(kind, False)


def evaluate(policy: FolderPolicy, *,
             name: str, kind: str, unread_count: int,
             folder_id: str = "", adapter: str = "") -> str:
    """폴더 1개에 대한 정책 평가 — 수집 여부 코드 반환."""
    # 1) 명시 override
    if policy.exclude_folder_names and name in policy.exclude_folder_names:
        return EXCLUDED_OVERRIDE
    if policy.include_folder_names and name in policy.include_folder_names:
        # zero unread 면서도 명시 include 면 included_override (수집은 시도)
        if unread_count == 0:
            return EXCLUDED_ZERO_UNREAD
        return INCLUDED_OVERRIDE
    # 2) kind 기반
    kind_allowed = _kind_to_flag(policy, kind)
    if not kind_allowed:
        return EXCLUDED_BY_POLICY
    # 3) zero unread
    if unread_count == 0:
        return EXCLUDED_ZERO_UNREAD
    # 4) adapter unavailable
    if adapter == "" or adapter == "unsupported_folder":
        return EXCLUDED_NO_ADAPTER
    # 5) folder_id 없음 (학습 실패)
    if not folder_id:
        return EXCLUDED_NO_ADAPTER
    return INCLUDED


# ── adapter 자동 선택 ───────────────────────────────────────────────

ADAPTER_URL_PAGE = "url_page"
ADAPTER_DIRECT_LINK = "direct_link_url_page"
ADAPTER_NEXT_ARROW = "next_arrow"
ADAPTER_SCROLL_LOAD_MORE = "scroll_load_more"
ADAPTER_UNSUPPORTED = "unsupported_folder"


def select_adapter(*, kind: str, folder_id: str, href_attr: str = "",
                   has_direct_link: bool = False) -> tuple[str, str]:
    """폴더에 가장 적합한 adapter 자동 선택.

    Returns (adapter, reason)
    """
    # inbox / smart / user / spam / trash 는 /v2/folders/{id}/unread 패턴 동일
    if folder_id and kind in (KIND_INBOX, KIND_SMART, KIND_USER,
                              KIND_SPAM, KIND_TRASH, KIND_SENT, KIND_DRAFT,
                              KIND_WRITE_TO_ME, KIND_RECEIPT):
        return (ADAPTER_URL_PAGE, f"folder_id={folder_id}_path_pattern")
    if has_direct_link:
        return (ADAPTER_DIRECT_LINK, "direct_link_present")
    if kind in (KIND_OTHER, KIND_UNKNOWN):
        return (ADAPTER_UNSUPPORTED, f"unknown_kind={kind}")
    if not folder_id:
        return (ADAPTER_UNSUPPORTED, "no_folder_id_learned")
    return (ADAPTER_UNSUPPORTED, "no_strategy_matched")
