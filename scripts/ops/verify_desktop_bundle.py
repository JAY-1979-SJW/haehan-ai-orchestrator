"""데스크톱 설치본 내용물 점검 — 빌드 직후, E2E(약 40분) 전에 빠진 파일을 1분 안에 잡는다.

2026-10-08 실측: electron-builder extraResources 가 Next.js standalone 의 .next/static·public 을 빠뜨려
설치본이 "로딩 중"에서 멈췄는데, 빌드는 성공으로 끝나 E2E 까지 가서야 드러났다.
도구는 설정대로만 묶고 빠진 것을 알려 주지 않으므로, 앱이 실행 때 찾는 경로를 여기서 직접 확인한다.
경로 기준은 admin-web/electron/lib/{fastapi_server,agent,nextjs_server,claude_mcp}.js 의 process.resourcesPath 사용처.

사용: python scripts/ops/verify_desktop_bundle.py <win-unpacked 폴더> [--dist <산출물 폴더>] [--smoke]
종료코드: 0 = 통과, 1 = 빠진 것 있음, 2 = 사용법 오류

`--smoke`(기본 꺼짐, 기존 호출 안 깨지게): exe "존재"만으론 못 잡는 결함을 추가로 본다
(2026-10-10 실측: local-agent.exe·haehan-mcp.exe 가 정본 모듈이 빠진 shim 진입점인 채로도
"파일이 있다"는 이유로 통과했다, W2 가 e25dd442 로 수정). local-agent.exe 는 인자 없이
실행해 argparse usage(종료코드 2)까지 도달하는지, haehan-mcp.exe 는 stdin 을 닫고 실행해
출력에 ModuleNotFoundError·ImportError·"Failed to execute script" 가 없는지 본다(각 30초
타임아웃). haehan-server.exe 는 E2E(HTTP 기동까지 실제로 확인)가 다루므로 여기선 제외.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

# (resources 기준 상대 경로, 종류) — file: 비어 있지 않은 파일, dir: 파일이 1개 이상 든 폴더
REQUIRED: list[tuple[str, str]] = [
    ("server/haehan-server/haehan-server.exe", "file"),
    ("local-agent/local-agent.exe", "file"),
    # local-agent-ai(AI 작업 콘솔 로컬 에이전트)는 이번 이식 범위 밖(보류, 2026-10-10
    # BUILD_PLAN 0' 단계 — updater.js·main.js 연동과 함께 별도 승인 예정). asm 은 아직
    # 그 PyInstaller 스펙·워크플로우 단계가 없어 여기서 요구하면 항상 FAIL 한다.
    ("mcp/haehan-mcp/haehan-mcp.exe", "file"),
    ("nextjs/server.js", "file"),
    ("nextjs/node_modules/next", "dir"),
    # Next.js standalone 배포 공식 요구사항: 정적 자산은 배포 쪽에서 직접 복사해야 한다(빠지면 화면 JS·CSS 404)
    ("nextjs/.next/static", "dir"),
    ("nextjs/public", "dir"),
    ("build-info.json", "file"),
]
BUILD_VERSION_RE = re.compile(r"^\d{8}-[0-9a-f]{7}$")


def _has_files(folder: Path) -> bool:
    return any(p.is_file() for p in folder.rglob("*"))


def check_resources(resources: Path) -> list[str]:
    """빠졌거나 비어 있는 항목의 설명 목록(비어 있으면 통과)."""
    problems: list[str] = []
    for rel, kind in REQUIRED:
        path = resources / rel
        if kind == "file" and not (path.is_file() and path.stat().st_size > 0):
            problems.append(f"파일 없음 또는 비어 있음: resources/{rel}")
        elif kind == "dir" and not (path.is_dir() and _has_files(path)):
            problems.append(f"폴더 없음 또는 비어 있음: resources/{rel}")
    static_dir = resources / "nextjs" / ".next" / "static"
    if static_dir.is_dir() and not any(static_dir.rglob("*.js")):
        problems.append("화면 JS 묶음 없음: resources/nextjs/.next/static 안에 .js 파일이 하나도 없음")
    info = resources / "build-info.json"
    if info.is_file():
        try:
            version = json.loads(info.read_text(encoding="utf-8-sig")).get("version", "")
        except (json.JSONDecodeError, OSError) as exc:
            problems.append(f"build-info.json 을 읽을 수 없음: {exc}")
        else:
            if not BUILD_VERSION_RE.match(str(version)):
                problems.append(f"build-info.json version 형식이 아님(<yyyymmdd>-<sha7> 기대): {version!r}")
    if not ((resources / "app.asar").is_file() or (resources / "app" / "main.js").is_file()):
        problems.append("앱 본체 없음: resources/app.asar 또는 resources/app/main.js")
    return problems


SMOKE_TIMEOUT_S = 30


def check_smoke(resources: Path, run=subprocess.run) -> list[str]:
    """`--smoke`: exe "존재"만으론 못 잡는 결함(정본 모듈 누락 등)을 실제로 한 번 실행해 본다.

    local-agent.exe 는 인자 없이 실행 — argparse usage 로 바로 끝나면(종료코드 2) 정본
    모듈이 로드된 것(모듈이 없으면 보통 트레이스백·다른 종료코드). haehan-mcp.exe 는
    stdin 을 바로 닫고 실행(MCP 서버는 stdio 로 명령을 기다리므로 안 닫으면 걸림) —
    출력에 ModuleNotFoundError·ImportError·"Failed to execute script"(PyInstaller 번들
    자체 로드 실패 메시지)가 있으면 FAIL. haehan-server.exe 는 E2E 가 실제 HTTP 기동까지
    보므로 여기선 안 본다. 두 exe 모두 없으면(이식 전 등) 조용히 넘어간다(존재 점검은
    REQUIRED 쪼가 이미 함).
    """
    problems: list[str] = []
    bad_markers = ("ModuleNotFoundError", "ImportError", "Failed to execute script")

    local_agent = resources / "local-agent" / "local-agent.exe"
    if local_agent.is_file():
        try:
            proc = run([str(local_agent)], capture_output=True, timeout=SMOKE_TIMEOUT_S, input=b"")
        except subprocess.TimeoutExpired:
            problems.append(f"local-agent.exe 가 {SMOKE_TIMEOUT_S}초 안에 안 끝남(인자 없이 실행 — argparse usage 로 바로 끝나야 함)")
        else:
            if proc.returncode != 2:
                text = ((proc.stdout or b"") + (proc.stderr or b"")).decode("utf-8", errors="replace")
                problems.append(
                    f"local-agent.exe 가 인자 없이 실행했을 때 종료코드 2(argparse usage)가 아님: {proc.returncode} — {text[:200]!r}"
                )

    haehan_mcp = resources / "mcp" / "haehan-mcp" / "haehan-mcp.exe"
    if haehan_mcp.is_file():
        try:
            proc = run([str(haehan_mcp)], capture_output=True, timeout=SMOKE_TIMEOUT_S, input=b"")
        except subprocess.TimeoutExpired:
            problems.append(f"haehan-mcp.exe 가 {SMOKE_TIMEOUT_S}초 안에 안 끝남(stdin 닫고 실행)")
        else:
            text = ((proc.stdout or b"") + (proc.stderr or b"")).decode("utf-8", errors="replace")
            hit = [m for m in bad_markers if m in text]
            if hit:
                problems.append(f"haehan-mcp.exe 실행 출력에 모듈/번들 로드 실패 신호: {', '.join(hit)}")
    return problems


def check_dist(dist: Path) -> list[str]:
    """설치형 산출물(setup.exe)이 함께 나왔는지.

    자동 업데이트 메타데이터(latest.yml·*.blockmap) 점검은 electron-updater 연동(이번
    이식 범위 밖, 보류)과 함께 나중에 추가한다 — asm 은 아직 publish 설정이 없어
    latest.yml 이 안 생긴다.
    """
    problems: list[str] = []
    if not list(dist.glob("HaehanAI-*-setup.exe")):
        problems.append(f"설치 파일 없음: {dist}/HaehanAI-*-setup.exe")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="데스크톱 설치본 내용물 점검")
    parser.add_argument("unpacked", type=Path, help="electron-builder 의 win-unpacked 폴더")
    parser.add_argument("--dist", type=Path, help="설치 파일이 나오는 산출물 폴더(주면 setup.exe·latest.yml 도 확인)")
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="local-agent.exe·haehan-mcp.exe 를 실제로 한 번 실행해 정본 모듈 누락을 잡는다(기본 꺼짐, 각 30초 타임아웃)",
    )
    args = parser.parse_args(argv)
    resources = args.unpacked / "resources"
    if not resources.is_dir():
        print(f"resources 폴더가 없음: {resources}", file=sys.stderr)
        return 2
    problems = check_resources(resources)
    if args.smoke:
        problems += check_smoke(resources)
    if args.dist is not None:
        problems += check_dist(args.dist)
    if problems:
        print(f"설치본 점검 실패 — {len(problems)}건")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"설치본 점검 통과 — 필수 항목 {len(REQUIRED)}개 + 화면 JS·버전 정보·앱 본체 확인")
    return 0


if __name__ == "__main__":
    sys.exit(main())
