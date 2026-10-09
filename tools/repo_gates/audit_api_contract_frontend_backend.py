"""R1 — 화면(admin-web) ↔ 서버(FastAPI) API 계약 검사기.

배경(ROOT_FIX_ORDERS.md R1): 라우트를 지워도 그 라우트를 호출하는 화면 코드가
남아 있어도 단위 테스트로 잡히지 않는다(스마트스토어 404, 메일 전송 501 등).
이 스크립트는 admin-web의 fetch 호출 경로와 FastAPI 런타임 등록 라우트를
대조해 끊긴 호출(backend에 없음)과 501 미구현 라우트를 찾는다.

게이트 정책: 기존 끊긴 호출은 configs/r1_api_contract_baseline.json 허용
목록으로 고정하고, 새로 끊기는 호출만 차단한다(기존 부채는 목록화만).
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ADMIN_WEB_SRC = ROOT / "admin-web" / "src"
BACKEND_ROOT = ROOT / "ai_orchestrator"
BASELINE_PATH = ROOT / "configs" / "r1_api_contract_baseline.json"

# admin-web에서 백엔드 base-url 변수로 쓰이는 이름들(실측). REGISTRY는
# site-registry 전용 base라 따로 표시만 하고 같은 규칙으로 비교한다.
BASE_VAR_NAMES = ("API_BASE", "BACKEND", "BASE", "REGISTRY")

# fetch(`${BASE_VAR}/literal/path...`  또는 fetch(`${BASE_VAR}${path}` 형태를 모두 잡는다.
_FETCH_CALL_RE = re.compile(
    r"fetch\(\s*`\$\{(" + "|".join(BASE_VAR_NAMES) + r")\}([^`]*)`",
)
_METHOD_RE = re.compile(r"method:\s*[\"'](GET|POST|PUT|PATCH|DELETE)[\"']")
_DYNAMIC_SEGMENT_RE = re.compile(r"\$\{[^}]+\}")


@dataclass
class FrontendCall:
    file: str
    line: int
    method: str
    raw_path: str
    normalized_path: str
    is_dynamic: bool  # 경로 전체(또는 일부)가 변수라 정적 대조 불가


@dataclass
class BackendRoute:
    method: str
    path: str


@dataclass
class Report:
    frontend_calls: list[FrontendCall] = field(default_factory=list)
    backend_routes: list[BackendRoute] = field(default_factory=list)
    broken_calls: list[FrontendCall] = field(default_factory=list)
    dynamic_calls: list[FrontendCall] = field(default_factory=list)
    unimplemented_501_routes: list[tuple[str, str, str]] = field(default_factory=list)  # method, path, file:line


def _normalize_path(raw: str) -> tuple[str, bool]:
    """프런트 경로 템플릿을 백엔드 라우트 표기({param})로 정규화.

    ${path}/${id} 같은 변수가 세그먼트 전체를 차지하면 그 세그먼트를 {param}으로
    바꾼다. 다만 ${path}처럼 여러 세그먼트를 한 번에 삼킬 수 있는 변수가 있으면
    정적 대조가 불가능하므로 is_dynamic=True로 표시한다.
    """
    if not raw.startswith("/"):
        # fetch(`${BASE}${path}`) 처럼 path가 변수 전체인 경우
        return raw, True

    # 쿼리스트링 제거
    raw = raw.split("?")[0]

    is_dynamic = False
    segments = raw.split("/")
    norm_segments = []
    for seg in segments:
        if _DYNAMIC_SEGMENT_RE.fullmatch(seg):
            norm_segments.append("{param}")
        elif _DYNAMIC_SEGMENT_RE.search(seg):
            # 세그먼트 일부만 변수 — path 전체를 삼키는 ${path} 류일 수 있어 보수적으로 동적 처리
            is_dynamic = True
            norm_segments.append(seg)
        else:
            norm_segments.append(seg)
    return "/".join(norm_segments), is_dynamic


def scan_frontend_calls() -> list[FrontendCall]:
    calls: list[FrontendCall] = []
    if not ADMIN_WEB_SRC.exists():
        return calls
    for path in ADMIN_WEB_SRC.rglob("*.ts*"):
        if "/node_modules/" in path.as_posix() or path.suffix not in (".ts", ".tsx"):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        rel = path.relative_to(ROOT).as_posix()
        lines = text.splitlines()
        for m in _FETCH_CALL_RE.finditer(text):
            raw_path = m.group(2)
            line_no = text.count("\n", 0, m.start()) + 1
            # method는 호출문 뒤 options 객체에서 찾는다(기본 GET).
            # 다음 fetch(...) 호출 시작 전까지로 창을 제한 — 안 그러면 다음 호출의
            # method가 이 호출 것으로 잘못 붙는다(2026-10-07 실측: sessions/status
            # 가 바로 뒤 sessions/refresh의 method:"POST"를 잘못 흡수).
            next_fetch = text.find("fetch(", m.end())
            tail_end = next_fetch if next_fetch != -1 else len(text)
            tail = text[m.end() : min(m.end() + 400, tail_end)]
            method_m = _METHOD_RE.search(tail)
            method = method_m.group(1) if method_m else "GET"
            normalized, is_dynamic = _normalize_path(raw_path)
            calls.append(
                FrontendCall(
                    file=rel,
                    line=line_no,
                    method=method,
                    raw_path=raw_path,
                    normalized_path=normalized,
                    is_dynamic=is_dynamic,
                )
            )
        del lines
    return calls


def scan_backend_routes() -> list[BackendRoute]:
    from tools.audits.backend.audit_backend_runtime_contract import iter_runtime_routes

    routes = []
    for method, path, _name in iter_runtime_routes():
        if method == "WEBSOCKET":
            continue
        for single in method.split(","):
            routes.append(BackendRoute(method=single, path=_normalize_backend_path(path)))
    return routes


_BACKEND_PARAM_RE = re.compile(r"\{[^}]+\}")


def _normalize_backend_path(path: str) -> str:
    return _BACKEND_PARAM_RE.sub("{param}", path)


def scan_501_routes() -> list[tuple[str, str, str]]:
    """라우터 파일에서 `raise HTTPException(status_code=501` 패턴을 찾아
    가장 가까운 앞쪽 @router.<method>(...) 데코레이터의 method/path를 역추적한다.
    """
    results: list[tuple[str, str, str]] = []
    decorator_re = re.compile(
        r"@\w+\.(get|post|put|patch|delete)\(\s*[\"']([^\"']+)[\"']",
    )
    if not BACKEND_ROOT.exists():
        return results
    for path in BACKEND_ROOT.rglob("*.py"):
        rel = path.relative_to(ROOT).as_posix()
        if "/tests/" in f"/{rel}/":
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if "status_code=501" not in text and "status_code = 501" not in text:
            continue
        lines = text.splitlines()
        last_decorator: tuple[str, str] | None = None
        for i, line in enumerate(lines, start=1):
            dm = decorator_re.search(line)
            if dm:
                last_decorator = (dm.group(1).upper(), dm.group(2))
            if "status_code=501" in line or "status_code = 501" in line:
                if last_decorator:
                    method, route_path = last_decorator
                    results.append((method, route_path, f"{rel}:{i}"))
    return sorted(set(results))


def run_audit() -> Report:
    report = Report()
    report.frontend_calls = scan_frontend_calls()
    report.backend_routes = scan_backend_routes()
    backend_keys = {(r.method, r.path) for r in report.backend_routes}

    for call in report.frontend_calls:
        if call.is_dynamic:
            report.dynamic_calls.append(call)
            continue
        if not call.normalized_path.startswith("/api/"):
            continue
        key = (call.method, call.normalized_path)
        if key not in backend_keys:
            report.broken_calls.append(call)

    report.unimplemented_501_routes = scan_501_routes()
    return report


def _call_id(call: FrontendCall) -> str:
    return f"{call.method} {call.normalized_path}"


def load_baseline() -> set[str]:
    if not BASELINE_PATH.exists():
        return set()
    data = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    return set(data.get("allowed_broken_calls", []))


def write_baseline(report: Report) -> None:
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    allowed = sorted({_call_id(c) for c in report.broken_calls})
    BASELINE_PATH.write_text(
        json.dumps(
            {
                "_comment": (
                    "R1 게이트 허용 목록 — 이 시점에 이미 끊겨 있던 호출(기존 부채)."
                    " 새로 끊기는 호출만 audit_r1_api_contract_gate.py가 차단한다."
                    " 수리는 목록 보고 후 별도 배정."
                ),
                "allowed_broken_calls": allowed,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def write_report_md(report: Report) -> Path:
    out_path = ROOT / "data" / "r1_api_contract_audit_latest.md"
    lines = [
        "# R1 API 계약 감사 — 최신 실행 결과",
        "",
        f"- 프런트 fetch 호출 스캔: {len(report.frontend_calls)}건"
        f" (정적 대조 가능 {len(report.frontend_calls) - len(report.dynamic_calls)}건,"
        f" 동적 경로 {len(report.dynamic_calls)}건)",
        f"- 백엔드 런타임 라우트: {len(report.backend_routes)}건",
        f"- 끊긴 호출(backend 없음): {len(report.broken_calls)}건",
        f"- 501 미구현 라우트: {len(report.unimplemented_501_routes)}건",
        "",
        "## 끊긴 호출 (404 후보)",
        "",
    ]
    for c in sorted(report.broken_calls, key=lambda c: (c.file, c.line)):
        lines.append(f"- `{c.method} {c.normalized_path}` — {c.file}:{c.line} (원본: `{c.raw_path}`)")
    if not report.broken_calls:
        lines.append("- (없음)")

    lines += ["", "## 501 미구현 라우트", ""]
    for method, path, loc in report.unimplemented_501_routes:
        lines.append(f"- `{method} {path}` — {loc}")
    if not report.unimplemented_501_routes:
        lines.append("- (없음)")

    lines += ["", "## 동적 경로(자동 대조 불가, 수동 확인 필요)", ""]
    for c in sorted(report.dynamic_calls, key=lambda c: (c.file, c.line))[:50]:
        lines.append(f"- {c.file}:{c.line} — 원본 `{c.raw_path}`")
    if len(report.dynamic_calls) > 50:
        lines.append(f"- ... 외 {len(report.dynamic_calls) - 50}건")
    if not report.dynamic_calls:
        lines.append("- (없음)")

    text = "\n".join(lines) + "\n"
    out_path.write_text(text, encoding="utf-8")

    # 조정 폴더 사본 — 하드코딩 금지(STD-02) 이므로 환경변수로만 받는다.
    # 지휘 작업 중엔 R1_COORDINATION_DIR=C:\work\_coordination 로 실행.
    coordination_dir = os.environ.get("R1_COORDINATION_DIR")
    if coordination_dir:
        coord_path = Path(coordination_dir) / "R1_api_contract.md"
        try:
            coord_path.parent.mkdir(parents=True, exist_ok=True)
            coord_path.write_text(text, encoding="utf-8")
        except OSError:
            pass
    return out_path


def main() -> int:
    write_baseline_mode = "--write-baseline" in sys.argv
    report = run_audit()
    out_path = write_report_md(report)

    if write_baseline_mode:
        write_baseline(report)
        print(f"[baseline] {BASELINE_PATH} 갱신 — 허용 끊긴 호출 {len(report.broken_calls)}건")

    print("=" * 70)
    print("[R1_API_CONTRACT] 화면↔서버 API 계약 감사")
    print("=" * 70)
    print(f"프런트 fetch 호출: {len(report.frontend_calls)} (동적 {len(report.dynamic_calls)})")
    print(f"백엔드 런타임 라우트: {len(report.backend_routes)}")
    print(f"끊긴 호출: {len(report.broken_calls)}")
    print(f"501 미구현 라우트: {len(report.unimplemented_501_routes)}")
    print(f"리포트: {out_path}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
