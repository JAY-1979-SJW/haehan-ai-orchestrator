"""PC Inventory MCP 서버 — Claude가 직접 로컬 PC 탐색 도구를 호출한다.

MCP stdio 서버. .mcp.json 에 등록하면 Claude Code에서 자동 인식.

제공 도구:
  pc_get_system      — 시스템 정보 (OS, CPU, RAM, 디스크)
  pc_list_apps       — 설치된 프로그램 목록
  pc_list_processes  — 실행 중인 프로세스 (상위 N개, 메모리 기준)
  pc_list_ports      — 열린(LISTEN) 포트 목록
  pc_list_services   — Windows 서비스 목록
  pc_list_startup    — 시작프로그램 목록
  pc_inventory_all   — 전체 수집 후 요약 반환
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

# scripts/ops/ 에서 직접 import
sys.path.insert(0, str(Path(__file__).parent))
from pc_inventory import (  # type: ignore[import-not-found]  # 같은 폴더 sys.path 추가 후 직접실행 지원(위 sys.path.insert) — 정적 분석 범위 밖
    SECTIONS,
    collect_all,
    collect_processes,
)

# ── MCP 최소 구현 (stdio JSON-RPC) ────────────────────────────────────────────


def _send(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _tool_result(content: Any, is_error: bool = False) -> dict:
    text = json.dumps(content, ensure_ascii=False, indent=2) if not isinstance(content, str) else content
    return {
        "content": [{"type": "text", "text": text}],
        "isError": is_error,
    }


TOOLS = [
    {
        "name": "pc_get_system",
        "description": "로컬 PC 시스템 정보 조회 (OS, CPU, RAM, 디스크)",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "pc_list_apps",
        "description": "설치된 프로그램 목록 조회 (이름·버전·설치일)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "프로그램명 필터 (포함 검색)"},
            },
        },
    },
    {
        "name": "pc_list_processes",
        "description": "실행 중인 프로세스 목록 (메모리 상위 N개)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "top": {"type": "integer", "description": "상위 N개 (기본 20)", "default": 20},
                "name_filter": {"type": "string", "description": "프로세스명 필터"},
            },
        },
    },
    {
        "name": "pc_list_ports",
        "description": "현재 LISTEN 중인 포트 목록",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "pc_list_services",
        "description": "Windows 서비스 목록 (이름·상태)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "status_filter": {
                    "type": "string",
                    "enum": ["RUNNING", "STOPPED", "all"],
                    "description": "상태 필터 (기본 all)",
                },
            },
        },
    },
    {
        "name": "pc_list_startup",
        "description": "Windows 시작프로그램 목록",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "pc_inventory_all",
        "description": "전체 PC 탐색 (시스템+앱+프로세스+포트+서비스+시작프로그램) 요약 반환",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
]


def _call_pc_apps(args: dict) -> dict:
    apps = SECTIONS["apps"]()
    q = (args.get("query") or "").lower()
    if q:
        apps = [a for a in apps if q in a["name"].lower()]
    return _tool_result({"count": len(apps), "apps": apps})


def _call_pc_processes(args: dict) -> dict:
    top = int(args.get("top") or 20)
    procs = collect_processes(top_n=max(top, 5))
    nf = (args.get("name_filter") or "").lower()
    if nf:
        procs = [p for p in procs if nf in p["name"].lower()]
    return _tool_result({"count": len(procs), "processes": procs[:top]})


def _call_pc_services(args: dict) -> dict:
    svcs = SECTIONS["services"]()
    sf = (args.get("status_filter") or "all").upper()
    if sf != "ALL":
        svcs = [s for s in svcs if s.get("status", "").upper() == sf]
    return _tool_result({"count": len(svcs), "services": svcs})


def _call_pc_inventory_all(args: dict) -> dict:
    data = collect_all()
    summary = {
        "collected_at": data.get("collected_at"),
        "system": data.get("system"),
        "installed_apps_count": len(data.get("apps", [])),
        "top10_apps": [a["name"] for a in (data.get("apps") or [])[:10]],
        "processes_count": len(data.get("processes", [])),
        "top10_processes": [f"{p['name']} ({p['mem_mb']}MB)" for p in (data.get("processes") or [])[:10]],
        "listen_ports": [f":{p['port']} ← {p['process']}" for p in (data.get("ports") or [])],
        "services_running": sum(1 for s in (data.get("services") or []) if s.get("status", "").upper() == "RUNNING"),
        "startup_count": len(data.get("startup", [])),
        "secret_values_output": False,
    }
    return _tool_result(summary)


_TOOL_CALLS = {
    "pc_get_system": lambda args: _tool_result(SECTIONS["system"]()),
    "pc_list_apps": _call_pc_apps,
    "pc_list_processes": _call_pc_processes,
    "pc_list_ports": lambda args: _tool_result(SECTIONS["ports"]()),
    "pc_list_services": _call_pc_services,
    "pc_list_startup": lambda args: _tool_result(SECTIONS["startup"]()),
    "pc_inventory_all": _call_pc_inventory_all,
}


def _handle_call(name: str, args: dict) -> dict:
    try:
        handler = _TOOL_CALLS.get(name)
        if handler is not None:
            return handler(args)

        return _tool_result({"error": f"unknown tool: {name}"}, is_error=True)
    except Exception as e:  # noqa: BLE001 - PC 인벤토리 MCP 도구 핸들러 최상위 캐치 - 각 도구는 read-only 조회이며 실패 시 에러 메시지를 결과로 반환할 뿐 상태를 변경하지 않음
        return _tool_result({"error": str(e)[:300]}, is_error=True)


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue

        rid = req.get("id")
        method = req.get("method", "")

        if method == "initialize":
            _send(
                {
                    "jsonrpc": "2.0",
                    "id": rid,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "pc-inventory", "version": "1.0.0"},
                    },
                }
            )

        elif method == "tools/list":
            _send({"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}})

        elif method == "tools/call":
            tool_name = req.get("params", {}).get("name", "")
            tool_args = req.get("params", {}).get("arguments", {})
            result = _handle_call(tool_name, tool_args)
            _send({"jsonrpc": "2.0", "id": rid, "result": result})

        elif method == "notifications/initialized":
            pass  # 응답 불필요

        else:
            _send(
                {
                    "jsonrpc": "2.0",
                    "id": rid,
                    "error": {
                        "code": -32601,
                        "message": f"method not found: {method}",
                    },
                }
            )


if __name__ == "__main__":
    main()
