"""검증된 환경의 버전 집합으로 `constraints.txt` 를 만든다 (pip 공식 *Constraints files* 방식).

기준서: docs/specs/2026-10-04_portability_standard.md

`requirements.txt` 는 직접 의존성을 범위(`>=`)로 적는다 → PC·시점마다 설치되는 버전이 달라진다. 이 도구는 **지금 파이썬 환경에 설치된**
버전 중 requirements.txt 에서 닿는 패키지(간접 의존성 포함)만 골라 `이름==버전` 으로 적는다. 시험이 통과하는 환경에서 돌려 만든다:

    <시험용 파이썬> tools/devflow/make_constraints.py            # constraints.txt 를 새로 쓴다
    <시험용 파이썬> tools/devflow/make_constraints.py --check    # 파일이 현재 환경과 같은지만 확인(다르면 종료코드 1)

설치: `pip install -r requirements.txt -c constraints.txt`.  pytest·ruff 같은 개발 도구는 requirements.txt 에서 닿지 않으므로 들어가지 않는다.
읽기 전용 점검(`--check`)을 빼면 파일 하나만 쓴다. 패키지를 설치·삭제하지 않는다.
"""

from __future__ import annotations

import platform
import sys
from collections.abc import Callable
from datetime import date
from importlib import metadata
from pathlib import Path

from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
REQUIREMENTS = ROOT / "requirements.txt"
OUTPUT = ROOT / "constraints.txt"


def read_requirements(path: Path) -> list[Requirement]:
    """requirements.txt 의 직접 의존성. 주석·빈 줄·옵션(`-r`, `--index-url` …)은 건너뛴다."""
    found = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split(" #", 1)[0].strip()
        if not line or line.startswith(("#", "-")):
            continue
        try:
            found.append(Requirement(line))
        except InvalidRequirement as exc:
            raise ValueError(f"requirements.txt 를 해석할 수 없습니다: {raw!r} ({exc})") from exc
    return found


def closure(
    roots: list[Requirement],
    distribution: Callable[[str], metadata.Distribution] = metadata.distribution,
) -> tuple[dict[str, str], list[str]]:
    """roots 에서 닿는 패키지의 {정규화 이름: 설치된 버전} 과 설치돼 있지 않아 못 찾은 이름 목록."""
    versions: dict[str, str] = {}
    missing: list[str] = []
    done: dict[str, set[str]] = {}
    queue: list[tuple[str, frozenset[str]]] = [(r.name, frozenset(r.extras)) for r in roots]
    while queue:
        name, extras = queue.pop()
        canon = canonicalize_name(name)
        if extras <= done.get(canon, set()) and canon in versions:
            continue
        try:
            dist = distribution(name)
        except metadata.PackageNotFoundError:
            if canon not in missing:
                missing.append(canon)
            continue
        versions[canon] = dist.version
        done.setdefault(canon, set()).update(extras)
        for text in dist.requires or []:
            req = Requirement(text)
            if req.marker is not None and not any(req.marker.evaluate({"extra": e}) for e in (extras | {""})):
                continue
            queue.append((req.name, frozenset(req.extras)))
    return versions, sorted(missing)


def render(versions: dict[str, str], today: date | None = None) -> str:
    header = [
        "# 검증된 환경의 버전 집합 — tools/devflow/make_constraints.py 로 생성(직접 고치지 않는다). 설치: pip install -r requirements.txt -c constraints.txt",
        f"# 생성: {today or date.today()} / Python {platform.python_version()} / {sys.platform}",
        "# requirements.txt 에서 닿는 패키지(간접 의존성 포함)만 담는다. 개발 도구(pytest·ruff 등)는 들어가지 않는다.",
    ]
    return "\n".join([*header, *(f"{name}=={versions[name]}" for name in sorted(versions)), ""])


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    versions, missing = closure(read_requirements(REQUIREMENTS))
    if missing:
        print("설치돼 있지 않아 고정하지 못한 패키지: " + ", ".join(missing), file=sys.stderr)
        print(
            "→ 먼저 이 환경에 pip install -r requirements.txt 를 하세요(플랫폼 전용 패키지는 제외될 수 있음).",
            file=sys.stderr,
        )
        return 2
    if "--check" in args:
        current = (
            {
                ln.split("==")[0]: ln.split("==")[1]
                for ln in OUTPUT.read_text(encoding="utf-8").splitlines()
                if "==" in ln
            }
            if OUTPUT.is_file()
            else {}
        )
        drift = sorted(f"{n} {current.get(n, '없음')}→{v}" for n, v in versions.items() if current.get(n) != v)
        print(
            "constraints.txt 가 현재 환경과 같습니다"
            if not drift
            else "다름 " + str(len(drift)) + "건: " + ", ".join(drift[:8])
        )
        return 1 if drift else 0
    OUTPUT.write_text(render(versions), encoding="utf-8", newline="\n")
    print(f"constraints.txt 를 썼습니다({len(versions)}개 패키지)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
