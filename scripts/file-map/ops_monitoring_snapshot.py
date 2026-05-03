#!/usr/bin/env python3
"""
운영 모니터링 snapshot 스크립트.

목표:
- cleanup-execute 실행 기록 수집
- 통계 집계
- 건강성 판정

원칙:
- read-only만 수행
- 민감정보 미출력
- 로그 원문 금지
- 경로/token/payload 금지
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

def get_monitoring_stats():
    """모니터링 통계 수집."""
    stats = {
        "period": "last_24h",
        "total_executions": 0,
        "dry_run_true": 0,
        "dry_run_false": 0,
        "success_count_total": 0,
        "failed_count_total": 0,
        "conflict_count_total": 0,
        "token_reject_count": 0,
        "spawn_error_count": 0,
        "http_500_count": 0,
        "consecutive_zero_success": False,
        "health_status": "PASS",
    }

    # 로그 디렉터리 확인
    log_dir = Path.cwd() / "logs" / "file-map"
    if not log_dir.exists():
        return stats

    # 최근 24시간 로그 수집
    cutoff_time = datetime.now() - timedelta(hours=24)

    try:
        for log_file in log_dir.glob("cleanup-execute*.log"):
            if log_file.stat().st_mtime < cutoff_time.timestamp():
                continue

            try:
                with log_file.open() as f:
                    for line in f:
                        try:
                            record = json.loads(line)

                            stats["total_executions"] += 1

                            if record.get("dry_run"):
                                stats["dry_run_true"] += 1
                            else:
                                stats["dry_run_false"] += 1

                            stats["success_count_total"] += record.get("success_count", 0)
                            stats["failed_count_total"] += record.get("failed_count", 0)
                            stats["conflict_count_total"] += record.get("conflict_count", 0)

                            if record.get("token_rejected"):
                                stats["token_reject_count"] += 1

                            if record.get("spawn_error"):
                                stats["spawn_error_count"] += 1

                            if record.get("http_status") == 500:
                                stats["http_500_count"] += 1
                        except json.JSONDecodeError:
                            pass
            except Exception:
                pass
    except Exception:
        pass

    # 건강성 판정
    if stats["http_500_count"] > 5:
        stats["health_status"] = "FAIL"
    elif stats["spawn_error_count"] > 3 or stats["token_reject_count"] > 10:
        stats["health_status"] = "WARN"

    # dry_run=false 감지
    if stats["dry_run_false"] > 0:
        stats["health_status"] = "FAIL"
        stats["warning"] = "dry_run=false 실행 감지"

    return stats

if __name__ == '__main__':
    stats = get_monitoring_stats()

    result = {
        "timestamp": datetime.now().isoformat(),
        "test_type": "ops_monitoring_snapshot",
        "monitoring": stats,
        "status": stats.get("health_status", "PASS"),
    }

    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(0)
