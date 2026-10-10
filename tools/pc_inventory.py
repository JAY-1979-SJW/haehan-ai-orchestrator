"""로컬 PC 탐색 도구 — 설치 프로그램·프로세스·서비스·포트·시작프로그램 수집.

단독 실행:
  python tools/pc_inventory.py
  python tools/pc_inventory.py --json       # JSON 출력
  python tools/pc_inventory.py --save       # data/local/ 저장
  python tools/pc_inventory.py --section apps  # 특정 섹션만

보안:
  - 레지스트리 읽기 전용
  - password/token/secret 포함 금지
  - 결과 외부 전송 없음
"""

from __future__ import annotations

import argparse
import contextlib
import json
import platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psutil

_BOOT = Path(__file__).resolve().parents[1]  # 정본을 import 하기 전 sys.path 부트스트랩(G5 예외: scripts/ 독립 실행)
if str(_BOOT) not in sys.path:
    sys.path.insert(0, str(_BOOT))

from scripts.common.app_paths import repo_root  # noqa: E402

ROOT = repo_root()
OUTPUT_DIR = ROOT / "data" / "local"

# 민감 키워드 — 값 마스킹
_SENSITIVE = {"password", "passwd", "secret", "token", "apikey", "api_key", "credential"}


def _mask(text: str) -> str:
    low = text.lower()
    if any(k in low for k in _SENSITIVE):
        return "***REDACTED***"
    return text


# ── 시스템 정보 ────────────────────────────────────────────────────────────────


def collect_system() -> dict[str, Any]:
    vm = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    cpu_freq = psutil.cpu_freq()
    return {
        "os": platform.system(),
        "os_version": platform.version()[:80],
        "os_release": platform.release(),
        "hostname": platform.node(),
        "architecture": platform.machine(),
        "cpu_physical_cores": psutil.cpu_count(logical=False),
        "cpu_logical_cores": psutil.cpu_count(logical=True),
        "cpu_freq_mhz": round(cpu_freq.current) if cpu_freq else None,
        "ram_total_gb": round(vm.total / 1024**3, 1),
        "ram_available_gb": round(vm.available / 1024**3, 1),
        "ram_used_pct": vm.percent,
        "disk_total_gb": round(disk.total / 1024**3, 1),
        "disk_free_gb": round(disk.free / 1024**3, 1),
        "disk_used_pct": round(disk.used / disk.total * 100, 1),
        "python_version": sys.version.split()[0],
    }


# ── 설치된 프로그램 (레지스트리) ────────────────────────────────────────────────


def collect_installed_apps() -> list[dict[str, Any]]:
    try:
        import winreg
    except ImportError:
        return [{"error": "winreg_not_available"}]

    apps: dict[str, dict] = {}
    keys = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]
    for hive, path in keys:
        try:
            with winreg.OpenKey(hive, path) as base:
                count = winreg.QueryInfoKey(base)[0]
                for i in range(count):
                    try:
                        sub_name = winreg.EnumKey(base, i)
                        with winreg.OpenKey(base, sub_name) as sub:

                            def _val(name: str) -> str:
                                try:
                                    return str(winreg.QueryValueEx(sub, name)[0])
                                except OSError:
                                    return ""

                            display = _val("DisplayName").strip()
                            if not display or display.startswith("{"):
                                continue
                            version = _val("DisplayVersion")
                            install_date = _val("InstallDate")
                            publisher = _val("Publisher")
                            key = display.lower()
                            if key not in apps:
                                apps[key] = {
                                    "name": display,
                                    "version": version or None,
                                    "publisher": publisher or None,
                                    "install_date": install_date or None,
                                }
                    except OSError:
                        continue
        except OSError:
            continue

    return sorted(apps.values(), key=lambda x: x["name"].lower())


# ── 실행 중인 프로세스 ──────────────────────────────────────────────────────────


def collect_processes(top_n: int = 50) -> list[dict[str, Any]]:
    procs = []
    for p in psutil.process_iter(["pid", "name", "status", "cpu_percent", "memory_info", "exe", "username"]):
        try:
            info = p.info
            exe = info.get("exe") or ""
            # 경로에서 민감 정보 마스킹
            exe = _mask(exe)
            mem_mb = round(info["memory_info"].rss / 1024**2, 1) if info.get("memory_info") else 0
            procs.append(
                {
                    "pid": info["pid"],
                    "name": info["name"],
                    "status": info["status"],
                    "cpu_pct": info.get("cpu_percent", 0.0),
                    "mem_mb": mem_mb,
                    "exe": exe,
                }
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    # CPU + 메모리 기준 상위 N개
    procs.sort(key=lambda x: x["mem_mb"], reverse=True)
    return procs[:top_n]


# ── 열린 포트 ───────────────────────────────────────────────────────────────────


def collect_ports() -> list[dict[str, Any]]:
    pid_to_name: dict[int, str] = {}
    for p in psutil.process_iter(["pid", "name"]):
        with contextlib.suppress(psutil.NoSuchProcess, psutil.AccessDenied):
            pid_to_name[p.pid] = p.info["name"]

    ports = []
    seen: set[int] = set()
    for conn in psutil.net_connections(kind="inet"):
        if conn.status != "LISTEN" or not conn.laddr:
            continue
        port = conn.laddr.port
        if port in seen:
            continue
        seen.add(port)
        pid = conn.pid or 0
        ports.append(
            {
                "port": port,
                "address": conn.laddr.ip,
                "pid": pid,
                "process": pid_to_name.get(pid, "unknown"),
            }
        )
    return sorted(ports, key=lambda x: x["port"])


# ── Windows 서비스 ──────────────────────────────────────────────────────────────


def collect_services() -> list[dict[str, Any]]:
    try:
        result = subprocess.run(
            ["sc", "query", "type=", "all", "state=", "all"],
            capture_output=True,
            text=True,
            timeout=15,
            encoding="utf-8",
        )
        services = []
        current: dict[str, str] = {}
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.startswith("SERVICE_NAME:"):
                if current:
                    services.append(current)
                current = {"name": line.split(":", 1)[1].strip()}
            elif line.startswith("DISPLAY_NAME:"):
                current["display"] = line.split(":", 1)[1].strip()
            elif line.startswith("STATE"):
                parts = line.split()
                current["status"] = parts[3] if len(parts) > 3 else "unknown"
            elif line.startswith("TYPE"):
                current["type"] = line.split(":", 1)[1].strip() if ":" in line else ""
        if current:
            services.append(current)
        return sorted(
            [s for s in services if s.get("name")],
            key=lambda x: x.get("display", x["name"]).lower(),
        )
    except Exception as e:  # noqa: BLE001 - 로컬 PC 정보 조회(읽기전용) — 조회 실패시 오류 문자열만 결과에 담아 반환, 시스템 변경 없음
        return [{"error": str(e)[:100]}]


# ── 시작프로그램 ────────────────────────────────────────────────────────────────


def collect_startup() -> list[dict[str, Any]]:
    try:
        import winreg
    except ImportError:
        return []

    startup: list[dict[str, Any]] = []
    run_keys = [
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Run"),
    ]
    for hive, path in run_keys:
        try:
            with winreg.OpenKey(hive, path) as key:
                i = 0
                while True:
                    try:
                        name, value, _ = winreg.EnumValue(key, i)
                        startup.append({"name": name, "command": _mask(value[:200])})
                        i += 1
                    except OSError:
                        break
        except OSError:
            continue
    return startup


# ── 전체 수집 ───────────────────────────────────────────────────────────────────

SECTIONS = {
    "system": collect_system,
    "apps": collect_installed_apps,
    "processes": collect_processes,
    "ports": collect_ports,
    "services": collect_services,
    "startup": collect_startup,
}


def collect_all(sections: list[str] | None = None) -> dict[str, Any]:
    targets = sections or list(SECTIONS)
    result: dict[str, Any] = {
        "collected_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "secret_values_output": False,
    }
    for name in targets:
        if name in SECTIONS:
            try:
                result[name] = SECTIONS[name]()
            except Exception as e:  # noqa: BLE001 - 로컬 PC 정보 조회(읽기전용) — 조회 실패시 오류 문자열만 결과에 담아 반환, 시스템 변경 없음
                result[name] = {"error": str(e)[:200]}
    return result


def save(data: dict) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = OUTPUT_DIR / f"pc_inventory_{ts}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    # latest 심볼 (항상 최신 결과)
    latest = OUTPUT_DIR / "pc_inventory_latest.json"
    latest.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="로컬 PC 탐색 도구")
    parser.add_argument("--json", action="store_true", help="JSON 형식으로 출력")
    parser.add_argument("--save", action="store_true", help="data/local/에 저장")
    parser.add_argument(
        "--section",
        choices=list(SECTIONS),
        default=None,
        help="특정 섹션만 수집 (기본: 전체)",
    )
    parser.add_argument("--top", type=int, default=50, help="프로세스 상위 N개 (기본 50)")
    args = parser.parse_args()

    sections = [args.section] if args.section else None
    print(f"[pc_inventory] 수집 중: {sections or '전체'} ...", file=sys.stderr)
    data = collect_all(sections)

    if args.save:
        path = save(data)
        print(f"[pc_inventory] 저장 완료: {path}", file=sys.stderr)

    if args.json or args.save:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        _print_summary(data)


def _print_system_section(s: dict) -> None:
    print(f"\n{'=' * 50}")
    print(f"  시스템: {s.get('os')} {s.get('os_release')}  {s.get('hostname')}")
    print(
        f"  CPU: {s.get('cpu_physical_cores')}코어/{s.get('cpu_logical_cores')}스레드  "
        f"RAM: {s.get('ram_total_gb')}GB ({s.get('ram_used_pct')}% 사용)"
    )
    print(f"  디스크: {s.get('disk_total_gb')}GB (여유 {s.get('disk_free_gb')}GB)")


def _print_apps_section(apps: list) -> None:
    print(f"\n  설치 프로그램: {len(apps)}개")
    for a in apps[:10]:
        ver = f" v{a['version']}" if a.get("version") else ""
        print(f"    • {a['name']}{ver}")
    if len(apps) > 10:
        print(f"    ... 외 {len(apps) - 10}개")


def _print_processes_section(procs: list) -> None:
    print("\n  실행 프로세스 상위 10 (메모리 기준):")
    for p in procs[:10]:
        print(f"    [{p['pid']:6}] {p['name']:<30} {p['mem_mb']:>7.1f}MB")


def _print_ports_section(ports: list) -> None:
    print(f"\n  리스닝 포트 ({len(ports)}개):")
    for p in ports:
        print(f"    :{p['port']:<6} ← {p['process']} (PID {p['pid']})")


def _print_startup_section(items: list) -> None:
    print(f"\n  시작프로그램 ({len(items)}개):")
    for s in items:
        print(f"    • {s['name']}")


def _print_summary(data: dict) -> None:
    if "system" in data:
        _print_system_section(data["system"])

    # list 형태일 때만 출력하는 섹션들 (출력 순서 유지)
    for key, printer in (
        ("apps", _print_apps_section),
        ("processes", _print_processes_section),
        ("ports", _print_ports_section),
        ("startup", _print_startup_section),
    ):
        if key in data and isinstance(data[key], list):
            printer(data[key])

    print(f"\n{'=' * 50}")
    print(f"  수집시각: {data.get('collected_at', '-')}")


if __name__ == "__main__":
    main()
