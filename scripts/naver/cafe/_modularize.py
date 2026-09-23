"""One-shot modularization script for scripts/naver/cafe/.

Run once:
    python scripts/naver/cafe/_modularize.py

Actions:
1. Create subdirectory structure
2. Copy each file with adjusted parents[] depth
3. Create __init__.py re-exports in each subdir
4. Replace original files with re-export stubs
"""

from __future__ import annotations

import textwrap
from pathlib import Path

CAFE_DIR = Path(__file__).resolve().parent

# Mapping: filename → target subdir
FILE_MAP: dict[str, str] = {
    # write/
    "writer.py": "write",
    "join_request.py": "write",
    # collection/
    "explorer.py": "collection",
    "collector.py": "collection",
    "cafe_explorer.py": "collection",
    "cafe_scraper.py": "collection",
    "cafe_attachments.py": "collection",
    "cafe_explore.py": "collection",
    "cafe_list.py": "collection",
    "list_collector.py": "collection",
    "member_collect.py": "collection",
    "topic_search.py": "collection",
    # analysis/
    "analyzer.py": "analysis",
    "classifier.py": "analysis",
    "organizer.py": "analysis",
    "pipeline.py": "analysis",
    # background/
    "list_background_runner.py": "background",
    "main_page.py": "background",
}

# Public symbols per file (used to build subdir __init__.py re-exports)
# We'll do a wildcard re-export via __all__ = [] approach; simpler is just
# "from .filename import *"  which works for modules without __all__ too.

SUBDIRS = ["write", "collection", "analysis", "background"]


def adjust_parents(src_text: str, filename: str) -> str:
    """Increment parents[N] by 1 in copied file.

    cafe/file.py uses parents[3] → repo root
    cafe/subdir/file.py needs parents[4] → repo root
    """
    # Replace parents[3] → parents[4], parents[4] → parents[5]
    # Do from high to low to avoid double-increment
    for n in (5, 4, 3):
        src_text = src_text.replace(f"parents[{n}]", f"__PARENTS_{n + 1}__")
    for n in (5, 4, 3):
        src_text = src_text.replace(f"__PARENTS_{n + 1}__", f"parents[{n + 1}]")
    return src_text


def make_stub(module_name: str, subdir: str) -> str:
    """Create a re-export stub for original file location."""
    rel_import = f"from .{subdir}.{module_name} import *"  # noqa: F841
    try_import = f"from .{subdir}.{module_name} import *  # noqa: F401,F403"  # noqa: F841
    return textwrap.dedent(f"""\
        \"\"\"Re-export stub — real implementation moved to {subdir}/{module_name}.py.

        This file is kept for backward compatibility.
        \"\"\"
        from __future__ import annotations
        from .{subdir}.{module_name} import *  # noqa: F401,F403

        # Allow 'from scripts.naver.cafe.{module_name} import SomeClass' to still work.
        try:
            from .{subdir}.{module_name} import *  # noqa: F401,F403
        except Exception:
            pass
        """)


def build_subdir_init(subdir: str, files: list[str]) -> str:
    """Build __init__.py for a subdirectory that re-exports all modules."""
    lines = [
        f'"""scripts.naver.cafe.{subdir} — auto-generated re-export __init__."""',
        "from __future__ import annotations",
        "",
    ]
    for f in sorted(files):
        module = f.removesuffix(".py")
        lines.append(f"from .{module} import *  # noqa: F401,F403")
    lines.append("")
    return "\n".join(lines)


def run() -> None:
    # Step 1: Create subdirectories
    for sd in SUBDIRS:
        (CAFE_DIR / sd).mkdir(exist_ok=True)
        print(f"[mkdir] {sd}/")

    # Step 2: Copy files with adjusted paths
    subdir_files: dict[str, list[str]] = {sd: [] for sd in SUBDIRS}

    for filename, subdir in FILE_MAP.items():
        src = CAFE_DIR / filename
        dst = CAFE_DIR / subdir / filename
        if not src.exists():
            print(f"[SKIP] {filename} — not found")
            continue
        text = src.read_text(encoding="utf-8")
        text = adjust_parents(text, filename)
        dst.write_text(text, encoding="utf-8")
        subdir_files[subdir].append(filename)
        print(f"[copy] {filename} → {subdir}/{filename}")

    # Step 3: Create __init__.py in each subdir
    for sd in SUBDIRS:
        init_path = CAFE_DIR / sd / "__init__.py"
        content = build_subdir_init(sd, subdir_files[sd])
        init_path.write_text(content, encoding="utf-8")
        print(f"[init] {sd}/__init__.py")

    # Step 4: Replace original files with re-export stubs
    for filename, subdir in FILE_MAP.items():
        src = CAFE_DIR / filename
        if not src.exists():
            continue
        module = filename.removesuffix(".py")
        stub = make_stub(module, subdir)
        src.write_text(stub, encoding="utf-8")
        print(f"[stub] {filename}")

    print("\n[done] Modularization complete.")
    print("Verify with:")
    print(
        "  python -c \"from scripts.naver.cafe.collection.cafe_explorer import *; from scripts.naver.cafe.analysis.analyzer import *; from scripts.naver.cafe.cafe_explorer import *; print('OK')\""
    )


if __name__ == "__main__":
    run()
