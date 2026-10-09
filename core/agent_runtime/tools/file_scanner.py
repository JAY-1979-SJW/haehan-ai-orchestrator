"""PC 파일 트리 read-only 스캐너 (Stage 1).

사용자가 지정한 root_path 내부만 read-only 로 순회하여 파일 정리를 위한
리포트를 생성한다. 이 모듈은 파일 삭제/이동/이름변경/휴지통 이동을 절대
수행하지 않으며, 결과 item 에는 사용자 실제 absolute_path 를 포함하지
않는다 (서버 전송 가능한 형태).

본 모듈은 read-only 전용이며 파일을 수정/삭제/이동/이름변경하는 표준
라이브러리 함수를 호출하지 않는다. 구체적으로 shutil 의 파일 이동/
삭제 계열, pathlib 의 이름변경/삭제 계열, os 의 동일 기능 계열,
휴지통 이동 라이브러리 모두 사용하지 않는다. (문자열 대조 검사용 목록은
테스트에서 관리한다.)
"""

from __future__ import annotations

import hashlib
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# ─── 분류 기준 ──────────────────────────────────────────────────────────────

PRESERVE_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".pem",
        ".key",
        ".env",
        ".pfx",
        ".p12",
        ".kdbx",
        ".db",
        ".sqlite",
        ".xlsx",
        ".xls",
        ".hwp",
        ".hwpx",
        ".docx",
        ".pdf",
        ".dwg",
        ".dxf",
    }
)

PRESERVE_KEYWORDS: tuple[str, ...] = (
    "계약",
    "견적",
    "내역",
    "기성",
    "청구",
    "세금계산서",
    "사업자",
    "입찰",
    "공고",
    "인증서",
    "서버",
    "접속정보",
    "비밀번호",
    "password",
    "secret",
    "token",
    "api_key",
)

DELETE_CANDIDATE_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".tmp",
        ".bak",
        ".log",
        ".cache",
    }
)

DELETE_CANDIDATE_BASENAMES: frozenset[str] = frozenset(
    {
        "Thumbs.db",
        "desktop.ini",
    }
)

EXCLUDED_DIRS: frozenset[str] = frozenset(
    {
        "AppData",
        "node_modules",
        ".git",
        "__pycache__",
        ".venv",
        "venv",
        "dist",
        "build",
        ".next",
        ".cache",
        ".pytest_cache",
    }
)

# 시스템 드라이브(기본 C:)의 보호 폴더 — 드라이브 문자를 문서에 박지 않고 환경변수에서 읽는다(없으면 C:)
_SYSTEM_DRIVE = os.environ.get("SystemDrive", "C:").lower()
_BLOCKED_PATH_PREFIXES: tuple[str, ...] = tuple(
    f"{_SYSTEM_DRIVE}/{name}"
    for name in ("windows", "program files", "program files (x86)", "programdata", "$recycle.bin", "system volume information")
)

_DRIVE_ROOT_PATTERN = re.compile(r"^[A-Za-z]:[\\/]?$")


# ─── 공개 API ──────────────────────────────────────────────────────────────


def scan_file_tree(
    root_path: str,
    max_depth: int = 5,
    max_files: int = 10000,
    include_hidden: bool = False,
    compute_hash: bool = False,
    max_hash_size_mb: int = 100,
) -> dict[str, Any]:
    """root_path 하위를 read-only 로 스캔 후 JSON 직렬화 가능한 dict 반환.

    - 드라이브 루트 / Windows 시스템 폴더는 기본 차단.
    - 제외 디렉터리 (node_modules, .git, __pycache__ 등) 는 스캔하지 않음.
    - 결과 item 에 absolute_path 미포함 (서버 전송 시 안전).
    - compute_hash=True 이고 파일 크기가 max_hash_size_mb 이하일 때만 hash_sha256 계산.
    """
    # 파라미터 방어
    try:
        max_depth = max(0, int(max_depth))
        max_files = max(1, int(max_files))
        max_hash_size_mb = max(0, int(max_hash_size_mb))
    except (TypeError, ValueError):
        return _error("ROOT_INVALID", "스캔 파라미터 타입 오류")
    include_hidden = bool(include_hidden)
    compute_hash = bool(compute_hash)

    if not isinstance(root_path, str) or not root_path.strip():
        return _error("ROOT_INVALID", "root_path 누락 또는 잘못된 타입")

    root_resolved, root_err = _resolve_scan_root(root_path)
    if root_err is not None:
        return root_err

    warnings: list[str] = []

    if root_resolved.is_file():
        item = _build_item(
            root_resolved,
            root_resolved.parent,
            depth=0,
            compute_hash=compute_hash,
            max_hash_size_mb=max_hash_size_mb,
            warnings=warnings,
            is_hidden=_is_hidden(root_resolved),
        )
        items = [item] if item is not None else []
        _classify_items(items)
        _mark_duplicates(items)
        return _build_report(
            root_display=_root_display(root_resolved),
            items=items,
            scanned_dirs=0,
            excluded_count=0,
            warnings=warnings,
        )

    if not root_resolved.is_dir():
        return _error("ROOT_NOT_DIRECTORY", "root_path 가 파일/디렉터리가 아님")

    items, scanned_dirs, excluded_count = _walk(
        root_resolved,
        max_depth=max_depth,
        max_files=max_files,
        include_hidden=include_hidden,
        compute_hash=compute_hash,
        max_hash_size_mb=max_hash_size_mb,
        warnings=warnings,
    )
    _classify_items(items)
    _mark_duplicates(items)
    return _build_report(
        root_display=_root_display(root_resolved),
        items=items,
        scanned_dirs=scanned_dirs,
        excluded_count=excluded_count,
        warnings=warnings,
    )


# ─── 내부 구현 ──────────────────────────────────────────────────────────────


def _resolve_scan_root(root_path: str) -> tuple[Path, None] | tuple[None, dict[str, Any]]:
    """root_path 차단/존재/해석 검증. (resolved_root, None) 또는 (None, 오류 dict)."""
    block = _check_blocked_root(root_path)
    if block is not None:
        code, msg = block
        return None, _error(code, msg)

    try:
        root = Path(root_path).expanduser()
    except (OSError, ValueError):
        return None, _error("ROOT_INVALID", "root_path 해석 실패")

    try:
        exists = root.exists()
    except OSError:
        return None, _error("ROOT_INVALID", "root_path 상태 조회 실패")
    if not exists:
        return None, _error("ROOT_NOT_FOUND", "root_path 가 존재하지 않음")

    # resolve 이후 시스템 폴더 재검증 (사용자가 상대 경로로 차단 회피 시도 방어)
    try:
        root_resolved = root.resolve()
    except OSError:
        root_resolved = root
    block = _check_blocked_root(str(root_resolved))
    if block is not None:
        code, msg = block
        return None, _error(code, msg)
    return root_resolved, None


def _error(code: str, summary: str) -> dict[str, Any]:
    return {
        "ok": False,
        "error_code": code,
        "summary": summary,
        "root_display": "<redacted>",
        "scanned_files": 0,
        "scanned_dirs": 0,
        "excluded_count": 0,
        "total_size_bytes": 0,
        "preserve_count": 0,
        "delete_candidate_count": 0,
        "review_count": 0,
        "duplicate_candidate_count": 0,
        "items": [],
        "warnings": [],
    }


def _check_blocked_root(raw: str) -> tuple[str, str] | None:
    stripped = raw.strip()
    if _DRIVE_ROOT_PATTERN.match(stripped):
        return ("ROOT_BLOCKED_DRIVE_ROOT", "드라이브 루트 전체 스캔은 차단됨")
    normalized = stripped.replace("\\", "/").rstrip("/").lower()
    for prefix in _BLOCKED_PATH_PREFIXES:
        if normalized == prefix or normalized.startswith(prefix + "/"):
            return ("ROOT_BLOCKED_SYSTEM", f"시스템 폴더 스캔 차단: {prefix}")
    return None


def _list_dir(cur: Path, warnings: list[str]) -> list[Path]:
    """디렉터리 항목 정렬 목록. 읽기 실패 시 경고 기록 후 빈 목록."""
    try:
        return sorted(cur.iterdir(), key=lambda p: p.name)
    except (PermissionError, OSError) as exc:
        warnings.append(f"iterdir_failed:{cur.name}:{type(exc).__name__}")
        return []


def _append_item(items: list[dict[str, Any]], item: dict[str, Any] | None) -> None:
    if item is not None:
        items.append(item)


def _safe_flag(fn: Any) -> bool:
    """is_symlink/is_dir/is_file 호출. OSError 이면 False."""
    try:
        return fn()
    except OSError:
        return False


def _is_skipped_entry(entry: Path, hidden: bool, include_hidden: bool, warnings: list[str]) -> bool:
    """숨김(미포함 시) / 심볼릭 링크 항목은 제외 대상. 링크는 경고 기록."""
    if hidden and not include_hidden:
        return True
    if _safe_flag(entry.is_symlink):
        warnings.append(f"skipped_symlink:{entry.name}")
        return True
    return False


def _walk(  # noqa: PLR0913 - keyword-only 내부 함수, 호출 1곳
    root: Path,
    *,
    max_depth: int,
    max_files: int,
    include_hidden: bool,
    compute_hash: bool,
    max_hash_size_mb: int,
    warnings: list[str],
) -> tuple[list[dict[str, Any]], int, int]:
    items: list[dict[str, Any]] = []
    scanned_dirs = 0
    excluded_count = 0
    truncated = False

    stack: list[tuple[Path, int]] = [(root, 0)]
    while stack:
        cur, depth = stack.pop()
        scanned_dirs += 1

        entries = _list_dir(cur, warnings)

        for entry in entries:
            if len(items) >= max_files:
                truncated = True
                break

            name = entry.name
            hidden = _is_hidden(entry)
            if _is_skipped_entry(entry, hidden, include_hidden, warnings):
                excluded_count += 1
                continue

            if _safe_flag(entry.is_dir):
                if name in EXCLUDED_DIRS or depth + 1 > max_depth:
                    excluded_count += 1
                    continue
                stack.append((entry, depth + 1))
                continue

            if not _safe_flag(entry.is_file):
                continue

            item = _build_item(
                entry,
                root,
                depth=depth + 1,
                compute_hash=compute_hash,
                max_hash_size_mb=max_hash_size_mb,
                warnings=warnings,
                is_hidden=hidden,
            )
            _append_item(items, item)

        if truncated:
            break

    if truncated:
        warnings.append(f"max_files_reached:{max_files}")

    return items, scanned_dirs, excluded_count


def _build_item(  # noqa: PLR0913 - keyword-only 내부 함수, 호출 2곳
    path: Path,
    root: Path,
    *,
    depth: int,
    compute_hash: bool,
    max_hash_size_mb: int,
    warnings: list[str],
    is_hidden: bool,
) -> dict[str, Any] | None:
    try:
        st = path.stat()
    except OSError as exc:
        warnings.append(f"stat_failed:{path.name}:{type(exc).__name__}")
        return None

    try:
        rel = path.relative_to(root)
    except ValueError:
        rel = Path(path.name)

    name = path.name
    ext = path.suffix.lower()
    size = int(getattr(st, "st_size", 0))

    item: dict[str, Any] = {
        "relative_path": str(rel).replace("\\", "/"),
        "file_name": name,
        "extension": ext,
        "size_bytes": size,
        "modified_at": _iso_utc(getattr(st, "st_mtime", 0)),
        "depth": int(depth),
        "is_hidden": bool(is_hidden),
        "file_type": _file_type(ext),
        "category": "review",
        "reason": "general_file",
        "duplicate_candidate": False,
        "duplicate_strength": "none",
    }

    birth = getattr(st, "st_birthtime", None)
    if birth:
        item["created_at"] = _iso_utc(birth)
    else:
        ctime = getattr(st, "st_ctime", None)
        if ctime:
            item["created_at"] = _iso_utc(ctime)

    if compute_hash:
        limit_bytes = max_hash_size_mb * 1024 * 1024
        if size <= limit_bytes:
            digest = _sha256_file(path)
            if digest is None:
                item["hash_skipped_reason"] = "read_error"
            else:
                item["hash_sha256"] = digest
        else:
            item["hash_skipped_reason"] = f"size_over_{max_hash_size_mb}MB"

    return item


def _sha256_file(path: Path, chunk_size: int = 65536) -> str | None:
    h = hashlib.sha256()
    try:
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(chunk_size), b""):
                h.update(chunk)
    except OSError:
        return None
    return h.hexdigest()


def _classify_items(items: list[dict[str, Any]]) -> None:
    for item in items:
        cat, reason, preserve_reason = _classify(item)
        item["category"] = cat
        item["reason"] = reason
        if preserve_reason:
            item["preserve_reason"] = preserve_reason


def _classify(item: dict[str, Any]) -> tuple[str, str, str]:
    name = item.get("file_name", "")
    ext = (item.get("extension") or "").lower()
    size = int(item.get("size_bytes", 0))
    lowered = name.lower()

    # 시스템 아티팩트 파일명은 확장자 preserve 규칙보다 우선 (예: Thumbs.db).
    # 사용자의 실제 데이터가 아닌 OS 캐시/메타데이터.
    if name in DELETE_CANDIDATE_BASENAMES:
        return "candidate_delete", f"system_artifact:{name}", ""

    # Office lock 파일 (~$prefix) 은 preserve 확장자 규칙보다 우선.
    # "~$contract.docx" 류는 실제 계약서가 아니라 열려있는 문서의 임시 잠금 파일.
    if name.startswith("~$"):
        return "candidate_delete", "office_lock_file", ""

    # preserve 최우선: 확장자
    if ext in PRESERVE_EXTENSIONS:
        return "preserve", f"preserve_extension:{ext}", f"extension={ext}"

    # preserve: 파일명 키워드 (대소문자 무시)
    for kw in PRESERVE_KEYWORDS:
        if kw.lower() in lowered:
            return "preserve", f"preserve_keyword:{kw}", f"keyword={kw}"

    # 삭제 후보
    if ext in DELETE_CANDIDATE_EXTENSIONS:
        return "candidate_delete", f"temporary_ext:{ext}", ""
    if size == 0:
        return "candidate_delete", "empty_file", ""

    return "review", "general_file", ""


def _mark_duplicates(items: list[dict[str, Any]]) -> None:
    by_name_size: dict[tuple[str, int], list[int]] = {}
    by_ext_size: dict[tuple[str, int], list[int]] = {}

    for i, it in enumerate(items):
        key_strong = (it["file_name"], int(it["size_bytes"]))
        by_name_size.setdefault(key_strong, []).append(i)
        key_weak = ((it.get("extension") or ""), int(it["size_bytes"]))
        by_ext_size.setdefault(key_weak, []).append(i)

    for (name, size), idxs in by_name_size.items():
        if len(idxs) > 1:
            group_key = f"strong:{name}:{size}"
            for i in idxs:
                items[i]["duplicate_candidate"] = True
                items[i]["duplicate_strength"] = "strong"
                items[i]["duplicate_group_key"] = group_key

    for (ext, size), idxs in by_ext_size.items():
        if len(idxs) > 1 and size > 0:
            group_key = f"weak:{ext}:{size}"
            for i in idxs:
                if items[i].get("duplicate_strength") == "strong":
                    continue
                items[i]["duplicate_candidate"] = True
                items[i]["duplicate_strength"] = "weak"
                items[i]["duplicate_group_key"] = group_key


def _build_report(
    *,
    root_display: str,
    items: list[dict[str, Any]],
    scanned_dirs: int,
    excluded_count: int,
    warnings: list[str],
) -> dict[str, Any]:
    preserve_count = sum(1 for i in items if i["category"] == "preserve")
    delete_count = sum(1 for i in items if i["category"] == "candidate_delete")
    review_count = sum(1 for i in items if i["category"] == "review")
    dup_count = sum(1 for i in items if i.get("duplicate_candidate"))
    total_size = sum(int(i.get("size_bytes", 0)) for i in items)

    return {
        "ok": True,
        "root_display": root_display,
        "scanned_files": len(items),
        "scanned_dirs": int(scanned_dirs),
        "excluded_count": int(excluded_count),
        "total_size_bytes": int(total_size),
        "preserve_count": preserve_count,
        "delete_candidate_count": delete_count,
        "review_count": review_count,
        "duplicate_candidate_count": dup_count,
        "items": items,
        "warnings": warnings,
    }


def _is_hidden(path: Path) -> bool:
    name = path.name
    if name.startswith("."):
        return True
    if os.name == "nt":
        try:
            import stat as _stat

            attrs = path.stat().st_file_attributes  # type: ignore[attr-defined]
            hidden_flag = getattr(_stat, "FILE_ATTRIBUTE_HIDDEN", 0x02)
            return bool(attrs & hidden_flag)
        except (AttributeError, OSError):
            return False
    return False


_FILE_TYPE_TABLE: tuple[tuple[frozenset[str], str], ...] = (
    (frozenset({".pem", ".key", ".env", ".pfx", ".p12", ".kdbx"}), "secret"),
    (frozenset({".docx", ".doc", ".hwp", ".hwpx", ".pdf", ".rtf", ".txt", ".md"}), "document"),
    (frozenset({".xlsx", ".xls", ".csv"}), "spreadsheet"),
    (frozenset({".ppt", ".pptx"}), "presentation"),
    (frozenset({".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tif", ".tiff", ".webp"}), "image"),
    (frozenset({".dwg", ".dxf"}), "cad"),
    (frozenset({".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz"}), "archive"),
    (frozenset({".py", ".js", ".ts", ".tsx", ".java", ".c", ".cpp", ".go", ".rs", ".rb"}), "code"),
    (frozenset({".db", ".sqlite", ".json", ".xml", ".yaml", ".yml"}), "data"),
)


def _file_type(ext: str) -> str:
    for exts, kind in _FILE_TYPE_TABLE:
        if ext in exts:
            return kind
    if ext in DELETE_CANDIDATE_EXTENSIONS:
        return "temporary"
    return "other"


def _iso_utc(ts: float) -> str:
    try:
        return datetime.fromtimestamp(float(ts), tz=UTC).isoformat()
    except (OSError, ValueError, OverflowError):
        return ""


def _root_display(root: Path) -> str:
    try:
        name = root.name
        return name if name else "<selected_root>"
    except Exception:  # noqa: BLE001 - 선택된 루트 디렉터리 표시명 조회 실패 시 플레이스홀더 문자열 반환 - 파일 스캐너 UI 표시용, 읽기전용 파일 목록 스캔 로직에 영향 없음
        return "<selected_root>"


__all__ = [
    "DELETE_CANDIDATE_BASENAMES",
    "DELETE_CANDIDATE_EXTENSIONS",
    "EXCLUDED_DIRS",
    "PRESERVE_EXTENSIONS",
    "PRESERVE_KEYWORDS",
    "scan_file_tree",
]
