"""블로그 모듈 분리 가능성 점검 — 기준서 0절 "분리 경계"가 실제로 지켜지는지 검사.

## 왜 필요한가
`docs/specs/naver_blog_content_standard.md` 0절은 "언제든 들어낼 수 있는
경계를 유지한다"고 정해두었지만, **손으로 관리하는 목록은 반드시 낡는다**.
실제로 2026-08-24 점검 시 목록에 3개 파일이 빠져 있었고(blog_publish_manual,
writer, post_cache), 반대로 목록에 있던 `blog_ai_batch_20.py`는 GPT 차단으로
못 쓰는 상태였다.

그래서 목록을 믿지 말고 **import를 직접 스캔**한다.

## 검사 항목
1. 타 업무 도메인 import (EUM·g2b·스마트스토어·하이웍스 등) — **0건이어야 함**
2. 앱 본체(`ai_orchestrator`) import — 있으면 어떤 모듈인지 보고
3. 분리 대상 파일 존재 여부

사용:
    python -m scripts.naver.blog.cli.check_blog_separability          # 사람이 읽는 리포트
    python -m scripts.naver.blog.cli.check_blog_separability --strict # 위반 시 exit 1 (CI용)
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[4]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# 분리 대상 — 2026-08-24 모듈 통합 이후로는 **폴더 하나**다.
#
# 이전엔 파일 7개를 손으로 나열했는데, 그 목록이 6일 만에 낡아서 이 도구를
# 만들게 됐다(위 docstring 참조). 통합 후에는 나열할 게 없다 —
# `scripts/naver/blog/` 전체가 블로그 모듈이고, 새 파일을 이 폴더 어디에
# 만들든 자동으로 검사 대상이 된다. **목록이 낡을 수가 없는 구조**이고,
# 이것이 흩어진 4곳을 한 폴더로 모은 실질적 이유다.
BLOG_PATHS = [
    "scripts/naver/blog",
]

# 절대 참조하면 안 되는 타 업무 도메인 (기준서 "격리 규칙")
FORBIDDEN_DOMAINS = [
    "scripts.eum",
    "scripts.g2b",
    "scripts.naver.smartstore",
    "scripts.hiworks",
    "scripts.kakaowork",
    "ai_orchestrator.connectors.smartstore",
]

# 앱 본체 의존 — 금지는 아니지만 분리 시 손봐야 하므로 목록화한다.
APP_PREFIX = "ai_orchestrator"

_IMPORT_RE = re.compile(r"^\s*(?:from|import)\s+([A-Za-z_][\w.]*)", re.M)


def _iter_py_files() -> list[Path]:
    files: list[Path] = []
    for rel in BLOG_PATHS:
        p = _ROOT / rel
        if p.is_dir():
            files.extend(f for f in p.rglob("*.py") if "__pycache__" not in str(f))
        elif p.is_file():
            files.append(p)
    return files


def scan() -> dict:
    forbidden: list[tuple[str, str, int]] = []
    app_deps: list[tuple[str, str, int]] = []
    missing = [rel for rel in BLOG_PATHS if not (_ROOT / rel).exists()]

    for f in _iter_py_files():
        rel = f.relative_to(_ROOT).as_posix()
        text = f.read_text(encoding="utf-8", errors="ignore")
        for m in _IMPORT_RE.finditer(text):
            mod = m.group(1)
            line = text[: m.start()].count("\n") + 1
            if any(mod.startswith(d) for d in FORBIDDEN_DOMAINS):
                forbidden.append((rel, mod, line))
            elif mod.split(".")[0] == APP_PREFIX:
                app_deps.append((rel, mod, line))

    return {
        "files_scanned": len(_iter_py_files()),
        "forbidden": forbidden,
        "app_deps": app_deps,
        "missing": missing,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true", help="위반 시 exit 1")
    args = ap.parse_args()

    r = scan()
    print(f"블로그 모듈 분리 가능성 점검 — 파일 {r['files_scanned']}개 스캔\n")

    if r["missing"]:
        print("⚠️ 분리 목록에 있으나 실제로 없는 경로:")
        for rel in r["missing"]:
            print(f"   · {rel}")
        print()

    if r["forbidden"]:
        print(f"❌ 타 업무 도메인 import {len(r['forbidden'])}건 — 격리 규칙 위반")
        for rel, mod, line in r["forbidden"]:
            print(f"   · {rel}:{line}  →  {mod}")
    else:
        print("✅ 타 업무 도메인 import 0건 (EUM·g2b·스마트스토어·하이웍스 등)")
    print()

    if r["app_deps"]:
        print(f"ℹ️ 앱 본체({APP_PREFIX}) 의존 {len(r['app_deps'])}건 — 분리 시 처리 필요")
        for rel, mod, line in r["app_deps"]:
            print(f"   · {rel}:{line}  →  {mod}")
    else:
        print(f"✅ 앱 본체({APP_PREFIX}) 의존 0건 — 그대로 들어내도 됨")

    if args.strict and (r["forbidden"] or r["missing"]):
        sys.exit(1)


if __name__ == "__main__":
    main()
