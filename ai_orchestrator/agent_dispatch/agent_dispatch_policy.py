"""AI 에이전트 작업 분배 — 충돌 정책(순수 함수, I/O 없음).

기준서: docs/specs/2026-10-02_app_agent_dispatch.md §2·§4 (P2).

하위 작업이 선언한 자원(resources)으로 "같이 돌려도 되는가"를 판정한다.
- 전역 직렬 자원(git/db/server/deploy/delete/permission/secret): 그 작업이 도는 동안 다른 작업(읽기 전용 포함)은 시작하지 않고,
  다른 작업이 도는 동안에는 시작하지 않는다(단독 실행).
- 배타 자원(ui, cdp:<사이트>, path:<경로>): 같은 토큰(경로는 정규화한 뒤 포함 관계)끼리만 동시 실행 금지.
- 읽기 전용 + 자원 선언 없음: 전역 직렬 작업이 아니면 자유롭게 병렬.
- 자원을 선언하지 않았거나 모르는 토큰이면 전역 직렬로 취급한다(fail-closed).
"""

from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# ── 한도(기준서 §5·§8 확정값) ────────────────────────────────────────────
MAX_SUBTASKS = 6
DEFAULT_PARALLEL = 2
MAX_PARALLEL = 3
TOTAL_BUDGET_USD = 6.0
TASK_BUDGET_USD = 1.0
DEFAULT_TASK_TIMEOUT_SEC = 300
MAX_TASK_TIMEOUT_SEC = 1800

# 항상 직렬(전역 락) — 승인해도 풀 수 없다.
GLOBAL_SERIAL_RESOURCES = frozenset({"git", "db", "server", "deploy", "delete", "permission", "secret"})
# 한 번에 하나(토큰이 같을 때만 충돌). 접두 형태는 "cdp:", "path:".
_EXCLUSIVE_EXACT = frozenset({"ui"})
_EXCLUSIVE_PREFIXES = ("cdp:", "path:")

# 작업 상태
PENDING, STARTING, RUNNING, DONE, FAILED, SKIPPED = "pending", "starting", "running", "done", "failed", "skipped"
_FINISHED_BAD = (FAILED, SKIPPED)


@dataclass(frozen=True)
class ResourceClaim:
    """정규화된 자원 선언. is_global 이면 단독 실행."""

    tokens: frozenset[str]
    is_global: bool
    free: bool  # 읽기 전용 + 선언 없음 → 전역 직렬이 아닌 작업과는 충돌 판정 대상 아님


# 상대 경로의 기준 폴더(= 로컬 에이전트가 claude 를 실행하는 저장소 루트). 순수 계산이며 파일 시스템을 읽지 않는다.
WORKDIR = Path(__file__).resolve().parents[2].as_posix().lower()

_DRIVE_ABS = re.compile(r"^([a-z]:)/")
_DRIVE_REL = re.compile(r"^[a-z]:(?!/)")
_BAD_PATH_CHARS = re.compile(r'[\x00-\x1f*?"<>|]')
_SHORT_NAME = re.compile(r"~\d")


def _clean_segments(value: str) -> str | None:
    """세그먼트별 Windows 정규화: 끝의 점·공백 제거(`src.` == `src`), 8.3 짧은 이름은 판정 불가라 거부."""
    segs = []
    for seg in value.split("/"):
        if seg in ("", ".", ".."):
            segs.append(seg)
            continue
        cleaned = seg.rstrip(". ")
        if not cleaned or _SHORT_NAME.search(cleaned):
            return None
        segs.append(cleaned)
    return "/".join(segs)


def _norm_path(token: str) -> str | None:
    """`path:<경로>` 를 비교 가능한 표준형(`path:c:/dir/sub` 또는 `path://host/share/dir`)으로 바꾼다.

    같은 위치를 가리키는 서로 다른 표기(`src`·`./src`·`SRC/`·`src.`·`src/../src`·절대/상대·슬래시 방향·`\\\\?\\` 접두)를
    하나로 모은다. 판정할 수 없는 표기(드라이브 상대 `C:src`, 앞 슬래시만 있는 `/x`, 와일드카드, 제어문자,
    대체 데이터 스트림 `a:b`, 8.3 짧은 이름, 기준을 벗어나는 `..`)는 None → 호출자가 전역 직렬로 처리한다(fail-closed).
    심볼릭 링크·정션은 이름만으로 알 수 없다(격리 worktree 실행으로 보완 — 기준서 P4).
    """
    raw = token[len("path:") :].strip()
    if not raw or _BAD_PATH_CHARS.search(raw):
        return None
    value = raw.replace("\\", "/").lower()
    if value.startswith("//?/unc/"):
        value = "//" + value[len("//?/unc/") :]
    elif value.startswith(("//?/", "//./")):
        value = value[4:]

    anchored = _anchor_of(value)
    if anchored is None:
        return None
    anchor, value = anchored
    cleaned = _clean_segments(value)
    if cleaned is None:
        return None
    normalized = posixpath.normpath(cleaned)
    if normalized != anchor and not normalized.startswith(anchor + "/"):
        return None  # `..` 로 드라이브/공유 루트 밖으로 벗어남
    return "path:" + normalized


def _anchor_of(value: str) -> tuple[str, str] | None:
    """경로의 뿌리(드라이브 `c:` 또는 UNC `//host/share`)와 절대화한 경로를 돌려준다. 판정 불가면 None."""
    if value.startswith("//"):  # UNC: //host/share/...
        host_share = value[2:].split("/")[:2]
        if len(host_share) < 2 or not all(host_share):
            return None
        return "//" + "/".join(host_share), value
    if _DRIVE_REL.match(value) or value.startswith("/"):
        return None
    m = _DRIVE_ABS.match(value)
    if m is not None:
        return (m.group(1), value) if ":" not in value[len(m.group(1)) :] else None
    if ":" in value:
        return None  # 대체 데이터 스트림 등
    absolute = f"{WORKDIR}/{value}"
    base = _DRIVE_ABS.match(absolute)
    return (base.group(1), absolute) if base else None  # 기준 폴더가 드라이브 경로가 아니면 판정 불가


def _valid_token(token: str) -> bool:
    if token in GLOBAL_SERIAL_RESOURCES or token in _EXCLUSIVE_EXACT:
        return True
    return any(token.startswith(p) and len(token) > len(p) for p in _EXCLUSIVE_PREFIXES)


def _normalize_token(item: str) -> str | None:
    token = item.strip()
    if token.lower().startswith("path:"):
        token = _norm_path(token) or ""
    else:
        token = token.lower()
    return token if token and _valid_token(token) else None


_UNKNOWN_CLAIM = ResourceClaim(frozenset({"unknown"}), True, False)


def claim_of(task: dict[str, Any]) -> ResourceClaim:
    """하위 작업 dict 에서 자원 선언을 읽어 정규화한다. 모호하면 전역 직렬."""
    raw = task.get("resources")
    read_only = task.get("read_only") is True
    declared = isinstance(raw, (list, tuple, set, frozenset))
    tokens: set[str] = set()
    if isinstance(raw, (list, tuple, set, frozenset)):
        for item in raw:
            token = _normalize_token(item) if isinstance(item, str) else None
            if token is None:
                return _UNKNOWN_CLAIM
            tokens.add(token)

    if not tokens:
        if read_only and declared:
            return ResourceClaim(frozenset(), False, True)
        return _UNKNOWN_CLAIM  # 선언 없음(또는 쓰기 작업인데 빈 선언) → fail-closed
    return ResourceClaim(frozenset(tokens), bool(tokens & GLOBAL_SERIAL_RESOURCES), False)


def _paths_overlap(a: str, b: str) -> bool:
    pa, pb = a[len("path:") :], b[len("path:") :]
    return pa == pb or pa.startswith(pb + "/") or pb.startswith(pa + "/")


def conflicts(a: ResourceClaim, b: ResourceClaim) -> bool:
    """두 작업을 동시에 돌리면 안 되면 True.

    전역 직렬 작업은 읽기 전용(free) 작업을 포함해 **모든** 작업과 충돌한다(그 작업이 도는 동안 다른 작업은 시작하지 않고,
    그 작업은 다른 작업이 도는 동안 시작하지 않는다). 읽기 전용+선언 없음 작업끼리, 그리고 비전역 작업과는 병렬이다.
    """
    if a.is_global or b.is_global:
        return True
    if a.free or b.free:
        return False
    for ta in a.tokens:
        for tb in b.tokens:
            if ta.startswith("path:") and tb.startswith("path:"):
                if _paths_overlap(ta, tb):
                    return True
            elif ta == tb:
                return True
    return False


# ── 역할(기준서 P3) ──────────────────────────────────────────────────────
# 읽기 전용 여부는 AI 가 아니라 역할이 결정한다(AI 가 스스로 read_only 를 선언해 충돌 검사를 피하지 못하게).
READ_ONLY_ROLES = frozenset({"explore", "review", "summarize"})
WRITE_ROLES = frozenset({"implement"})
ROLES = READ_ONLY_ROLES | WRITE_ROLES
SUMMARIZE_ROLE = "summarize"


def normalize_plan(raw_tasks: Any) -> tuple[list[dict[str, Any]], list[str]]:
    """AI 가 제안한 하위 작업 목록을 표준 형태로 바꾼다. (작업 목록, 오류 목록).

    - role 이 없거나 모르는 값이면 오류.
    - 읽기 전용 역할은 resources 를 비운다(선언해도 무시). implement 는 resources 가 필수(없으면 validate 에서 직렬 취급).
    - summarize 는 최대 1개이며 다른 모든 작업에 의존하도록 고정한다.
    """
    if not isinstance(raw_tasks, list) or not raw_tasks:
        return [], ["tasks 가 비어 있거나 목록이 아닙니다"]
    tasks: list[dict[str, Any]] = []
    errors: list[str] = []
    for index, raw in enumerate(raw_tasks):
        if not isinstance(raw, dict):
            errors.append(f"{index + 1}번째 하위 작업이 객체가 아닙니다")
            continue
        tid = str(raw.get("id") or f"t{index + 1}").strip()
        role = str(raw.get("role", "")).strip().lower()
        if role not in ROLES:
            errors.append(f"{tid}: 알 수 없는 역할({role or '없음'})")
            continue
        prompt = str(raw.get("prompt", "")).strip()
        if not prompt:
            errors.append(f"{tid}: prompt 가 비어 있습니다")
            continue
        read_only = role in READ_ONLY_ROLES
        task: dict[str, Any] = {
            "id": tid,
            "title": str(raw.get("title") or tid).strip()[:80],
            "role": role,
            "prompt": prompt[:4000],
            "read_only": read_only,
            "resources": [] if read_only else raw.get("resources"),
            "depends_on": [str(d) for d in (raw.get("depends_on") or []) if isinstance(d, (str, int))],
            "budget_usd": raw.get("budget_usd", TASK_BUDGET_USD),
            "timeout_sec": raw.get("timeout_sec", DEFAULT_TASK_TIMEOUT_SEC),
        }
        tasks.append(task)

    summaries = [t for t in tasks if t["role"] == SUMMARIZE_ROLE]
    if len(summaries) > 1:
        errors.append("summarize 작업은 최대 1개입니다")
    elif summaries:
        summaries[0]["depends_on"] = [t["id"] for t in tasks if t is not summaries[0]]
    return tasks, errors


# ── 계획 검증 ────────────────────────────────────────────────────────────
def validate_plan(tasks: list[dict[str, Any]]) -> list[str]:
    """분배안 검증. 오류 문자열 목록(비어 있으면 통과)."""
    errors: list[str] = []
    if not tasks:
        return ["하위 작업이 없습니다"]
    if len(tasks) > MAX_SUBTASKS:
        errors.append(f"하위 작업은 최대 {MAX_SUBTASKS}개입니다({len(tasks)}개)")

    ids = [str(t.get("id", "")).strip() for t in tasks]
    if any(not i for i in ids):
        errors.append("id 가 없는 하위 작업이 있습니다")
    if len(set(ids)) != len(ids):
        errors.append("하위 작업 id 가 중복됩니다")
    known = set(ids)

    total = 0.0
    for t, tid in zip(tasks, ids, strict=False):
        task_errors, budget = _check_task(t, tid, known)
        errors.extend(task_errors)
        total += budget
    if total > TOTAL_BUDGET_USD + 1e-9:
        errors.append(f"전체 비용 상한 {TOTAL_BUDGET_USD}$ 초과({total:.2f}$)")

    if not errors and _has_cycle(tasks):
        errors.append("의존 관계에 순환이 있습니다")
    return errors


def _check_task(task: dict[str, Any], tid: str, known: set[str]) -> tuple[list[str], float]:
    errors: list[str] = []
    for dep in task.get("depends_on") or []:
        if dep not in known:
            errors.append(f"{tid}: 없는 작업({dep})에 의존합니다")
        elif dep == tid:
            errors.append(f"{tid}: 자기 자신에 의존합니다")
    budget = _num(task.get("budget_usd"), TASK_BUDGET_USD)
    if not 0 < budget <= TASK_BUDGET_USD:
        errors.append(f"{tid}: 작업당 비용 상한은 0 초과 {TASK_BUDGET_USD}$ 이하입니다")
    timeout = _num(task.get("timeout_sec"), DEFAULT_TASK_TIMEOUT_SEC)
    if not 30 <= timeout <= MAX_TASK_TIMEOUT_SEC:
        errors.append(f"{tid}: 시간 제한은 30~{MAX_TASK_TIMEOUT_SEC}초입니다")
    return errors, budget


def _num(value: Any, default: float) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return -1.0


def _has_cycle(tasks: list[dict[str, Any]]) -> bool:
    deps = {str(t["id"]): list(t.get("depends_on") or []) for t in tasks}
    state: dict[str, int] = {}

    def visit(node: str) -> bool:
        if state.get(node) == 1:
            return True
        if state.get(node) == 2:
            return False
        state[node] = 1
        if any(visit(d) for d in deps[node]):
            return True
        state[node] = 2
        return False

    return any(visit(n) for n in deps)


# ── 스케줄 ───────────────────────────────────────────────────────────────
def clamp_parallel(value: Any) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return DEFAULT_PARALLEL
    return max(1, min(MAX_PARALLEL, n))


def next_step(
    tasks: list[dict[str, Any]],
    states: dict[str, str],
    max_parallel: int = DEFAULT_PARALLEL,
) -> tuple[list[str], list[str]]:
    """지금 시작할 작업 id 목록과 건너뛸(skipped) 작업 id 목록을 돌려준다.

    tasks 순서가 우선순위다. 의존 작업이 failed/skipped 면 그 작업은 skipped.
    실행 중인 작업과 충돌하거나 동시 실행 한도를 넘는 작업은 이번에는 시작하지 않는다.
    """
    cap = clamp_parallel(max_parallel)
    by_id = {str(t["id"]): t for t in tasks}
    claims = {tid: claim_of(t) for tid, t in by_id.items()}

    skipped: list[str] = []
    for tid, t in by_id.items():
        if states.get(tid, PENDING) != PENDING:
            continue
        if any(states.get(d, PENDING) in _FINISHED_BAD for d in t.get("depends_on") or []):
            skipped.append(tid)

    skipped_set = set(skipped)
    active = [tid for tid, s in states.items() if s in (STARTING, RUNNING) and tid in by_id]
    start: list[str] = []
    for tid, t in by_id.items():
        if len(active) + len(start) >= cap:
            break
        if states.get(tid, PENDING) != PENDING or tid in skipped_set:
            continue
        if any(states.get(d, PENDING) != DONE for d in t.get("depends_on") or []):
            continue
        if any(conflicts(claims[tid], claims[o]) for o in (*active, *start)):
            continue
        start.append(tid)
    return start, skipped


def preview_waves(tasks: list[dict[str, Any]], max_parallel: int = DEFAULT_PARALLEL) -> list[list[str]]:
    """모두 성공한다고 가정한 시작 순서 미리보기(분배안 카드용). 한 묶음 = 동시에 시작."""
    states = {str(t["id"]): PENDING for t in tasks}
    waves: list[list[str]] = []
    while any(s == PENDING for s in states.values()):
        start, _ = next_step(tasks, states, max_parallel)
        if not start:  # 의존이 풀리지 않는 경우 방어(검증을 통과한 계획에서는 발생하지 않음)
            break
        waves.append(start)
        for tid in start:
            states[tid] = DONE
    return waves


__all__ = [
    "DEFAULT_PARALLEL",
    "GLOBAL_SERIAL_RESOURCES",
    "MAX_PARALLEL",
    "MAX_SUBTASKS",
    "READ_ONLY_ROLES",
    "ROLES",
    "TASK_BUDGET_USD",
    "TOTAL_BUDGET_USD",
    "WRITE_ROLES",
    "ResourceClaim",
    "claim_of",
    "clamp_parallel",
    "conflicts",
    "next_step",
    "normalize_plan",
    "preview_waves",
    "validate_plan",
]
