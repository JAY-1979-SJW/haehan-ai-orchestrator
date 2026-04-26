"""LOCAL-FS-1 — 로컬 파일 조회·검색·요약.

- 프로젝트 루트 기준 allowlist 경로 우선 적용
- secrets/.env/key류 기본 차단
- 민감정보 redaction 후 preview 반환
- binary 파일 skip
- 결과 JSON/MD 저장

절대 금지:
  - .env / secrets/ / *.pem / *.key 원문 출력
  - API key / token / password 원문 출력
  - private key 출력
"""
from __future__ import annotations

import fnmatch
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

# ── 허용 경로 (프로젝트 루트 기준) ─────────────────────────────────────────

ALLOWED_ROOTS: tuple[str, ...] = (
    "docs",
    "scripts",
    "ai_orchestrator",
    "local_agent",
    "agent",
    "samples",
    "runs",
    "data",
    "config",
    "mcp_server",
)

# ── 기본 제외 패턴 ────────────────────────────────────────────────────────

_EXCLUDED_DIRS: tuple[str, ...] = (
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    "dist",
    "build",
    ".next",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "secrets",
)

_EXCLUDED_GLOBS: tuple[str, ...] = (
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "*.sqlite",
    "*.db",
    "*.pyc",
    "*.pyo",
    "*.so",
    "*.dll",
    "*.exe",
    "*.bin",
    "*.zip",
    "*.tar",
    "*.gz",
    "*.7z",
    "*.whl",
    "*.egg",
    "*.mp4",
    "*.mp3",
    "*.avi",
    "*.mov",
    "*.png",
    "*.jpg",
    "*.jpeg",
    "*.gif",
    "*.ico",
    "*.pdf",
    ".env",
    ".env.*",
    "*.secret",
    "*.secrets",
)

ALLOWED_EXTENSIONS: frozenset[str] = frozenset({
    ".py", ".md", ".txt", ".json", ".yaml", ".yml",
    ".csv", ".html", ".css", ".js", ".ts", ".tsx", ".jsx",
    ".toml", ".cfg", ".ini", ".rst",
})

_MAX_FILE_SIZE_BYTES = 2 * 1024 * 1024  # 2 MB

# ── redaction 패턴 ────────────────────────────────────────────────────────

_REDACT_PATTERNS: list[tuple[re.Pattern, str]] = [
    # password=xxx / password: xxx
    (re.compile(r'(?i)(password\s*[=:]\s*)[^\s,\'"]{4,}'), r'\1***'),
    # Authorization: Bearer xxx
    (re.compile(r'(?i)(authorization\s*:\s*bearer\s+)[A-Za-z0-9\-._~+/]+=*'), r'\1***'),
    # token=xxx / access_token=xxx / refresh_token=xxx
    (re.compile(r'(?i)(\b(?:access_token|refresh_token|id_token|token)\s*[=:]\s*)[^\s,\'"]{8,}'), r'\1***'),
    # client_secret=xxx
    (re.compile(r'(?i)(client_secret\s*[=:]\s*)[^\s,\'"]{4,}'), r'\1***'),
    # api_key=xxx / apikey=xxx
    (re.compile(r'(?i)(api[_\-]?key\s*[=:]\s*)[^\s,\'"]{8,}'), r'\1***'),
    # cookie: xxx (header value)
    (re.compile(r'(?i)(cookie\s*:\s*)[^\n]{8,}'), r'\1***'),
    # session=xxx
    (re.compile(r'(?i)(session\s*[=:]\s*)[^\s,\'"]{8,}'), r'\1***'),
    # -----BEGIN ... KEY-----
    (re.compile(r'-----BEGIN [A-Z ]+-----[\s\S]+?-----END [A-Z ]+-----'), '[PRIVATE KEY REDACTED]'),
    # 32자 이상 hex 문자열 (API key류)
    (re.compile(r'\b[0-9a-fA-F]{32,}\b'), lambda m: m.group()[:6] + '...' + m.group()[-4:]),
    # 40자 이상 base64류 (token류)
    (re.compile(r'[A-Za-z0-9+/]{40,}={0,2}'), lambda m: m.group()[:6] + '...' + m.group()[-4:]),
]


def redact_sensitive_text(text: str) -> str:
    for pattern, replacement in _REDACT_PATTERNS:
        if callable(replacement):
            text = pattern.sub(replacement, text)
        else:
            text = pattern.sub(replacement, text)
    return text


# ── 경로 유틸 ─────────────────────────────────────────────────────────────

def normalize_root(path: str | Path) -> Path:
    return Path(path).expanduser().resolve()


def is_excluded_path(path: Path) -> bool:
    """절대/상대 경로 구분 없이 제외 여부를 반환한다."""
    parts = path.parts
    for part in parts:
        if part in _EXCLUDED_DIRS:
            return True
    name = path.name
    for glob in _EXCLUDED_GLOBS:
        if fnmatch.fnmatch(name, glob):
            return True
    # secrets/ 하위 경로 명시 차단 (Windows \ 구분자 정규화)
    path_str = str(path).replace("\\", "/")
    if "/secrets/" in path_str or path_str.endswith("/secrets"):
        return True
    # parts 기반 추가 체크 (절대경로)
    if "secrets" in path.parts:
        return True
    return False


def is_allowed_path(path: Path, root: Path) -> bool:
    """root 기준 allowlist 경로 내에 있는지 확인한다."""
    try:
        rel = path.relative_to(root)
    except ValueError:
        return False
    if not rel.parts:
        return False
    top = rel.parts[0]
    return top in ALLOWED_ROOTS or path == root


def _is_binary(path: Path) -> bool:
    try:
        chunk = path.read_bytes()[:1024]
        # null byte 있으면 binary
        return b"\x00" in chunk
    except OSError:
        return True


def _is_text_file(path: Path) -> bool:
    if path.suffix.lower() not in ALLOWED_EXTENSIONS:
        return False
    if path.stat().st_size > _MAX_FILE_SIZE_BYTES:
        return False
    return not _is_binary(path)


# ── scan_files ───────────────────────────────────────────────────────────

def scan_files(
    root: str | Path,
    *,
    include_globs: list[str] | None = None,
    exclude_globs: list[str] | None = None,
    max_files: int = 5000,
    include_runs: bool = False,
    allow_sensitive_paths: bool = False,
) -> list[Path]:
    root_path = normalize_root(root)
    results: list[Path] = []

    def _walk(directory: Path) -> Iterator[Path]:
        try:
            entries = sorted(directory.iterdir())
        except PermissionError:
            return
        for entry in entries:
            if entry.is_symlink():
                continue
            if entry.is_dir():
                if entry.name in _EXCLUDED_DIRS:
                    continue
                if not allow_sensitive_paths and is_excluded_path(entry):
                    continue
                if not include_runs and entry.name == "runs":
                    continue
                yield from _walk(entry)
            elif entry.is_file():
                yield entry

    extra_excludes = list(exclude_globs or [])

    for path in _walk(root_path):
        if len(results) >= max_files:
            break
        if not allow_sensitive_paths and is_excluded_path(path):
            continue
        if not is_allowed_path(path, root_path):
            continue
        if not _is_text_file(path):
            continue
        if include_globs:
            if not any(fnmatch.fnmatch(path.name, g) for g in include_globs):
                continue
        if extra_excludes:
            if any(fnmatch.fnmatch(path.name, g) for g in extra_excludes):
                continue
        results.append(path)

    return results


# ── search_files ─────────────────────────────────────────────────────────

def search_files(
    root: str | Path,
    query: str,
    *,
    file_types: list[str] | None = None,
    max_results: int = 50,
    include_runs: bool = False,
    allow_sensitive_paths: bool = False,
    include_globs: list[str] | None = None,
) -> list[dict[str, Any]]:
    root_path = normalize_root(root)
    query_lower = query.lower()
    extensions: set[str] | None = None
    if file_types:
        extensions = {(ft if ft.startswith(".") else f".{ft}").lower() for ft in file_types}

    files = scan_files(
        root_path,
        include_globs=include_globs,
        max_files=10000,
        include_runs=include_runs,
        allow_sensitive_paths=allow_sensitive_paths,
    )

    results: list[dict[str, Any]] = []
    for path in files:
        if len(results) >= max_results:
            break
        if extensions and path.suffix.lower() not in extensions:
            continue

        rel = str(path.relative_to(root_path)).replace("\\", "/")
        matched_in_name = query_lower in path.name.lower() or query_lower in rel.lower()
        matched_lines: list[dict] = []

        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        for i, line in enumerate(text.splitlines(), start=1):
            if query_lower in line.lower():
                matched_lines.append({
                    "line": i,
                    "text": redact_sensitive_text(line.rstrip())[:300],
                })
                if len(matched_lines) >= 5:
                    break

        if matched_in_name or matched_lines:
            results.append({
                "path": rel,
                "size_bytes": path.stat().st_size,
                "match_in_name": matched_in_name,
                "matched_lines": matched_lines,
                "match_count": len(matched_lines),
            })

    results.sort(key=lambda r: (-r["match_count"], r["path"]))
    return results[:max_results]


# ── read_file_preview ─────────────────────────────────────────────────────

def read_file_preview(
    path: str | Path,
    *,
    max_chars: int = 8000,
    allow_sensitive_paths: bool = False,
) -> dict[str, Any]:
    p = normalize_root(path)

    if not allow_sensitive_paths and is_excluded_path(p):
        return {"path": str(p), "error": "EXCLUDED_PATH", "preview": None}

    if not p.exists():
        return {"path": str(p), "error": "NOT_FOUND", "preview": None}

    if not _is_text_file(p):
        return {"path": str(p), "error": "BINARY_OR_UNSUPPORTED", "preview": None}

    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return {"path": str(p), "error": str(e)[:100], "preview": None}

    truncated = len(text) > max_chars
    preview = redact_sensitive_text(text[:max_chars])
    return {
        "path": str(p),
        "size_bytes": p.stat().st_size,
        "lines": text.count("\n") + 1,
        "truncated": truncated,
        "preview": preview,
        "error": None,
    }


# ── summarize_file_metadata ───────────────────────────────────────────────

def summarize_file_metadata(path: str | Path) -> dict[str, Any]:
    p = normalize_root(path)
    if not p.exists():
        return {"path": str(p), "exists": False}
    stat = p.stat()
    return {
        "path": str(p),
        "exists": True,
        "size_bytes": stat.st_size,
        "extension": p.suffix.lower(),
        "name": p.name,
        "is_excluded": is_excluded_path(p),
        "is_text": _is_text_file(p),
        "modified_ts": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
    }


# ── build_file_index ──────────────────────────────────────────────────────

def build_file_index(
    root: str | Path,
    *,
    max_files: int = 5000,
    include_runs: bool = False,
) -> dict[str, Any]:
    root_path = normalize_root(root)
    files = scan_files(root_path, max_files=max_files, include_runs=include_runs)
    by_ext: dict[str, int] = {}
    for f in files:
        ext = f.suffix.lower() or "(no ext)"
        by_ext[ext] = by_ext.get(ext, 0) + 1

    return {
        "root": str(root_path),
        "total_files": len(files),
        "by_extension": dict(sorted(by_ext.items(), key=lambda x: -x[1])),
        "files": [
            {
                "path": str(f.relative_to(root_path)).replace("\\", "/"),
                "size_bytes": f.stat().st_size,
                "extension": f.suffix.lower(),
            }
            for f in files
        ],
    }


# ── write_search_result ───────────────────────────────────────────────────

def write_search_result(result: dict[str, Any], out_dir: str | Path) -> dict[str, str]:
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    json_path = out_path / f"local_file_search_{ts}.json"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    md_path = out_path / f"local_file_search_{ts}.md"
    md_path.write_text(_build_md(result), encoding="utf-8")

    return {"json": str(json_path), "md": str(md_path)}


def _build_md(result: dict) -> str:
    lines = [
        "# Local File Search Result",
        "",
        f"query: `{result.get('query', '(index)')}`",
        f"root: `{result.get('root', '')}`",
        f"searched_at: {result.get('searched_at', '')}",
        f"total_matches: {result.get('total_matches', 0)}",
        "",
    ]
    for r in result.get("results", []):
        lines += [
            f"## {r['path']}",
            f"- size: {r['size_bytes']} bytes",
            f"- match_in_name: {r['match_in_name']}",
            f"- matched_lines: {r['match_count']}",
        ]
        for ml in r.get("matched_lines", []):
            lines.append(f"  - L{ml['line']}: `{ml['text'][:120]}`")
        if r.get("preview"):
            lines += [
                "",
                "<details><summary>preview</summary>",
                "",
                "```",
                r["preview"][:2000],
                "```",
                "</details>",
            ]
        lines.append("")

    lines += [
        "## 보안 확인",
        "- .env / secrets 원문 출력: 없음",
        "- API key / token / password 원문: redaction 처리",
        "- private key: redaction 처리",
    ]
    return "\n".join(lines)
