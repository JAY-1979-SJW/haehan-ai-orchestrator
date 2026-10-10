"""폴더 승인 게이트 (G16) — 코드가 있는 폴더는 승인된 목록(configs/folder_registry.json)에 있어야 한다. 새 폴더는 대표님 승인 없이 못 만든다.

정본 목록: configs/folder_registry.json — 코드(.py·.ts·.tsx·.js)가 들어 있는 **모든 폴더** 한 줄씩(path·purpose·kind·status·approved_at·approved_by).
하위 폴더도 각각 등록해야 한다(예: scripts/browser/ 와 scripts/browser/cdp/ 는 별개). 설계: docs/architecture/FOLDER_STRUCTURE.md,
절차: 작업 창 → 지휘창에 '새 폴더 요청(경로·목적·왜 기존 폴더로 안 되는지)' → 대표님 승인 → 목록 추가 커밋 → PR 에 라벨 folder-approved(지휘창만 붙인다).

사용:
    python tools/repo_gates/folder_gate.py --staged                      # pre-commit: 새로 추가(A)·이름변경(R)된 코드 파일의 폴더가 목록에 없으면 차단
    python tools/repo_gates/folder_gate.py --check-all                   # CI: 추적 코드 파일 전체의 폴더가 목록에 있어야 통과
    python tools/repo_gates/folder_gate.py --check-approval --base B --head H [--event E] [--labels L1,L2]
                                                                    # CI: B→H 에서 목록에 항목이 '추가'됐으면 승인 증거(라벨)를 요구
    python tools/repo_gates/folder_gate.py --init-registry               # 목록이 없을 때만: 현재 트리 + 사전 승인 폴더로 최초 생성
    python tools/repo_gates/folder_gate.py --classify <폴더 또는 파일 경로...>

승인 증거(--check-approval):
    - pull_request  : 목록에 항목이 추가됐으면 라벨 folder-approved 가 있어야 통과(라벨은 지휘창만 붙인다).
    - workflow_dispatch : 추가가 있으면 FAIL(라벨을 확인할 PR 이 없다).
    - push          : 추가를 경고로 알리고 통과한다 — 병합 전 PR 에서 이미 라벨을 확인했고, 병합 직후 push 실행이 같은 추가를 다시 막으면
                      승인된 병합이 master CI 를 깨뜨린다. (--on-push fail 로 바꿀 수 있다.)
    - 기준(base)에 목록 파일이 아직 없으면(이 게이트를 처음 넣는 PR) 초기 등록으로 보고 통과한다(현재 트리·설계서 사전 승인분).
    - 삭제는 승인이 필요 없다(줄이는 방향).
우회 옵션 없음 — 승인된 폴더에 두거나, 새 폴더가 정말 필요하면 위 승인 절차를 밟는다.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path, PurePosixPath

_BOOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
if str(_BOOT) not in sys.path:
    sys.path.insert(0, str(_BOOT))

from scripts.common.app_paths import repo_root  # noqa: E402
from tools.repo_gates.tool_home_gate import staged_added, tracked_files  # noqa: E402

ROOT = repo_root()
REGISTRY = "configs/folder_registry.json"
LABEL = "folder-approved"
CODE_EXT = frozenset({".py", ".ts", ".tsx", ".js"})
APPROVED_AT = "2026-10-07"
APPROVED_BY = "대표님(사전 승인: 현재 트리·설계서 §1·§1-1·§1-2)"

# 설계서(FOLDER_STRUCTURE_DESIGN.md §1·§1-1·§1-2)의 목표 폴더 — 대표님이 이미 승인한 설계라 사전 승인으로 한 번에 등록한다.
# (경로, 목적, kind)
PRE_APPROVED_TARGETS: tuple[tuple[str, str, str], ...] = (
    ("ai_orchestrator/core", "서버 공용 기반(models·task_state·execution_limits·logging_setup)", "공용 기반"),
    ("ai_orchestrator/llm", "LLM 호출·가드(app_llm·openai_client·openai_guard·planner)", "공용 기반"),
    ("ai_orchestrator/mcp", "MCP 서버·도구 이름(mcp_server·mcp_tool_names)", "기능"),
    ("ai_orchestrator/notify", "알림(텔레그램 발송·웹훅·경보 분류)", "기능"),
    ("ai_orchestrator/tasks", "작업 실행·템플릿·외부 작업 레지스트리", "기능"),
    ("ai_orchestrator/agent_hub", "서버 쪽 로컬 에이전트 관리(T4)", "기능"),
    ("ai_orchestrator/agent_hub/router", "에이전트 관리 라우터(T4)", "기능"),
    ("ai_orchestrator/agent_hub/registry", "에이전트 레지스트리(T4)", "기능"),
    ("ai_orchestrator/agent_hub/policy", "에이전트 정책(T4)", "기능"),
    ("ai_orchestrator/audit", "감사 로그 정본(잎, T1)", "공용 기반"),
    ("ai_orchestrator/site_work", "사이트 탐색·AI 직원 서버 쪽 기능(F1)", "기능"),
    ("ai_orchestrator/agent_dispatch", "에이전트 작업 배정(F2)", "기능"),
    ("ai_orchestrator/gongmu", "공무(F9)", "기능"),
    ("ai_orchestrator/scheduler", "예약 작업(F10)", "기능"),
    ("ai_orchestrator/vendor_directory", "업체 디렉터리(F11)", "기능"),
    ("ai_orchestrator/dev_reg", "개발자 등록 승인(F12)", "기능"),
    ("ai_orchestrator/web_task", "웹 작업 레지스트리·승인(F13)", "기능"),
    ("ai_orchestrator/marketing", "마케팅 운영실(F14)", "기능"),
    ("ai_orchestrator/auth", "로그인·계정·등록 코드(F15)", "기능"),
    ("ai_orchestrator/user_data", "사용자 데이터 기여(F16)", "기능"),
    ("ai_orchestrator/connectors/hanafax", "하나팩스 API(F4)", "도구"),
    ("ai_orchestrator/connectors/naver_cafe", "네이버 카페 API(F5)", "도구"),
    ("ai_orchestrator/connectors/naver_mail", "네이버 메일 API(F3)", "도구"),
    ("ai_orchestrator/connectors/naver_blog", "네이버 블로그 API(F6)", "도구"),
    ("ai_orchestrator/connectors/youtube", "유튜브 API(F6)", "도구"),
    ("ai_orchestrator/connectors/google", "구글 API(F7)", "도구"),
    ("ai_orchestrator/connectors/g2b", "나라장터 API(F8)", "도구"),
    ("scripts/common", "스크립트 공용 기반(config·logger·op_log·gate·app_paths 등)", "공용 기반"),
    ("scripts/browser", "브라우저 기반 한 곳", "공용 기반"),
    ("scripts/browser/cdp", "CDP 연결·모니터", "공용 기반"),
    ("scripts/browser/session", "브라우저 세션·수명·게이트", "공용 기반"),
    ("scripts/browser/page", "페이지 도우미·분석", "공용 기반"),
    ("scripts/browser/navigator", "네비게이터", "공용 기반"),
    ("scripts/browser/popup", "팝업 처리", "공용 기반"),
    ("scripts/auth", "로그인·인증 세션·자격 증명", "공용 기반"),
    ("scripts/ops/quality", "품질 게이트·설치 도구", "공용 기반"),
    ("scripts/explorer", "사이트 탐색 브라우저 쪽(F1)", "도구"),
)

# 정리 대상(설계서 §1 '정리 대상'): 참조 조사 후 소속 폴더로 이동하거나 archive 로 — 새 코드를 두지 않는다.
LEGACY_TO_REMOVE: frozenset[str] = (
    frozenset()
)  # S6 완료(2026-10-08) — 정리 대상 폴더 없음. 생기면 여기에 최상위 이름을 적는다

_NAME_PURPOSE = {
    "routers": "FastAPI 라우터",
    "persistence": "저장소(DB·JSONL)",
    "gates": "게이트·승인·정책",
    "domain": "도메인 규칙",
    "services": "서비스 로직",
    "workflows": "업무 흐름",
    "sites": "사이트 어댑터",
    "contracts": "공유 계약·스키마",
    "server": "서버 보조",
    "connectors": "외부 서비스 연결 API",
    "paths": "경로·데이터 위치 정본",
    "tests": "시험",
    "ops": "운영·감사 도구",
    "archive": "일회성·보관(삭제 아님)",
    "src": "소스",
    "app": "Next 앱 라우트",
    "components": "화면 컴포넌트",
    "lib": "공용 라이브러리",
    "electron": "Electron 데스크톱 쉘",
    "local_agent": "PC 실행 에이전트",
    "browser_tool": "브라우저 도구",
    "site_engine": "사이트 엔진",
    "adapters": "어댑터(정리 대상)",
}


def _norm(p: str) -> str:
    p = p.replace("\\", "/").strip("/")
    return p or "."


def folder_of(path: str) -> str:
    """파일 경로 → 그 파일이 든 폴더(저장소 루트는 '.')."""
    parent = str(PurePosixPath(path.replace("\\", "/")).parent)
    return "." if parent in ("", ".") else parent


def is_code(path: str) -> bool:
    return PurePosixPath(path.replace("\\", "/")).suffix.lower() in CODE_EXT


def load_registry(root: Path = ROOT) -> dict[str, dict]:
    p = root / REGISTRY
    if not p.is_file():
        return {}
    return {_norm(e["path"]): e for e in json.loads(p.read_text(encoding="utf-8")).get("folders", [])}


def registry_paths_at(root: Path, ref: str) -> set[str] | None:
    """커밋 ref 시점의 등록 폴더 집합. 그 시점에 목록 파일이 없으면 None(초기 등록 판단용)."""
    r = subprocess.run(
        ["git", "show", f"{ref}:{REGISTRY}"],
        cwd=str(root),
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if r.returncode != 0:
        return None
    try:
        return {_norm(e["path"]) for e in json.loads(r.stdout).get("folders", [])}
    except (json.JSONDecodeError, KeyError, TypeError):
        return None


def code_folders(files: Iterable[str], root: Path | None = None) -> dict[str, int]:
    """코드 파일이 든 폴더 → 파일 수. root 가 있으면 실제로 존재하는 파일만 센다."""
    out: dict[str, int] = {}
    for f in files:
        if is_code(f) and (root is None or (root / f).exists()):
            d = folder_of(f)
            out[d] = out.get(d, 0) + 1
    return out


def unregistered(folders: Iterable[str], registry: dict[str, dict]) -> list[str]:
    return sorted({f for f in folders if f not in registry})


def _kind_and_status(path: str) -> tuple[str, str]:
    top = path.split("/")[0]
    if top in LEGACY_TO_REMOVE:
        return "레거시", "legacy_to_remove"
    if top == "tests" or path.endswith("/tests") or "/tests/" in path or top == "e2e":
        return "시험", "approved"
    if top == "apps":
        return "앱", "approved"
    if top == "admin-web":
        return "앱", "approved"
    if top == "orchestrator_v1" or "archive" in path.split("/"):
        return "레거시", "approved"
    if (
        path.startswith("scripts/")
        and path.count("/") >= 1
        and path.split("/")[1] not in ("ops", "common", "browser", "auth", "archive", "site_engine", "verify", "ci")
    ):
        return "도구", "approved"
    if "/connectors/" in f"/{path}/" and path != "ai_orchestrator/connectors":
        return "도구", "approved"
    if path.split("/")[-1] in (
        "gates",
        "persistence",
        "domain",
        "contracts",
        "paths",
        "common",
        "core",
        "audit",
        "schemas",
    ):
        return "공용 기반", "approved"
    return "기능", "approved"


def _purpose(path: str) -> str:
    name = path.split("/")[-1]
    base = _NAME_PURPOSE.get(name, "")
    parent = path.rsplit("/", 1)[0] if "/" in path else ""
    where = f"{parent} 하위" if parent else "저장소 루트"
    return f"{base} ({where})" if base else f"{where} — 현재 트리 기준 등록(세부 목적은 폴더 승인 때 보강)"


def build_entries(files: Iterable[str], root: Path | None = None) -> list[dict]:
    """현재 트리의 코드 폴더 + 사전 승인 목표 폴더로 최초 목록을 만든다."""
    entries: dict[str, dict] = {}
    for path in sorted(code_folders(files, root)):
        kind, status = _kind_and_status(path)
        entries[path] = {
            "path": path,
            "purpose": _purpose(path),
            "kind": kind,
            "status": status,
            "approved_at": APPROVED_AT,
            "approved_by": APPROVED_BY,
        }
    for path, purpose, kind in PRE_APPROVED_TARGETS:
        entries.setdefault(
            path,
            {
                "path": path,
                "purpose": purpose,
                "kind": kind,
                "status": "approved",
                "approved_at": APPROVED_AT,
                "approved_by": APPROVED_BY + " — 목표 폴더(아직 비어 있을 수 있음)",
            },
        )
    return [entries[k] for k in sorted(entries)]


def write_registry(root: Path, entries: list[dict]) -> None:
    p = root / REGISTRY
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "_comment": (
            "폴더 승인 게이트(G16) 정본 — 코드(.py·.ts·.tsx·.js)가 든 모든 폴더. 목록에 없는 폴더에 코드 파일이 생기면 차단된다. "
            "항목 추가는 대표님 승인 후 PR 라벨 folder-approved 가 있어야 CI 를 통과한다(지휘창만 라벨을 붙인다). 삭제는 승인 불필요. "
            "kind: 도구·기능·공용 기반·레거시·시험·앱, status: approved | legacy_to_remove. 규칙: tools/repo_gates/folder_gate.py"
        ),
        "count": len(entries),
        "folders": entries,
    }
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    tmp.replace(p)  # 원자적 쓰기


def approval_verdict(
    added: set[str], *, initial: bool, event: str, labels: set[str], on_push: str = "warn"
) -> tuple[bool, str]:
    """목록에 추가된 폴더가 있을 때의 판정 → (통과 여부, 설명)."""
    if initial:
        return True, "초기 등록(기준에 목록 파일이 없음) — 현재 트리·설계서 사전 승인분"
    if not added:
        return True, "목록에 추가된 폴더 없음"
    names = ", ".join(sorted(added)[:8]) + (f" 외 {len(added) - 8}개" if len(added) > 8 else "")
    if event == "pull_request":
        if LABEL in labels:
            return True, f"추가 {len(added)}건 — 라벨 {LABEL} 확인({names})"
        return False, f"폴더 {len(added)}개 추가({names}) — PR 라벨 {LABEL} 가 없다(대표님 승인 후 지휘창이 붙인다)"
    if event == "push":
        if on_push == "fail":
            return False, f"push 에서 폴더 {len(added)}개 추가({names}) — 승인 증거를 확인할 수 없다"
        return True, f"push 에서 폴더 {len(added)}개 추가({names}) — 병합 전 PR 에서 라벨을 확인했으므로 경고만 한다"
    return (
        False,
        f"{event or '(이벤트 불명)'} 실행에서 폴더 {len(added)}개 추가({names}) — 라벨을 확인할 PR 이 없어 승인 증거가 없다",
    )


def _report_unregistered(bad: list[str], files_by_folder: dict[str, list[str]]) -> None:
    print("=" * 60, file=sys.stderr)
    print("[folder_gate] 승인되지 않은 폴더에 코드 파일이 있어 차단합니다.", file=sys.stderr)
    for d in bad:
        sample = ", ".join(files_by_folder.get(d, [])[:3])
        print(f"  - {d}/  (예: {sample})", file=sys.stderr)
    print("  → 승인된 폴더(configs/folder_registry.json)에 두세요. 새 폴더가 정말 필요하면:", file=sys.stderr)
    print(
        "    지휘창에 '새 폴더 요청'(경로·목적·왜 기존 폴더로 안 되는지) → 대표님 승인 → 목록 추가 → PR 라벨 folder-approved.",
        file=sys.stderr,
    )
    print("  (우회 옵션 없음. 정본: docs/architecture/FOLDER_STRUCTURE.md)", file=sys.stderr)
    print("=" * 60, file=sys.stderr)


def _group(files: Iterable[str]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for f in files:
        if is_code(f):
            out.setdefault(folder_of(f), []).append(f)
    return out


def main(argv: list[str] | None = None) -> int:  # noqa: C901, PLR0912, PLR0915 - CLI 모드 분기
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--staged", action="store_true")
    ap.add_argument("--check-all", action="store_true")
    ap.add_argument("--check-approval", action="store_true")
    ap.add_argument("--init-registry", action="store_true")
    ap.add_argument("--classify", action="store_true")
    ap.add_argument("--base")
    ap.add_argument("--head", default="HEAD")
    ap.add_argument("--event", default=os.environ.get("GITHUB_EVENT_NAME", ""))
    ap.add_argument("--labels", default=os.environ.get("FOLDER_GATE_LABELS", ""))
    ap.add_argument("--on-push", choices=("warn", "fail"), default="warn")
    ap.add_argument("--root", type=Path, default=ROOT)
    a = ap.parse_args(argv)
    root = a.root.resolve()
    registry = load_registry(root)

    if a.classify:
        for p in a.paths:
            d = _norm(p) if not is_code(p) else folder_of(p)
            print(f"{p}\t{d}\t{'등록됨: ' + registry[d]['purpose'] if d in registry else '미등록'}")
        return 0
    if a.init_registry:
        if (root / REGISTRY).is_file():
            print("목록이 이미 있다 — 항목 추가는 대표님 승인 절차(라벨)를 따른다", file=sys.stderr)
            return 2
        entries = build_entries(tracked_files(root), root)
        write_registry(root, entries)
        print(f"목록 생성: {len(entries)}개 폴더")
        return 0
    if not registry:
        print(
            f"[folder_gate] {REGISTRY} 가 없다 — --init-registry 로 최초 생성(현재 트리 + 사전 승인 폴더)",
            file=sys.stderr,
        )
        return 2
    if a.check_all:
        files = [f for f in tracked_files(root) if is_code(f) and (root / f).exists()]
        bad = unregistered(code_folders(files), registry)
        stale = sorted(p for p in registry if p not in code_folders(files) and registry[p].get("status") != "approved")
        if stale:
            print(
                f"[folder_gate] 참고: legacy_to_remove 인데 코드가 이미 없는 폴더 {len(stale)}건 — 목록에서 지울 수 있다",
                file=sys.stderr,
            )
        if bad:
            _report_unregistered(bad, _group(files))
            return 1
        print(f"[folder_gate] PASS — 코드 폴더 {len(code_folders(files))}개 모두 승인 목록 안")
        return 0
    if a.check_approval:
        if not a.base:
            ap.error("--check-approval 은 --base 가 필요하다")
        head = registry_paths_at(root, a.head) or set(registry)
        base = registry_paths_at(root, a.base)
        labels = {x.strip() for x in a.labels.split(",") if x.strip()}
        added = set() if base is None else head - base
        ok, msg = approval_verdict(added, initial=base is None, event=a.event, labels=labels, on_push=a.on_push)
        print(f"[folder_gate] {'PASS' if ok else 'FAIL'} — {msg}", file=sys.stderr if not ok else sys.stdout)
        return 0 if ok else 1
    if a.staged:
        added_files = [(st, p) for st, p in staged_added(root) if is_code(p)]
        if not added_files:
            return 0
        bad = unregistered({folder_of(p) for _, p in added_files}, registry)
        if bad:
            _report_unregistered(bad, _group(p for _, p in added_files))
            return 1
        return 0
    ap.error("--staged / --check-all / --check-approval / --init-registry / --classify 중 하나")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
