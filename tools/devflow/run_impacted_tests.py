"""바뀐 파일의 영향 테스트만 골라 명시 파일로 실행하고, 결과를 기준선(baseline)과 비교한다 (G6).

사용:
    python tools/devflow/run_impacted_tests.py <바뀐파일...> [--timeout 120] [--out 결과.json] [--baseline 이전결과.json]

원칙:
    - 영향 테스트는 `query.py tests-for` (코드 지도) 로 모은다.
    - 목록이 비면 실행을 거부한다(exit 2). "테스트 0개 통과" 로 착각하지 않게 — pytest 전체를 돌리지도 않는다.
    - pytest 는 항상 명시 파일 + `--timeout` + `-p no:cacheprovider` 로 돌린다.
    - 결과(JSON)에 테스트별 상태를 저장한다. --baseline 을 주면 pass→fail 로 바뀐 것만 '새 실패' 로 보고(exit 1).
종료 코드: 0 통과/새 실패 없음 · 1 새 실패(또는 기준선 없을 땐 실패 존재) · 2 실행 거부(영향 테스트 0개·지도 없음)
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.code_map import query as _query  # noqa: E402


def collect_tests(files: list[str], map_path: Path | None = None, root: Path = ROOT) -> list[str]:
    """바뀐 파일 → 영향 테스트 파일(존재하는 것만, 중복 제거, 순서 유지). 지도가 없으면 FileNotFoundError."""
    m = _query.load(map_path)
    seen: dict[str, None] = {}
    for p in _query.tests_for(m, [f.replace("\\", "/") for f in files]):
        if (root / p).is_file():
            seen.setdefault(p, None)
    return list(seen)


def _pyexe() -> list[str]:
    """pytest 를 돌릴 인터프리터 — **지금 이 도구를 실행 중인 인터프리터**를 그대로 쓴다.

    예전에는 `py -3.14` 를 우선했는데, CI(Windows 러너)에서는 py 런처가 가리키는 3.14 가 의존성이 설치된 setup-python
    인터프리터와 달라 pytest 가 없어서 실패했다(test_real_pytest_command_shape, 2026-10-07). 이 도구는 이미 올바른
    인터프리터(py -3.14 로 시작했든 CI 의 venv 든)로 실행 중이므로 sys.executable 이 항상 맞다."""
    return [sys.executable]


def parse_junit(xml_path: Path) -> dict[str, str]:
    """junit xml → {테스트 id: passed|failed|error|skipped}."""
    out: dict[str, str] = {}
    for tc in ET.parse(xml_path).getroot().iter("testcase"):  # noqa: S314 - 이동 전부터 있던 기존 패턴, 이동과 무관(신뢰된 자체 시험 리포트 xml)
        tid = f"{tc.get('classname', '')}::{tc.get('name', '')}"
        status = "passed"
        for child in tc:
            if child.tag in {"failure", "error", "skipped"}:
                status = {"failure": "failed"}.get(child.tag, child.tag)
        out[tid] = status
    return out


def compare(current: dict[str, str], baseline: dict[str, str]) -> dict:
    bad = {"failed", "error"}
    new_failures = sorted(t for t, s in current.items() if s in bad and baseline.get(t) not in bad)
    fixed = sorted(t for t, s in current.items() if s == "passed" and baseline.get(t) in bad)
    missing = sorted(t for t in baseline if t not in current and baseline[t] == "passed")
    return {"new_failures": new_failures, "fixed": fixed, "missing_vs_baseline": missing}


def run_pytest(tests: list[str], timeout: int, root: Path, junit: Path) -> tuple[int, str]:
    cmd = [
        *_pyexe(),
        "-m",
        "pytest",
        *tests,
        "--timeout",
        str(timeout),
        "-p",
        "no:cacheprovider",
        "-q",
        f"--junitxml={junit}",
    ]
    r = subprocess.run(cmd, cwd=str(root), capture_output=True, encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def main(argv: list[str] | None = None, *, runner=run_pytest) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", help="바뀐(또는 이동한) 소스 파일")
    ap.add_argument("--timeout", type=int, default=120, help="테스트 1개당 제한(초)")
    ap.add_argument("--map", type=Path, default=None, help="코드 지도 경로(기본 data/code_map/map.json)")
    ap.add_argument("--out", type=Path, default=None, help="결과 JSON 저장 경로")
    ap.add_argument("--baseline", type=Path, default=None, help="이전 결과 JSON — 새 실패만 비교")
    ap.add_argument("--root", type=Path, default=ROOT)
    ap.add_argument("--dry-run", action="store_true", help="영향 테스트 목록만 출력")
    a = ap.parse_args(argv)
    root = a.root.resolve()
    try:
        tests = collect_tests(a.files, a.map, root)
    except FileNotFoundError:
        print(
            "run_impacted_tests: 코드 지도(map.json) 없음 — build 먼저 (또는 --map / HAEHAN_CODE_MAP). 실행 거부.",
            file=sys.stderr,
        )
        return 2
    if not tests:
        print(
            f"run_impacted_tests: 영향 테스트 0개 ({', '.join(a.files)}) — 실행 거부(0개 통과로 오인 금지). 테스트를 직접 지정해 돌릴 것.",
            file=sys.stderr,
        )
        return 2
    print(f"영향 테스트 {len(tests)}개:")
    for t in tests:
        print("  " + t)
    if a.dry_run:
        return 0
    with tempfile.TemporaryDirectory() as td:
        junit = Path(td) / "junit.xml"
        rc, output = runner(tests, a.timeout, root, junit)
        results = parse_junit(junit) if junit.is_file() else {}
    tail = "\n".join(output.strip().splitlines()[-15:])
    print(tail)
    payload = {
        "created": datetime.now().isoformat(timespec="seconds"),
        "files": a.files,
        "tests": tests,
        "timeout": a.timeout,
        "pytest_returncode": rc,
        "results": results,
    }
    exit_code = 0 if rc == 0 else 1
    if a.baseline:
        base = json.loads(a.baseline.read_text(encoding="utf-8")).get("results", {})
        cmp_ = compare(results, base)
        payload["comparison"] = cmp_
        exit_code = 1 if cmp_["new_failures"] else 0
        print(
            f"기준선 비교: 새 실패 {len(cmp_['new_failures'])} · 고쳐짐 {len(cmp_['fixed'])} · 기준선에만 있는 통과 {len(cmp_['missing_vs_baseline'])}"
        )
        for t in cmp_["new_failures"][:20]:
            print("  새 실패: " + t)
    elif rc != 0 and rc != 1:
        exit_code = 1  # 수집 오류·타임아웃 등
    out = a.out or (root / "data" / "test_baselines" / f"impacted_{datetime.now():%Y%m%d_%H%M%S}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(out)  # 원자적 쓰기
    print(f"결과 저장: {out}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
