"""통합 개발현황 보고 — python scripts/cdp_client.py status

각 서비스 라우터의 __status__ 선언 + op_log DB 실행 기록을 조합해
전체 서비스 개발/운영 현황을 한눈에 출력한다.

출력 항목:
  - 서비스명 / 태스크 목록
  - 구현 상태: ✓(완성) △(부분) ✗(미구현) ??(알 수 없음)
  - 마지막 성공 실행 시각 (op_log 기준)
  - 최근 7일 실행 횟수 / 실패 횟수
"""
from __future__ import annotations

import importlib
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

# 서비스 라우터 레지스트리 (scripts/router.py 와 동기화)
_SERVICE_MAP: dict[str, str] = {
    "naver":      "scripts.naver.router",
    "google":     "scripts.google.router",
    "kakao":      "scripts.kakao.router",
    "eum":        "scripts.eum.router",
    "smartstore": "scripts.smartstore.router",
    "g2b":        "scripts.g2b.router",
    "local":      "scripts.local_agent.router",
    "explore":    "scripts.explorer.router",
}

_STATUS_ICON = {
    "done":    "✓",
    "partial": "△",
    "todo":    "✗",
    "wip":     "⋯",
}


def _load_router_status(module_path: str) -> dict[str, Any]:
    """라우터 모듈의 __status__ dict 로드. 없으면 빈 dict."""
    try:
        mod = importlib.import_module(module_path)
        return getattr(mod, "__status__", {})
    except Exception as e:
        return {"_error": str(e)}


def _query_op_stats(service_prefix: str) -> dict[str, Any]:
    """op_log DB에서 서비스 관련 최근 7일 통계 조회."""
    try:
        import sqlite3
        db_path = ROOT / "data" / "cdp.db"
        if not db_path.exists():
            return {}
        since = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        con = sqlite3.connect(str(db_path))
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        # 서비스 prefix로 op_name 매칭
        cur.execute("""
            SELECT op_name,
                   COUNT(*) as total,
                   SUM(CASE WHEN status='ok' THEN 1 ELSE 0 END) as ok_cnt,
                   SUM(CASE WHEN status='fail' THEN 1 ELSE 0 END) as fail_cnt,
                   MAX(CASE WHEN status='ok' THEN ts END) as last_ok
            FROM ops_log
            WHERE ts >= ? AND (op_name LIKE ? OR op_name LIKE ?)
            GROUP BY op_name
            ORDER BY total DESC
        """, (since, f"{service_prefix}.%", f"{service_prefix}_%"))
        rows = [dict(r) for r in cur.fetchall()]

        # 전체 서비스 마지막 성공 시각
        cur.execute("""
            SELECT MAX(ts) as last_ok, COUNT(*) as total,
                   SUM(CASE WHEN status='fail' THEN 1 ELSE 0 END) as fail_cnt
            FROM ops_log
            WHERE ts >= ? AND (op_name LIKE ? OR op_name LIKE ?)
              AND status IN ('ok','fail')
        """, (since, f"{service_prefix}.%", f"{service_prefix}_%"))
        summary = dict(cur.fetchone() or {})
        con.close()
        return {"ops": rows, "summary": summary}
    except Exception:
        return {}


def _fmt_ts(ts: str | None) -> str:
    if not ts:
        return "-"
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        local = dt.astimezone()
        return local.strftime("%m/%d %H:%M")
    except Exception:
        return ts[:16] if ts else "-"


def report(verbose: bool = False) -> None:
    """전체 서비스 개발현황 출력."""
    print("=" * 70)
    print("  개발현황 보고 (서비스별 구현 상태 + 최근 7일 실행 기록)")
    print(f"  기준: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 70)

    for svc, module in _SERVICE_MAP.items():
        status = _load_router_status(module)
        stats = _query_op_stats(svc)
        summary = stats.get("summary", {})
        ops = stats.get("ops", [])

        last_ok = _fmt_ts(summary.get("last_ok"))
        total_7d = summary.get("total") or 0
        fail_7d = summary.get("fail_cnt") or 0

        # 헤더
        err_flag = " ⚠ 로드오류" if "_error" in status else ""
        print(f"\n▶ [{svc.upper()}]{err_flag}")
        if "_error" in status:
            print(f"   {status['_error']}")

        # 태스크 현황
        tasks: dict[str, str] = status.get("tasks", {})
        if tasks:
            for t_name, t_state in tasks.items():
                icon = _STATUS_ICON.get(t_state, "?")
                print(f"   {icon} {t_name}")
        else:
            print("   (tasks 선언 없음 — 구현 상태 미등록)")

        # 메모
        note = status.get("note", "")
        if note:
            print(f"   📌 {note}")

        # 실행 기록
        if total_7d:
            ok_7d = total_7d - fail_7d
            bar = f"{ok_7d}성공 / {fail_7d}실패 / {total_7d}회 (7일)"
            print(f"   🕐 마지막 성공: {last_ok}  |  {bar}")
            if verbose and ops:
                for op in ops[:5]:
                    print(f"      {op['op_name']:<30} ok={op['ok_cnt']} fail={op['fail_cnt']}")
        else:
            print(f"   🕐 최근 7일 실행 기록 없음")

    print("\n" + "=" * 70)
    print("  범례: ✓완성  △부분구현  ✗미구현  ⋯개발중")
    print("=" * 70)
