"""L1 Shared Contracts — 작업 기록 저장소(Work Record Store, WRS) 도메인 모델 (순수 타입·규칙).

기준서: docs/specs/2026-10-05_work_record_store.md (M1, §3 데이터 모델 / §7 보안)

- I/O·DB·환경변수·시계·외부 호출이 없다. 시각은 호출자(L7)가 문자열로 넘긴다.
- 상태 Enum·전이 허용표·kind 허용목록·화이트리스트·검증 함수·엔티티(dataclass)·6a 호출 규약 Protocol 만 둔다.
- 값은 기본 미저장: 허용 필드 화이트리스트 밖 키·과대 크기·쿼리/자격증명이 든 URL 은 거부한다(마스킹 본체는 M2).
- 업무 식별자: job 은 `job_id`, 지도의 업무 항목은 `task_key`. `task_id` 는 audit_logger 정합용 연결 키에만 쓴다.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol
from urllib.parse import urlsplit

# ── 오류 ─────────────────────────────────────────────────────────────────


class WorkRecordError(Exception):
    """WRS 공통 예외."""


class ValidationError(WorkRecordError, ValueError):
    """화이트리스트·크기·형식 위반."""


class NotFoundError(WorkRecordError, LookupError):
    """대상 job/step/artifact 없음(또는 범위 밖)."""


class InvalidTransitionError(WorkRecordError):
    """허용되지 않은 상태 전이(또는 동시 전이에서 진 쪽)."""


# ── 상태·분류 Enum ────────────────────────────────────────────────────────


class JobStatus(StrEnum):
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    RUNNING = "running"
    PAUSED = "paused"
    RESUMABLE = "resumable"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class StepStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


class Risk(StrEnum):
    READ = "read"
    WRITE = "write"
    SUBMIT = "submit"


class Sensitivity(StrEnum):
    PUBLIC = "public"
    INTERNAL = "internal"
    RESTRICTED = "restricted"


class RetentionClass(StrEnum):
    STANDARD = "standard"
    SHORT = "short"
    KEEP = "keep"


class LinkType(StrEnum):
    APPROVAL = "approval"
    AUDIT = "audit"
    DISPATCH = "dispatch"
    SCHEDULED_RUN = "scheduled_run"
    GONGMU_TASK = "gongmu_task"
    EXPLORE_REQUEST = "explore_request"


# job 전이표 (기준서 §3-2). 종료 상태는 전이 없음(재실행은 새 job).
JOB_TRANSITIONS: Mapping[JobStatus, frozenset[JobStatus]] = {
    JobStatus.DRAFT: frozenset({JobStatus.PENDING_APPROVAL, JobStatus.CANCELLED}),
    JobStatus.PENDING_APPROVAL: frozenset({JobStatus.RUNNING, JobStatus.CANCELLED, JobStatus.EXPIRED}),
    JobStatus.RUNNING: frozenset({JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.PAUSED, JobStatus.CANCELLED}),
    JobStatus.PAUSED: frozenset({JobStatus.RESUMABLE, JobStatus.CANCELLED}),
    JobStatus.RESUMABLE: frozenset({JobStatus.RUNNING, JobStatus.CANCELLED}),
    JobStatus.SUCCEEDED: frozenset(),
    JobStatus.FAILED: frozenset(),
    JobStatus.CANCELLED: frozenset(),
    JobStatus.EXPIRED: frozenset(),
}
JOB_TERMINAL = frozenset(s for s, nxt in JOB_TRANSITIONS.items() if not nxt)
# 생성 시 허용되는 초기 상태(그 밖의 상태로 바로 만들 수 없다)
JOB_INITIAL_STATUSES = frozenset({JobStatus.DRAFT, JobStatus.PENDING_APPROVAL, JobStatus.RUNNING})

# step 전이표: 실패 step 은 재시도(attempt+1) 로만 running 에 돌아갈 수 있다.
STEP_TRANSITIONS: Mapping[StepStatus, frozenset[StepStatus]] = {
    StepStatus.PENDING: frozenset({StepStatus.RUNNING, StepStatus.SKIPPED, StepStatus.SUCCEEDED, StepStatus.FAILED}),
    StepStatus.RUNNING: frozenset({StepStatus.SUCCEEDED, StepStatus.FAILED}),
    StepStatus.FAILED: frozenset({StepStatus.RUNNING}),
    StepStatus.SUCCEEDED: frozenset(),
    StepStatus.SKIPPED: frozenset(),
}


def can_transition_job(current: JobStatus, new: JobStatus) -> bool:
    return new in JOB_TRANSITIONS[current]


def job_sources_for(new: JobStatus) -> tuple[JobStatus, ...]:
    """`new` 로 갈 수 있는 모든 이전 상태 — 원자적 `UPDATE ... WHERE status IN (...)` 의 조건."""
    return tuple(s for s, nxt in JOB_TRANSITIONS.items() if new in nxt)


def can_transition_step(current: StepStatus, new: StepStatus) -> bool:
    return new in STEP_TRANSITIONS[current]


# ── kind 허용목록 ─────────────────────────────────────────────────────────

JOB_KINDS = frozenset({"site_map_explore", "task_run", "dev_task", "ops_check", "manual"})
JOB_KIND_ONBOARD_PREFIX = "site.onboard:"  # 6a 온보딩 job: `site.onboard:<host>`
STEP_KINDS = frozenset(
    {"explore", "classify", "navigate", "read", "fill", "submit", "verify", "approve", "dry_run", "run"}
)
ARTIFACT_KINDS = frozenset({"site_map_snapshot", "task_spec", "run_result_meta", "screenshot", "report", "export"})

_HOST_RE = re.compile(r"^[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?$")
_ACTOR_RE = re.compile(r"^[\w.@:+-]{1,100}$")
_TENANT_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_TAG_RE = re.compile(r"^[\w가-힣.:+-]{1,40}$")
_EVENT_RE = re.compile(r"^[a-z][a-z0-9_.]{0,63}$")
_REF_RE = re.compile(r"^[\w.:@/-]{1,200}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MEDIA_RE = re.compile(r"^[a-z0-9][a-z0-9.+-]*/[a-z0-9][a-z0-9.+-]*$")
_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?)?$")

TITLE_MAX = 200
SUMMARY_MAX = 1000
ERROR_MAX = 500
EVENT_DETAIL_MAX = 1000
PARAMS_JSON_MAX = 8000
PARAM_STR_MAX = 500
PARAM_LIST_MAX = 50
TAGS_MAX = 20
ARTIFACT_MAX_BYTES = 256 * 1024 * 1024
PAGE_LIMIT_MAX = 100


def validate_host(host: str) -> str:
    if not isinstance(host, str) or not _HOST_RE.match(host) or ".." in host:
        raise ValidationError(f"잘못된 host 형식: {host!r}")
    return host


def validate_job_kind(kind: str) -> str:
    """허용 kind 이거나 `site.onboard:<host>`(호스트 형식 검사)."""
    if kind in JOB_KINDS:
        return kind
    if isinstance(kind, str) and kind.startswith(JOB_KIND_ONBOARD_PREFIX):
        validate_host(kind[len(JOB_KIND_ONBOARD_PREFIX) :])
        return kind
    raise ValidationError(f"허용되지 않은 job kind: {kind!r}")


def onboard_host(kind: str) -> str | None:
    """`site.onboard:<host>` 면 host, 아니면 None."""
    if isinstance(kind, str) and kind.startswith(JOB_KIND_ONBOARD_PREFIX):
        return kind[len(JOB_KIND_ONBOARD_PREFIX) :]
    return None


def _in_set(value: str, allowed: frozenset[str], label: str) -> str:
    if value not in allowed:
        raise ValidationError(f"허용되지 않은 {label}: {value!r}")
    return value


def validate_step_kind(kind: str) -> str:
    return _in_set(kind, STEP_KINDS, "step kind")


def validate_artifact_kind(kind: str) -> str:
    return _in_set(kind, ARTIFACT_KINDS, "artifact kind")


def _enum_value(enum_cls: type[StrEnum], value: str, label: str) -> str:
    try:
        return str(enum_cls(value).value)
    except ValueError:
        raise ValidationError(f"허용되지 않은 {label}: {value!r}") from None


def validate_job_status(value: str) -> JobStatus:
    return JobStatus(_enum_value(JobStatus, value, "job status"))


def validate_step_status(value: str) -> StepStatus:
    return StepStatus(_enum_value(StepStatus, value, "step status"))


def validate_risk(value: str) -> str:
    return _enum_value(Risk, value, "risk")


def validate_sensitivity(value: str) -> str:
    return _enum_value(Sensitivity, value, "sensitivity")


def validate_retention(value: str) -> str:
    return _enum_value(RetentionClass, value, "retention_class")


def validate_link_type(value: str) -> str:
    return _enum_value(LinkType, value, "link_type")


# ── 텍스트·식별자 검증 ─────────────────────────────────────────────────────

_FORBIDDEN_KEY_PARTS = (
    "password", "passwd", "token", "secret", "cookie", "otp", "session", "credential", "authorization", "apikey", "api_key",
)  # fmt: skip
_SECRET_ASSIGN_RE = re.compile(r"(?i)(password|passwd|token|secret|cookie|otp|apikey|api_key)\s*[=:]\s*\S")
_URL_RE = re.compile(r"https?://[^\s\"'<>)]+", re.IGNORECASE)

# input_params 허용 필드(기준서 §3-1·§3-6: 구조·해시·개수만). 이 밖의 키는 거부한다.
PARAM_ALLOWED_KEYS = frozenset(
    {
        "host", "start_url", "url", "task_key", "map_rev", "fingerprint", "mode", "max_pages", "max_depth",
        "dry_run", "field_names", "columns", "row_count", "count", "page_count", "note", "label", "source", "reason",
        "verdict", "robots_status",
    }
)  # fmt: skip

# 열거형 검증 키(6a M10 사전조사용 구조 문자열). 허용 값 밖·문자열 아님은 거부.
PARAM_ENUM_VALUES: dict[str, frozenset[str]] = {
    "verdict": frozenset({"proceed", "use_api", "blocked"}),
    "robots_status": frozenset({"ok", "missing", "unavailable"}),
}


def unsafe_url_reason(url: str) -> str | None:
    """쿼리·프래그먼트·자격증명이 있는 URL 이면 사유, 안전하면 None."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return "URL 파싱 실패"
    if parts.query:
        return "URL 쿼리 포함"
    if parts.fragment:
        return "URL 프래그먼트 포함"
    if parts.username is not None or parts.password is not None or "@" in parts.netloc:
        return "URL 자격증명 포함"
    return None


def check_text(value: str | None, label: str, max_len: int) -> str | None:
    """요약·오류·상세 문자열 검사: 길이 제한, 쿼리/자격증명 URL 거부, `password=...` 형태 거부."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValidationError(f"{label} 은 문자열이어야 한다")
    if len(value) > max_len:
        raise ValidationError(f"{label} 이 너무 길다({len(value)}>{max_len})")
    if "\x00" in value:
        raise ValidationError(f"{label} 에 NUL 문자")
    for m in _URL_RE.finditer(value):
        reason = unsafe_url_reason(m.group(0))
        if reason:
            raise ValidationError(f"{label}: {reason}")
    if _SECRET_ASSIGN_RE.search(value):
        raise ValidationError(f"{label}: 비밀값 대입 형태 문자열 거부")
    return value


def validate_title(title: str) -> str:
    if not isinstance(title, str) or not title.strip():
        raise ValidationError("title 은 비어 있을 수 없다")
    return str(check_text(title.strip(), "title", TITLE_MAX))


def validate_actor(actor: str) -> str:
    if not isinstance(actor, str) or not _ACTOR_RE.match(actor):
        raise ValidationError(f"잘못된 actor: {actor!r}")
    return actor


def validate_tenant(tenant_id: str) -> str:
    if not isinstance(tenant_id, str) or not _TENANT_RE.match(tenant_id):
        raise ValidationError(f"잘못된 tenant_id: {tenant_id!r}")
    return tenant_id


def validate_tags(tags: Sequence[str]) -> tuple[str, ...]:
    if isinstance(tags, str):
        raise ValidationError("tags 는 문자열 목록이어야 한다")
    out: list[str] = []
    for tag in tags:
        if not isinstance(tag, str) or not _TAG_RE.match(tag):
            raise ValidationError(f"잘못된 tag: {tag!r}")
        if tag not in out:
            out.append(tag)
    if len(out) > TAGS_MAX:
        raise ValidationError(f"tag 는 최대 {TAGS_MAX}개")
    return tuple(out)


def validate_event_name(event: str) -> str:
    if not isinstance(event, str) or not _EVENT_RE.match(event):
        raise ValidationError(f"잘못된 event 이름: {event!r}")
    return event


def validate_ref(value: str, label: str) -> str:
    if not isinstance(value, str) or not _REF_RE.match(value):
        raise ValidationError(f"잘못된 {label}: {value!r}")
    return value


def validate_ref_id(value: str, label: str, *, allow_none: bool = False) -> str | None:
    if value is None and allow_none:
        return None
    return validate_ref(value, label)


def validate_sha256(value: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.match(value):
        raise ValidationError("sha256 은 소문자 hex 64자")
    return value


def validate_media_type(value: str) -> str:
    if not isinstance(value, str) or len(value) > 100 or not _MEDIA_RE.match(value):
        raise ValidationError(f"잘못된 media_type: {value!r}")
    return value


def validate_iso(value: str | None, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not _ISO_RE.match(value):
        raise ValidationError(f"{label} 은 ISO8601 형식이어야 한다")
    return value


def validate_artifact_rel_path(path: str) -> str:
    """저장용 상대 경로 검사(순수): 절대경로·드라이브·`..`·역슬래시·빈 구성요소 거부."""
    if not isinstance(path, str) or not path or len(path) > 500 or "\x00" in path:
        raise ValidationError("artifact 경로가 비었거나 너무 길다")
    if "\\" in path or path.startswith("/") or re.match(r"^[A-Za-z]:", path):
        raise ValidationError("artifact 경로는 '/' 구분 상대 경로여야 한다")
    parts = path.split("/")
    if any(p in ("", ".", "..") for p in parts):
        raise ValidationError("artifact 경로에 빈 구성요소/'.'/'..' 금지")
    return path


def _validate_enum_param(key: str, value: Any, allowed: frozenset[str]) -> None:
    if not isinstance(value, str) or value not in allowed:
        raise ValidationError(f"params.{key}: 허용 값 아님(허용: {sorted(allowed)})")


def _validate_param_value(key: str, value: Any) -> None:
    if value is None or isinstance(value, (bool, int, float)):
        return
    if isinstance(value, str):
        check_text(value, f"params.{key}", PARAM_STR_MAX)
        if value.lower().startswith(("http://", "https://")):
            reason = unsafe_url_reason(value)
            if reason:
                raise ValidationError(f"params.{key}: {reason}")
        return
    if isinstance(value, (list, tuple)):
        if len(value) > PARAM_LIST_MAX:
            raise ValidationError(f"params.{key} 목록이 너무 길다")
        for item in value:
            if not (item is None or isinstance(item, (bool, int, float, str))):
                raise ValidationError(f"params.{key} 목록 원소는 스칼라만")
            if isinstance(item, str):
                _validate_param_value(key, item)
        return
    raise ValidationError(f"params.{key}: 허용되지 않은 값 형식({type(value).__name__})")


def _validate_param(key: str, value: Any) -> None:
    allowed = PARAM_ENUM_VALUES.get(key)
    if allowed is not None:
        _validate_enum_param(key, value, allowed)
    else:
        _validate_param_value(key, value)


def validate_params(params: Mapping[str, Any] | None) -> dict[str, Any]:
    """input_params 화이트리스트 검사. 알 수 없는 키·금지 키 이름·과대 크기·위험 URL 은 예외."""
    if params is None:
        return {}
    if not isinstance(params, Mapping):
        raise ValidationError("params 는 객체여야 한다")
    clean: dict[str, Any] = {}
    for key, value in params.items():
        if not isinstance(key, str):
            raise ValidationError("params 키는 문자열이어야 한다")
        low = key.lower()
        if any(part in low for part in _FORBIDDEN_KEY_PARTS):
            raise ValidationError(f"params 키에 금지 이름 포함: {key!r}")
        if key not in PARAM_ALLOWED_KEYS:
            raise ValidationError(f"params 허용 필드가 아님: {key!r}")
        _validate_param(key, value)
        clean[key] = list(value) if isinstance(value, tuple) else value
    if len(canonical_json(clean)) > PARAMS_JSON_MAX:
        raise ValidationError("params 가 너무 크다")
    return clean


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def compute_input_hash(kind: str, host: str | None, params: Mapping[str, Any]) -> str:
    """정규화 입력(kind·host·params) sha256 — 동일 입력 재실행 판정용."""
    return hashlib.sha256(canonical_json({"kind": kind, "host": host, "params": dict(params)}).encode()).hexdigest()


# ── 조회 범위 (테넌트·소유자 필터 기본 ON) ────────────────────────────────────


@dataclass(frozen=True)
class Scope:
    """조회 범위. 직접 생성 대신 `owner_only` / `tenant_wide` 를 쓴다(필터가 암묵적으로 꺼지지 않게)."""

    tenant_id: str
    created_by: str | None

    @classmethod
    def owner_only(cls, created_by: str, tenant_id: str = "default") -> Scope:
        return cls(validate_tenant(tenant_id), validate_actor(created_by))

    @classmethod
    def tenant_wide(cls, tenant_id: str = "default") -> Scope:
        return cls(validate_tenant(tenant_id), None)


# ── 엔티티 ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class JobDraft:
    """job 생성 입력. 검증은 스토어가 `validate_*` 로 한다."""

    kind: str
    title: str
    actor: str
    host: str | None = None
    site_id: str | None = None
    params: Mapping[str, Any] | None = None
    tenant_id: str = "default"
    status: JobStatus = JobStatus.DRAFT
    tags: Sequence[str] = ()
    rerun_of: str | None = None
    forked_from: str | None = None
    resumed_from: str | None = None
    retention_class: str = RetentionClass.STANDARD.value
    workflow_run_id: str | None = None
    task_id: str | None = None  # audit_logger 정합용 연결 키(기준서 §3-1·§3-5)


@dataclass(frozen=True)
class StepDraft:
    kind: str
    risk: str
    seq: int | None = None
    status: StepStatus = StepStatus.PENDING
    input_summary: str | None = None
    output_summary: str | None = None
    error: str | None = None
    approval_ref: str | None = None
    irreversible: bool = False


@dataclass(frozen=True)
class StepUpdate:
    """step 상태 변경 입력(요약·오류·승인 참조는 상태 변경과 함께만 갱신된다)."""

    status: str
    output_summary: str | None = None
    error: str | None = None
    approval_ref: str | None = None


@dataclass(frozen=True)
class JobPatch:
    """job 의 가변 필드(title/tags/starred/archived)만."""

    title: str | None = None
    tags: Sequence[str] | None = None
    starred: bool | None = None
    archived: bool | None = None


@dataclass(frozen=True)
class JobQuery:
    """목록 필터(기준서 §6-1). 테넌트·소유자 범위는 `Scope` 로 따로 받는다."""

    status: str | None = None
    host: str | None = None
    kind: str | None = None
    kind_prefix: str | None = None
    tag: str | None = None
    starred: bool | None = None
    archived: bool | None = None
    created_from: str | None = None
    created_to: str | None = None
    text: str | None = None  # 제목·태그 부분 일치(요약 검색은 M2 이후)
    include_deleted: bool = False


@dataclass(frozen=True)
class ArtifactSpec:
    kind: str
    src_path: str
    step_seq: int | None = None
    sensitivity: str = Sensitivity.INTERNAL.value
    media_type: str = "application/octet-stream"
    retention_class: str = RetentionClass.STANDARD.value


@dataclass(frozen=True)
class Job:
    job_id: str
    kind: str
    title: str
    status: JobStatus
    site_id: str | None
    host: str | None
    params: dict[str, Any]
    input_hash: str
    tags: tuple[str, ...]
    starred: bool
    archived: bool
    rerun_of: str | None
    forked_from: str | None
    resumed_from: str | None
    version: int
    tenant_id: str
    created_by: str
    updated_by: str
    retention_class: str
    workflow_run_id: str | None
    task_id: str | None
    created_at: str
    updated_at: str
    deleted_at: str | None = None


@dataclass(frozen=True)
class Step:
    job_id: str
    seq: int
    kind: str
    status: StepStatus
    risk: str
    started_at: str | None
    finished_at: str | None
    input_summary: str | None
    output_summary: str | None
    error: str | None
    approval_ref: str | None
    attempt: int
    irreversible: bool


@dataclass(frozen=True)
class Artifact:
    artifact_id: str
    job_id: str
    step_seq: int | None
    kind: str
    path: str
    sha256: str
    size_bytes: int
    media_type: str
    sensitivity: str
    retention_class: str
    created_at: str


@dataclass(frozen=True)
class Event:
    event_id: int
    job_id: str
    step_seq: int | None
    at: str
    actor: str
    event: str
    detail: str | None


@dataclass(frozen=True)
class Link:
    job_id: str
    link_type: str
    ref_store: str
    ref_id: str


@dataclass(frozen=True)
class JobPage:
    items: list[Job] = field(default_factory=list)
    total: int = 0
    limit: int = 30
    offset: int = 0


# ── 6a 호출 규약 (기준서 §4) — 시그니처만. 구현은 M2 의 L6 서비스 ─────────────────


class RecordJobStart(Protocol):
    def __call__(  # noqa: PLR0913 — 기준서 §4 시그니처 고정
        self,
        kind: str,
        title: str,
        host: str | None,
        params: Mapping[str, Any] | None,
        *,
        actor: str,
        tenant_id: str | None = None,
        rerun_of: str | None = None,
    ) -> str: ...


class RecordStep(Protocol):
    def __call__(  # noqa: PLR0913 — 기준서 §4 시그니처 고정
        self,
        job_id: str,
        seq: int,
        kind: str,
        risk: str,
        *,
        status: str,
        input_summary: str | None = None,
        output_summary: str | None = None,
        error: str | None = None,
        approval_ref: str | None = None,
        irreversible: bool = False,
    ) -> None: ...


class AttachArtifact(Protocol):
    def __call__(
        self,
        job_id: str,
        kind: str,
        src_path: str,
        *,
        step_seq: int | None = None,
        sensitivity: str = "internal",
    ) -> str: ...


class FinishJob(Protocol):
    def __call__(self, job_id: str, status: str, *, error: str | None = None) -> None: ...
