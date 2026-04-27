"""시스템 상태 조회용 read-only 커넥터.

- 외부 명령 실행 금지 (subprocess 사용 안 함).
- psutil + os 기반으로 CPU / 메모리 / uptime 만 반환.
"""

import os
import time

try:
    import psutil
    _HAS_PSUTIL = True
except ImportError:
    psutil = None
    _HAS_PSUTIL = False


def get_server_status() -> dict:
    """read-only 서버 상태 스냅샷."""
    if not _HAS_PSUTIL:
        return {
            "cpu_percent": None,
            "memory": None,
            "uptime_sec": None,
            "note": "psutil_not_installed",
        }

    cpu_percent = psutil.cpu_percent(interval=0.1)
    mem = psutil.virtual_memory()
    boot_time = psutil.boot_time()
    uptime_sec = max(0, int(time.time() - boot_time))

    return {
        "cpu_percent": cpu_percent,
        "memory": {
            "total_mb": int(mem.total / (1024 * 1024)),
            "used_mb": int((mem.total - mem.available) / (1024 * 1024)),
            "percent": mem.percent,
        },
        "uptime_sec": uptime_sec,
        "pid": os.getpid(),
    }
