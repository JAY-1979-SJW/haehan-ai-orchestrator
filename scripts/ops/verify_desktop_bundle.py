"""데스크톱 설치본 내용물 점검 — 빌드 직후, E2E(약 40분) 전에 빠진 파일을 1분 안에 잡는다.

2026-10-08 실측: electron-builder extraResources 가 Next.js standalone 의 .next/static·public 을 빠뜨려
설치본이 "로딩 중"에서 멈췄는데, 빌드는 성공으로 끝나 E2E 까지 가서야 드러났다.
도구는 설정대로만 묶고 빠진 것을 알려 주지 않으므로, 앱이 실행 때 찾는 경로를 여기서 직접 확인한다.
경로 기준은 admin-web/electron/lib/{fastapi_server,agent,nextjs_server,claude_mcp}.js 의 process.resourcesPath 사용처.

사용: python scripts/ops/verify_desktop_bundle.py <win-unpacked 폴더> [--dist <산출물 폴더>]
종료코드: 0 = 통과, 1 = 빠진 것 있음, 2 = 사용법 오류
"""

from __future__ import annotations

import argparse
import json
import re
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
    args = parser.parse_args(argv)
    resources = args.unpacked / "resources"
    if not resources.is_dir():
        print(f"resources 폴더가 없음: {resources}", file=sys.stderr)
        return 2
    problems = check_resources(resources)
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
