"""자동 작성 저장소 — 규칙·초안·실행 기록을 파일로 저장하고 읽는다.

기준서: docs/specs/2026-09-30_blog_auto_writing_automation.md (v2 §3) — DB 스키마 변경 없이 JSON 파일.

    data/blog_automation/rules/<id>.json      규칙 1개
    data/blog_automation/drafts/<id>_<시각>.json  생성된 초안(네이버에 쓰기 전 로컬 사본)
    data/blog_automation/history.json         실행 기록(회차별 1줄, 최근 HISTORY_MAX 개)

- 쓰기는 같은 폴더의 임시 파일에 쓴 뒤 교체해 반쯤 쓰인 파일이 남지 않게 한다.
- 규칙 id 는 파일 이름이 되므로 `rules.is_valid_rule_id` 를 통과한 값만 경로에 쓴다(경로 탈출 차단).
- 한 프로세스 안의 동시 접근은 잠금으로 막는다. 여러 프로세스가 같은 폴더를 동시에 쓰는 경우는 다루지 않는다.
"""

from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path
from typing import Any

from scripts.common.app_paths import runtime_data_dir
from scripts.naver.blog.automation.rules import Rule, is_valid_rule_id, parse_rule, rule_to_dict

ROOT = Path(__file__).resolve().parents[4]
DEFAULT_BASE = runtime_data_dir() / "blog_automation"
HISTORY_MAX = 2000

_LOCK = threading.RLock()


class StoreError(Exception):
    """저장된 규칙 파일이 손상됐거나 잘못된 요청."""


def _write_json_atomic(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except (json.JSONDecodeError, OSError) as exc:
        raise StoreError(f"{path.name} 를 읽을 수 없음: {exc}") from exc


class Store:
    def __init__(self, base: Path | None = None) -> None:
        self.base = Path(base) if base else DEFAULT_BASE

    @property
    def rules_dir(self) -> Path:
        return self.base / "rules"

    @property
    def drafts_dir(self) -> Path:
        return self.base / "drafts"

    @property
    def history_path(self) -> Path:
        return self.base / "history.json"

    # ── 규칙 ─────────────────────────────────────────────────────────────

    def _rule_path(self, rule_id: str) -> Path:
        if not is_valid_rule_id(rule_id):
            raise StoreError("잘못된 규칙 id")
        return self.rules_dir / f"{rule_id}.json"

    def save_rule(self, rule: Rule) -> Path:
        path = self._rule_path(rule.id)
        with _LOCK:
            _write_json_atomic(path, rule_to_dict(rule))
        return path

    def load_rule(self, rule_id: str, *, known_blog_ids: frozenset[str] | None = None) -> Rule | None:
        """없으면 None, 손상됐으면 StoreError."""
        path = self._rule_path(rule_id)
        with _LOCK:
            data = _read_json(path, None)
        if data is None:
            return None
        rule, errors = parse_rule(data, known_blog_ids=known_blog_ids)
        if rule is None:
            raise StoreError(f"규칙 {rule_id} 가 손상됨: {'; '.join(errors)}")
        return rule

    def list_rules(self, *, known_blog_ids: frozenset[str] | None = None) -> tuple[list[Rule], dict[str, list[str]]]:
        """(정상 규칙 목록, {파일 id: 오류}) — 손상된 파일 하나가 목록 전체를 막지 않는다."""
        rules: list[Rule] = []
        broken: dict[str, list[str]] = {}
        if not self.rules_dir.is_dir():
            return rules, broken
        with _LOCK:
            for path in sorted(self.rules_dir.glob("*.json")):
                try:
                    data = _read_json(path, None)
                except StoreError as exc:
                    broken[path.stem] = [str(exc)]
                    continue
                rule, errors = parse_rule(data, known_blog_ids=known_blog_ids)
                if rule is None:
                    broken[path.stem] = errors
                elif rule.id != path.stem:
                    broken[path.stem] = ["파일 이름과 규칙 id 가 다름"]
                else:
                    rules.append(rule)
        return rules, broken

    def delete_rule(self, rule_id: str) -> bool:
        path = self._rule_path(rule_id)
        with _LOCK:
            if not path.exists():
                return False
            path.unlink()
            return True

    # ── 실행 기록 ────────────────────────────────────────────────────────

    def load_history(self) -> list[dict[str, Any]]:
        with _LOCK:
            data = _read_json(self.history_path, [])
        return data if isinstance(data, list) else []

    def upsert_history(self, entry: dict[str, Any]) -> None:
        """(rule_id, slot) 이 같은 기록이 있으면 교체(예: pending → published), 없으면 추가. 오래된 기록은 잘라 낸다."""
        with _LOCK:
            history = self.load_history()
            key = (entry.get("rule_id"), entry.get("slot"))
            for i, old in enumerate(history):
                if (old.get("rule_id"), old.get("slot")) == key:
                    history[i] = entry
                    break
            else:
                history.append(entry)
            _write_json_atomic(self.history_path, history[-HISTORY_MAX:])

    # ── 초안 ─────────────────────────────────────────────────────────────

    def save_draft(self, rule_id: str, payload: dict[str, Any], *, stamp: str) -> Path:
        if not is_valid_rule_id(rule_id):
            raise StoreError("잘못된 규칙 id")
        safe_stamp = re.sub(r"[^0-9]", "", stamp) or "0"
        with _LOCK:
            path = self.drafts_dir / f"{rule_id}_{safe_stamp}.json"
            n = 1
            while path.exists():
                path = self.drafts_dir / f"{rule_id}_{safe_stamp}_{n}.json"
                n += 1
            _write_json_atomic(path, payload)
        return path

    def list_drafts(self, rule_id: str | None = None, *, limit: int = 50) -> list[dict[str, Any]]:
        """최근 초안 요약(최신순) — 본문 전체는 싣지 않는다."""
        if rule_id is not None and not is_valid_rule_id(rule_id):
            raise StoreError("잘못된 규칙 id")
        if not self.drafts_dir.is_dir():
            return []
        out: list[dict[str, Any]] = []
        # 파일 이름 접두어(a_ 가 a_b_ 도 잡음)가 아니라 저장된 rule_id 로 거른다.
        for path in sorted(self.drafts_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            if len(out) >= limit:
                break
            try:
                data = _read_json(path, {})
            except StoreError:
                continue
            if rule_id is not None and data.get("rule_id") != rule_id:
                continue
            post = data.get("post", {})
            out.append(
                {
                    "file": path.name,
                    "rule_id": data.get("rule_id"),
                    "generated_at": data.get("generated_at"),
                    "topic": data.get("topic", {}).get("topic"),
                    "title": post.get("title"),
                    "body_chars": len(post.get("body", "")),
                    "quality_ok": data.get("quality", {}).get("ok"),
                    "publishable": data.get("publishable"),
                }
            )
        return out
