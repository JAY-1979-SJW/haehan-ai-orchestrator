"""L6 Business Workflows — 하나팩스 자동 발송 한 번 실행(승인서 범위 안, 드라이런 승인서는 전송하지 않고 계획만 기록).

예약 작업 허용 목록(`services/scheduled_job_actions`, `hanafax_send`)과 '지금 발송'(`authorization_service`)이 함께 쓴다.
하나팩스 쪽 구현이라 이 폴더에 둔다 — 두 호출부가 서로를 import 하지 않게(순환 방지) 공용 진입점으로 분리했다.
"""

from __future__ import annotations

from typing import Any


def run_send(params: dict[str, Any]) -> str:
    """승인서 범위 안에서 팩스를 자동 발송한다. 승인서가 드라이런이면 전송하지 않고 계획만 기록한다."""
    from datetime import datetime

    from ai_orchestrator.connectors.hanafax import authorization_store as fax_store
    from ai_orchestrator.connectors.hanafax import auto_send as fax_flow
    from ai_orchestrator.connectors.hanafax import auto_sender as adapter

    auth_id = params["authorization_id"]
    row = fax_store.get_authorization(auth_id)
    if row is None:
        raise ValueError("팩스 발송 승인서를 찾을 수 없습니다")

    def _never(*_args: Any) -> dict[str, Any]:  # 드라이런은 발송기를 부르지 않는다 — 불렸다면 버그이므로 멈춘다
        raise RuntimeError("드라이런 승인서는 전송할 수 없습니다")

    bulk = len(row["recipients"]) > 1  # 여러 명이면 하나팩스 단체발송(로그인·업로드 1회)으로 묶음 전송
    sender: Any = _never
    if row["live"]:
        build = adapter.build_bulk_sender if bulk else adapter.build_sender
        try:
            sender = build(row["document_ref"], row["document_hash"])
        except adapter.DocumentChanged as exc:
            raise RuntimeError(str(exc)) from exc
    runner = fax_flow.run_bulk if bulk else fax_flow.run
    result = runner(auth_id, sender, datetime.now().astimezone())
    if result.decision == "deny":
        raise RuntimeError(f"발송하지 않음({result.reason})")
    text = (
        f"{'드라이런 ' if result.dry_run else ''}발송 {result.sent}건, 실패 {result.failed}건, "
        f"확인 필요 {result.unknown}건, 건너뜀 {len(result.skipped)}건"
    )
    if result.decision == "skip":
        return f"보낼 대상 없음({result.reason})"
    if result.failed or result.unknown or result.stopped_midway:
        raise RuntimeError(text + (" — 정지·취소로 중단됨" if result.stopped_midway else ""))
    return text
