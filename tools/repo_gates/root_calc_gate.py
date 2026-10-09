"""'저장소 루트 직접 계산' 차단 게이트 (G5) — 새로 추가된 줄만 본다.

파일마다 `Path(__file__).resolve().parents[N]` / `.parent.parent` / `os.path.dirname(os.path.dirname(__file__))` 로
저장소 루트를 따로 계산하다가 폴더를 옮길 때마다 깊이가 어긋나 데이터 위치가 바뀐 사고(defect #120)가 났다.
새 코드는 정본을 쓴다:
    ai_orchestrator 안  : from ai_orchestrator.paths import repo_root
    scripts 쪽          : from scripts.common.app_paths import repo_root

사용:
    python tools/repo_gates/root_calc_gate.py --staged                    # pre-commit: staged diff 의 새 줄
    python tools/repo_gates/root_calc_gate.py --check-diff <base> <head>  # CI: base..head 의 새 줄

판정(오탐 방지): 그 줄이 있는 파일의 저장소 상대 경로로 `Path(__file__)` 를 실제로 따라가서 **저장소 루트(이상)에
닿을 때만** 위반이다. 자기 폴더 한 단계(`Path(__file__).parent`, `parents[0]`, dirname 한 번)나 저장소 안의 다른
폴더를 가리키는 식은 허용한다. 기존 줄은 막지 않는다(새 줄만) — 그래서 기준선 파일이 없다.
예외(configs/root_calc_gate.json, 사유 포함): 정본 파일 자체, tests/, apps/, docs/, archive, 그리고
  - `# haehan-root-bootstrap:` 마커 바로 아래 줄(make_shim 이 만드는 직접 실행 부트스트랩)
  - scripts/ 의 독립 실행 스크립트가 정본을 import 하기 전에 sys.path 를 여는 부트스트랩(같은 줄 또는 바로 아래 10줄 안에서 sys.path 에 쓰임)
우회 옵션 없음.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

_BOOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
if str(_BOOT) not in sys.path:
    sys.path.insert(0, str(_BOOT))

from scripts.common.app_paths import repo_root  # noqa: E402

ROOT = repo_root()
CONFIG = "configs/root_calc_gate.json"
BOOTSTRAP_MARK = "haehan-root-bootstrap"

_PATH_TAIL = r"(?:\.(?:resolve|absolute)\(\))*(?:\.parents\[(?P<n>\d+)\]|(?P<chain>(?:\.parent)+))"
_PATH_RE = re.compile(r"(?<![A-Za-z0-9.])_*(?:pathlib\.)?Path\(\s*__file__\s*\)" + _PATH_TAIL)
_PATH_ABS_RE = re.compile(
    r"(?<![A-Za-z0-9.])_*(?:pathlib\.)?Path\(\s*os\.path\.(?:abspath|realpath)\(\s*__file__\s*\)\s*\)" + _PATH_TAIL
)
_DIRNAME_RE = re.compile(r"(?P<dn>(?:(?:os\.path\.)?dirname\(\s*)+)(?:os\.path\.(?:abspath|realpath)\(\s*)?__file__")
_ASSIGN_RE = re.compile(r"^\s*(?P<name>[A-Za-z_]\w*)\s*(?::[^=]+)?=")
_SYSPATH_RE = re.compile(r"sys\.path\.(?:insert|append)\(")


def load_config(root: Path = ROOT) -> dict:
    cfg = json.loads((root / CONFIG).read_text(encoding="utf-8"))
    cfg["_exempt"] = [(e.get("prefix"), re.compile(e["regex"]) if "regex" in e else None) for e in cfg["exempt"]]
    return cfg


def _is_exempt(path: str, cfg: dict) -> bool:
    return any(
        (p is not None and path.startswith(p)) or (rx is not None and rx.search(path)) for p, rx in cfg["_exempt"]
    )


def _strip_comment(line: str) -> str:
    # 문자열 안의 # 은 드물다 — 단순히 첫 # 이후를 버린다(주석 속 예시 코드를 위반으로 세지 않기 위해).
    return line.split("#", 1)[0]


def root_levels(line: str) -> list[int]:
    """그 줄에서 `__file__` 로부터 몇 단계 위로 올라가는지(식마다 하나씩). 한 단계 = 자기 폴더."""
    code = _strip_comment(line)
    out: list[int] = []
    for rx in (_PATH_RE, _PATH_ABS_RE):
        for m in rx.finditer(code):
            out.append(int(m.group("n")) + 1 if m.group("n") is not None else m.group("chain").count(".parent"))
    for m in _DIRNAME_RE.finditer(code):
        out.append(m.group("dn").count("dirname("))
    return out


def reaches_root(levels: int, path: str) -> bool:
    """`path`(저장소 상대) 파일의 `__file__` 에서 levels 단계 위가 저장소 루트(또는 그 위)인가. 한 단계(자기 폴더)는 늘 허용."""
    if levels < 2:
        return False
    dirs = len([p for p in path.split("/") if p]) - 1  # 파일을 담은 폴더 수 = 루트까지 올라가는 단계 − 1
    return levels >= dirs + 1


def _marker_above(lines: list[str], idx: int) -> bool:
    return any(BOOTSTRAP_MARK in ln for ln in lines[max(0, idx - 4) : idx])


def _is_syspath_bootstrap(lines: list[str], idx: int) -> bool:
    cur = lines[idx]
    if _SYSPATH_RE.search(cur):
        return True
    m = _ASSIGN_RE.match(cur)
    if not m:
        return False
    name = re.compile(r"\b" + re.escape(m.group("name")) + r"\b")
    return any(_SYSPATH_RE.search(ln) and name.search(ln) for ln in lines[idx + 1 : idx + 11])


def _guidance(path: str) -> str:
    if path.startswith("ai_orchestrator/"):
        return "from ai_orchestrator.paths import repo_root"
    return "from scripts.common.app_paths import repo_root"


def check_file(path: str, added: list[tuple[int, str]], text: str, cfg: dict) -> list[tuple[int, str, str]]:
    """(줄번호, 줄, 안내) 위반 목록. added=[(줄번호, 줄)] 새 줄만."""
    if not path.endswith(".py") or _is_exempt(path, cfg):
        return []
    lines = text.splitlines()
    bootstrap_ok = path.startswith(tuple(cfg["bootstrap_prefixes"]))
    bad = []
    for no, line in added:
        levels = [lv for lv in root_levels(line) if reaches_root(lv, path)]
        if not levels:
            continue
        idx = no - 1
        if 0 <= idx < len(lines):
            if _marker_above(lines, idx):
                continue
            if bootstrap_ok and _is_syspath_bootstrap(lines, idx):
                continue
        bad.append((no, line.strip(), _guidance(path)))
    return bad


def _depth_free(line: str) -> str:
    """깊이 숫자만 지운 줄 — 파일을 옮기면서 `parents[1]` → `parents[3]` 처럼 단계 수만 바뀐 줄을 같은 줄로 보기 위해."""
    code = re.sub(r"parents\[\d+\]", "parents[N]", line.strip())
    code = re.sub(r"(?:\.parent(?![\w]))+", ".parent*", code)
    return re.sub(r"(?:os\.path\.)?dirname\(", "dirname(", code)


def parse_added(diff: str) -> dict[str, list[tuple[int, str]]]:
    """`git diff -U0` 출력 → {파일: [(새 줄번호, 줄)]}. 같은 파일의 지워진 줄과 깊이 숫자만 다른 줄(= 이동에 따른 단계 보정)은 뺀다."""
    out: dict[str, list[tuple[int, str]]] = {}
    removed: dict[str, set[str]] = {}
    cur: str | None = None
    new_no = 0
    for ln in diff.splitlines():
        if ln.startswith("+++ "):
            cur = ln[6:] if ln.startswith("+++ b/") else None
            continue
        m = re.match(r"@@ -\S+ \+(\d+)(?:,(\d+))? @@", ln)
        if m:
            new_no = int(m.group(1))
            continue
        if cur and ln.startswith("-") and not ln.startswith("---"):
            removed.setdefault(cur, set()).add(_depth_free(ln[1:]))
        elif cur and ln.startswith("+") and not ln.startswith("+++"):
            out.setdefault(cur, []).append((new_no, ln[1:]))
            new_no += 1
    for path, rows in list(out.items()):
        gone = removed.get(path, set())
        kept = [(no, text) for no, text in rows if _depth_free(text) not in gone]
        if kept:
            out[path] = kept
        else:
            del out[path]
    return out


def _git(root: Path, *args: str) -> str:
    r = subprocess.run(["git", *args], cwd=str(root), capture_output=True, encoding="utf-8", errors="replace")
    return r.stdout if r.returncode == 0 else ""


def run(diff: str, read_text, cfg: dict) -> list[tuple[str, int, str, str]]:
    bad = []
    for path, added in parse_added(diff).items():
        if not path.endswith(".py"):
            continue
        text = read_text(path)
        for no, line, guide in check_file(path, added, text, cfg):
            bad.append((path, no, line, guide))
    return bad


def _report(bad: list[tuple[str, int, str, str]]) -> None:
    print("=" * 60, file=sys.stderr)
    print("[root_calc_gate] 저장소 루트를 직접 계산하는 새 줄이 있어 차단합니다.", file=sys.stderr)
    for path, no, line, guide in bad:
        print(f"  - {path}:{no}  {line[:100]}", file=sys.stderr)
        print(f"      → {guide}  (repo_root() 를 쓰세요)", file=sys.stderr)
    print(
        "  자기 폴더 한 단계(Path(__file__).parent)는 허용됩니다. 정본: ai_orchestrator/paths · scripts/common/app_paths.py",
        file=sys.stderr,
    )
    print(
        "  정말 예외면 configs/root_calc_gate.json 의 exempt 에 사유와 함께 추가(리뷰 대상). 우회 옵션 없음.",
        file=sys.stderr,
    )
    print("=" * 60, file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--staged", action="store_true")
    g.add_argument("--check-diff", nargs=2, metavar=("BASE", "HEAD"))
    ap.add_argument("--root", type=Path, default=ROOT)
    a = ap.parse_args(argv)
    root = a.root.resolve()
    cfg = load_config(root)
    if a.staged:
        diff = _git(root, "diff", "--cached", "-U0", "--no-color", "--diff-filter=AMR")
        read_text = lambda p: _git(root, "show", f":{p}")  # noqa: E731 - 인덱스(staged) 내용 기준
    else:
        base, head = a.check_diff
        diff = _git(root, "diff", "-U0", "--no-color", "--diff-filter=AMR", f"{base}...{head}")
        read_text = lambda p: _git(root, "show", f"{head}:{p}")  # noqa: E731
    bad = run(diff, read_text, cfg)
    if bad:
        _report(bad)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
