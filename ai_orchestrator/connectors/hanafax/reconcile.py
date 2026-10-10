"""L6 서비스 — 하나팩스 전송결과 대조: 앱이 '접수됨(sent)'으로 기록한 건의 **최종 성공/실패**를 사이트 전송결과로 확정한다.

기준서: docs/specs/2026-10-02_hanafax_auto_send.md §15
- 읽기 전용(전송결과 화면만 읽는다). 대조 결과로 이력에 `delivered`(최종 성공) / `delivery_failed`(최종 실패)를 **추가**할 뿐 기존 기록은 바꾸지 않는다.
- 매칭은 보수적으로: ① 관리제목 일치(사이트가 길면 `..` 로 줄이므로 접두 일치) ② 앱 기록 시각과 사이트 전송 시각이 10분 이내
  ③ 같은 전송으로 묶이는 번호 수(앱에서 몇 초 안에 기록된 묶음)가 사이트의 '전체' 건수와 같음 ④ 한 건짜리면 번호도 일치.
  하나라도 맞지 않으면 아무것도 바꾸지 않고 `unmatched` 로 센다(오판보다 미확정이 안전). 일부만 성공(혼합)이면 사이트 세부내역(번호별 결과)으로 건별 확정하고, 못 하면 바꾸지 않고 `partial`.
- `delivery_failed` 번호는 사람이 확인하기 전까지 자동으로 다시 보내지 않는다(`확인 필요` 목록에 나타나 PIN 으로 해소).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from ai_orchestrator.connectors.hanafax import authorization_store as store

CLUSTER_GAP_SECONDS = 15  # 같은 전송으로 기록된 번호는 몇 초 안에 몰려 있다
MATCH_WINDOW_MINUTES = 10


def _local(iso_utc: str) -> datetime:
    return datetime.fromisoformat(iso_utc).astimezone()


def _clusters(pending: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """접수된 번호들을 기록 시각이 몰려 있는 단위(= 한 번의 전송)로 묶는다."""
    ordered = sorted(pending, key=lambda r: _local(r["created_at"]))
    groups: list[list[dict[str, Any]]] = []
    for rec in ordered:
        if (
            groups
            and (_local(rec["created_at"]) - _local(groups[-1][-1]["created_at"])).total_seconds()
            <= CLUSTER_GAP_SECONDS
        ):
            groups[-1].append(rec)
        else:
            groups.append([rec])
    return groups


def _title_matches(site_title: str, subject: str) -> bool:
    site, ours = site_title.strip(), subject.strip()
    if site.endswith(".."):  # 사이트 목록은 긴 제목을 '..' 로 줄여 보여 준다
        return ours.startswith(site[:-2].rstrip())
    return site == ours or ours.startswith(site)


def _eligible(site: dict[str, Any], subject: str) -> bool:
    """대조 대상 행인지 — 분 단위 시각이 있고 최종 결과가 확정됐으며 제목이 같다."""
    status = str(site["status"])
    if site["when"] is None or not site["minute_known"] or not status.startswith("전송") or "중" in status:
        return False
    return _title_matches(site["title"], subject)


def _best_group(site: dict[str, Any], free: list[list[dict[str, Any]]]) -> list[dict[str, Any]] | None:
    """사이트 행과 맞는 접수 묶음 — 건수·시각(±10분)·(한 건이면) 번호가 모두 맞는 것 중 시각이 가장 가까운 것."""
    window = MATCH_WINDOW_MINUTES * 60
    candidates = [
        g
        for g in free
        if len(g) == site["total"]
        and abs(_local(g[0]["created_at"]) - site["when"]).total_seconds() <= window
        and (not site["number"] or g[0]["fax_digits"] == site["number"])
    ]
    return min(candidates, key=lambda g: abs(_local(g[0]["created_at"]) - site["when"])) if candidates else None


def _resolve_mixed(
    auth_id: str, site: dict[str, Any], group: list[dict[str, Any]], fetch_detail: Callable[[str], dict[str, Any]] | None
) -> tuple[int, int] | None:
    """일부만 성공한 건을 **사이트 세부내역(번호별 결과)** 으로 건별 확정한다. 확정 못 하면 None(아무것도 바꾸지 않음).

    조건: 건 ID 가 있고, 세부내역의 번호 집합이 앱의 접수 묶음과 정확히 같으며, 모든 번호의 결과가 확인돼야 한다.
    """
    if not site.get("job_id"):
        return None
    if fetch_detail is None:
        from scripts.hanafax.send_result import fetch_job_detail

        fetch_detail = fetch_job_detail
    try:
        detail = fetch_detail(site["job_id"])
    except Exception:  # noqa: BLE001 - 상세를 못 읽어도 대조 전체를 깨지 않는다(혼합 건은 partial 로 남는다)
        return None
    digits = {rec["fax_digits"] for rec in group}
    outcomes = detail.get("outcomes", {})
    if set(outcomes) != digits or (detail.get("numbers") and set(detail["numbers"]) != digits):
        return None
    delivered = failed = 0
    for rec in group:
        ok = outcomes[rec["fax_digits"]] == "success"
        label = detail.get("labels", {}).get(rec["fax_digits"], "")
        store.record_send(
            store.SendRecord(
                auth_id,
                rec["fax_digits"],
                rec["document_hash"],
                store.DELIVERED if ok else store.DELIVERY_FAILED,
                None,
                f"전송결과 상세 확인: {label}",
            )
        )
        delivered, failed = delivered + ok, failed + (not ok)
    return delivered, failed


def reconcile(
    auth_id: str,
    fetch: Callable[[], list[dict[str, Any]]] | None = None,
    fetch_detail: Callable[[str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """승인서 하나의 접수된 건을 사이트 전송결과와 대조한다. `fetch`·`fetch_detail` 은 테스트용 주입(기본: 실제 사이트 읽기)."""
    row = store.get_authorization(auth_id)
    if row is None:
        raise ValueError("승인서를 찾을 수 없습니다")
    pending = store.pending_sent(auth_id)
    summary: dict[str, Any] = {
        "checked": len(pending),
        "delivered": 0,
        "delivery_failed": 0,
        "partial": 0,
        "unmatched": 0,
    }
    if not pending:
        return summary
    if fetch is None:
        from scripts.hanafax.send_result import fetch_results

        fetch = fetch_results
    free = _clusters(pending)
    for site in fetch():
        group = _best_group(site, free) if _eligible(site, row["subject"]) else None
        if group is None:
            continue
        free.remove(group)
        if site["success"] == site["total"]:
            status, key = store.DELIVERED, "delivered"
        elif site["failure"] == site["total"]:
            status, key = store.DELIVERY_FAILED, "delivery_failed"
        else:  # 일부만 성공 — 세부내역으로 번호별 확정을 시도하고, 못 하면 그대로 둔다
            resolved = _resolve_mixed(auth_id, site, group, fetch_detail)
            if resolved is None:
                summary["partial"] += len(group)
            else:
                summary["delivered"] += resolved[0]
                summary["delivery_failed"] += resolved[1]
            continue
        for rec in group:
            store.record_send(
                store.SendRecord(
                    auth_id, rec["fax_digits"], rec["document_hash"], status, None, f"전송결과 확인: {site['status']}"
                )
            )
        summary[key] += len(group)
    summary["unmatched"] = sum(len(g) for g in free)
    summary["checked_at"] = datetime.now(UTC).isoformat(timespec="seconds")
    return summary
