"""AI 에이전트 작업 분배 — 충돌 정책(순수 함수, I/O 없음).

기준서: docs/specs/2026-10-02_app_agent_dispatch.md §2·§4 (P2).

하위 작업이 선언한 자원(resources)으로 "같이 돌려도 되는가"를 판정한다.
- 전역 직렬 자원(git/db/server/deploy/delete/permission/secret): 그 작업이 도는 동안 다른 작업은 시작하지 않는다.
- 배타 자원(ui, cdp:<사이트>, path:<경로>): 같은 토큰(경로는 포함 관계)끼리만 동시 실행 금지.
- 읽기 전용 + 자원 선언 없음: 자유롭게 병렬.
- 자원을 선언하지 않았거나 모르는 토큰이면 전역 직렬로 취급한다(fail-closed).
"""

from __future__ import annotations

from dataclasses import dataclass
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
PENDING, RUNNING, DONE, FAILED, SKIPPED = "pending", "running", "done", "failed", "skipped"
_FINISHED_BAD = (FAILED, SKIPPED)


@dataclass(frozen=True)
class ResourceClaim:
    """정규화된 자원 선언. is_global 이면 단독 실행."""

    tokens: frozenset[str]
    is_global: bool
    free: bool  # 읽기 전용 + 선언 없음 → 충돌 판정 대상 아님


def _norm_path(token: str) -> str:
    value = token[len("path:") :].replace("\\", "/").strip().lower().rstrip("/")
    return "path:" + value


def _valid_token(token: str) -> bool:
    if token in GLOBAL_SERIAL_RESOURCES or token in _EXCLUSIVE_EXACT:
        return True
    return any(token.startswith(p) and len(token) > len(p) for p in _EXCLUSIVE_PREFIXES)


def claim_of(task: dict[str, Any]) -> ResourceClaim:
    """하위 작업 dict 에서 자원 선언을 읽어 정규화한다. 모호하면 전역 직렬."""
    raw = task.get("resources")
    read_only = task.get("read_only") is True
    if raw is None or not isinstance(raw, (list, tuple, set, frozenset)):
        raw_list: list[Any] = []
        declared = False
    else:
        raw_list = list(raw)
        declared = True

    tokens: set[str] = set()
    for item in raw_list:
        if not isinstance(item, str):
            return ResourceClaim(frozenset({"unknown"}), True, False)
        token = item.strip().lower() if not item.strip().lower().startswith("path:") else item.strip()
        if token.lower().startswith("path:"):
            token = _norm_path(token)
        if not _valid_token(token):
            return ResourceClaim(frozenset({"unknown"}), True, False)
        tokens.add(token)

    if not tokens:
        if read_only and declared:
            return ResourceClaim(frozenset(), False, True)
        # 선언 없음(또는 쓰기 작업인데 빈 선언) → fail-closed
        return ResourceClaim(frozenset({"unknown"}), True, False)
    return ResourceClaim(frozenset(tokens), bool(tokens & GLOBAL_SERIAL_RESOURCES), False)


def _paths_overlap(a: str, b: str) -> bool:
    pa, pb = a[len("path:") :], b[len("path:") :]
    return pa == pb or pa.startswith(pb + "/") or pb.startswith(pa + "/")


def conflicts(a: ResourceClaim, b: ResourceClaim) -> bool:
    """두 작업을 동시에 돌리면 안 되면 True."""
    if a.free or b.free:
        return False
    if a.is_global or b.is_global:
        return True
    for ta in a.tokens:
        for tb in b.tokens:
            if ta.startswith("path:") and tb.startswith("path:"):
                if _paths_overlap(ta, tb):
                    return True
            elif ta == tb:
                return True
    return False


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
    active = [tid for tid, s in states.items() if s == RUNNING and tid in by_id]
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
    "TASK_BUDGET_USD",
    "TOTAL_BUDGET_USD",
    "ResourceClaim",
    "claim_of",
    "clamp_parallel",
    "conflicts",
    "next_step",
    "preview_waves",
    "validate_plan",
]
