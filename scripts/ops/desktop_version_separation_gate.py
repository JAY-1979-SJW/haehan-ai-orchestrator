"""데스크톱 앱 구버전/신버전 분리 강제 게이트.

신버전(모듈화된 lib/* + 통합 shell.html) 구조를 강제하고,
구버전 잔재(google-hub.html, 옛 네비바 shell, monolithic main.js)의
재유입을 차단한다. 신버전 설치/배포의 선행 게이트.

판정:
    FORBIDDEN_OLD_ARTIFACT > 0  → FAIL
    MISSING_MODULE        > 0   → FAIL
    NON_MODULAR           > 0   → FAIL
    그 외                       → PASS

사용:
    python scripts/ops/desktop_version_separation_gate.py
    python scripts/ops/desktop_version_separation_gate.py --json
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ELECTRON = ROOT / "admin-web" / "electron"
LIB = ELECTRON / "lib"

# 신버전 필수 모듈 (앱 실행 코드 모듈화 결과)
REQUIRED_MODULES = [
    "config.js",
    "agent.js",
    "mainWindow.js",
    "youtube.js",
    "licenseWindow.js",
    "tray.js",
]

# main.js 가 각 모듈을 실제로 wiring 하는지 확인할 require 토큰
REQUIRED_MAIN_REQUIRES = [
    "./lib/config",
    "./lib/agent",
    "./lib/mainWindow",
    "./lib/licenseWindow",
    "./lib/youtube",
    "./lib/tray",
]

# 구버전 잔재 파일 (존재 자체가 위반)
FORBIDDEN_FILES = [
    ELECTRON / "google-hub.html",
]

# 구버전 shell.html 네비바 마커 (신버전은 네비바 없이 / 통합 UI 로드)
OLD_SHELL_MARKERS = [
    'id="nav"',
    "btn-smartstore",
    "google-hub",
    "navigate('google-hub')",
    "dropdown-menu",
]

# monolithic main.js 마커 (모듈로 빠져야 하는 정의가 main.js에 인라인으로 남아있으면 위반)
MONOLITHIC_MAIN_MARKERS = [
    "function createLicenseWindow",
    "function openYouTubeOAuthPopup",
    "function createTray",
    "function startAgent",
]


@dataclass
class Finding:
    category: str   # FORBIDDEN_OLD_ARTIFACT | MISSING_MODULE | NON_MODULAR
    detail: str


@dataclass
class GateResult:
    findings: list[Finding] = field(default_factory=list)

    def add(self, category: str, detail: str) -> None:
        self.findings.append(Finding(category, detail))

    def count(self, category: str) -> int:
        return sum(1 for f in self.findings if f.category == category)

    @property
    def failed(self) -> bool:
        return len(self.findings) > 0


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def run_gate() -> GateResult:
    result = GateResult()

    # 1) 구버전 잔재 파일 금지
    for f in FORBIDDEN_FILES:
        if f.exists():
            result.add("FORBIDDEN_OLD_ARTIFACT", f"구버전 파일 잔존: {f.relative_to(ROOT)}")

    # 2) shell.html 구버전 네비바 마커 금지
    shell = _read(ELECTRON / "shell.html")
    for marker in OLD_SHELL_MARKERS:
        if marker in shell:
            result.add("FORBIDDEN_OLD_ARTIFACT", f"shell.html 구버전 마커: {marker!r}")

    # 3) 필수 모듈 존재
    for mod in REQUIRED_MODULES:
        if not (LIB / mod).exists():
            result.add("MISSING_MODULE", f"필수 모듈 누락: lib/{mod}")

    # 4) main.js 모듈 wiring + 비-monolithic
    main_js = _read(ELECTRON / "main.js")
    if not main_js:
        result.add("MISSING_MODULE", "main.js 를 읽을 수 없음")
    else:
        for token in REQUIRED_MAIN_REQUIRES:
            if token not in main_js:
                result.add("NON_MODULAR", f"main.js 가 {token} 를 require 하지 않음")
        for marker in MONOLITHIC_MAIN_MARKERS:
            if marker in main_js:
                result.add("NON_MODULAR", f"main.js 에 모듈화 대상 정의 잔존: {marker!r}")

    # 5) package.json build.files 가 lib 포함 + 구버전 파일 제외
    pkg_raw = _read(ELECTRON / "package.json")
    try:
        files = json.loads(pkg_raw).get("build", {}).get("files", [])
    except json.JSONDecodeError:
        files = []
        result.add("NON_MODULAR", "electron/package.json 파싱 실패")
    if not any("lib/" in str(x) for x in files):
        result.add("NON_MODULAR", "package.json build.files 에 lib/**/* 누락 (패키징 시 모듈 미포함)")
    if any("google-hub" in str(x) for x in files):
        result.add("FORBIDDEN_OLD_ARTIFACT", "package.json build.files 에 google-hub.html 참조 잔존")

    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", help="JSON 출력")
    args = ap.parse_args()

    result = run_gate()
    categories = ["FORBIDDEN_OLD_ARTIFACT", "MISSING_MODULE", "NON_MODULAR"]
    counts = {c: result.count(c) for c in categories}

    if args.json:
        print(json.dumps({
            "pass": not result.failed,
            "counts": counts,
            "findings": [{"category": f.category, "detail": f.detail} for f in result.findings],
        }, ensure_ascii=False, indent=2))
    else:
        print("=== 데스크톱 구버전/신버전 분리 게이트 ===")
        for c in categories:
            print(f"  {c}: {counts[c]}")
        if result.findings:
            print("--- 위반 상세 ---")
            for f in result.findings:
                print(f"  [{f.category}] {f.detail}")
        print("판정:", "FAIL" if result.failed else "PASS")

    return 1 if result.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
