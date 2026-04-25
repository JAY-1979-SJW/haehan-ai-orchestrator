"""CLI: Naver / YouTube API secret 안전 등록 도구 (F-4S-4K).

원칙:
- secret value 는 stdin 으로만 받는다. argv / 환경변수 / 파일 경로로 받지 않는다.
- stdout / stderr 에 secret 원문 출력 금지. .env 전체 내용 출력 금지.
- 변경된 key 이름만 표시. 길이는 --verify 의 redacted 출력에서만.
- 지원 키: NAVER_CLIENT_ID / NAVER_CLIENT_SECRET / YOUTUBE_DATA_API_KEY
- write 동작: .env upsert 만. OAuth / 브라우저 자동화 / 외부 push 없음.

사용 예:
    python scripts/set_api_env_secret.py --set NAVER_CLIENT_ID --value-stdin --verify
    python scripts/set_api_env_secret.py --set NAVER_CLIENT_SECRET --value-stdin --verify
    python scripts/set_api_env_secret.py --set YOUTUBE_DATA_API_KEY --value-stdin --verify --run-smoke
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Mapping, Optional, Sequence, TextIO, Tuple

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from ai_orchestrator.connectors import naver_search_api_config as naver_cfg_mod  # noqa: E402
from ai_orchestrator.connectors import youtube_data_api_config as yt_cfg_mod  # noqa: E402

ALLOWED_KEYS: Tuple[str, ...] = (
    "NAVER_CLIENT_ID",
    "NAVER_CLIENT_SECRET",
    "YOUTUBE_DATA_API_KEY",
)
DEFAULT_ENV_PATH = ".env"

_PASSTHROUGH_ENV_KEYS: Tuple[str, ...] = (
    "NAVER_SEARCH_API_BASE_URL",
    "NAVER_SEARCH_API_TIMEOUT_SECONDS",
    "YOUTUBE_DATA_API_BASE_URL",
    "YOUTUBE_DATA_API_TIMEOUT_SECONDS",
)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="set_api_env_secret.py",
        description="Naver / YouTube API secret 안전 등록 (stdin 전용, .env upsert).",
    )
    p.add_argument(
        "--set",
        dest="set_key",
        choices=list(ALLOWED_KEYS),
        default=None,
        help="등록할 key (값은 --value-stdin 으로만 받는다)",
    )
    p.add_argument(
        "--value-stdin",
        action="store_true",
        help="값을 stdin 으로 입력. argv 에 절대 값을 넣지 않는다.",
    )
    p.add_argument(
        "--env-path",
        default=DEFAULT_ENV_PATH,
        help=f"대상 .env 경로 (기본: {DEFAULT_ENV_PATH})",
    )
    p.add_argument(
        "--verify",
        action="store_true",
        help="redacted config 출력 (Naver / YouTube)",
    )
    p.add_argument(
        "--run-smoke",
        action="store_true",
        help="키가 있는 플랫폼만 read-only smoke 호출",
    )
    return p


def _parse_env_file(path: Path) -> Dict[str, str]:
    """Best-effort .env 파서 — 따옴표 escape 미지원, 충분히 단순한 형식만."""
    if not path.exists():
        return {}
    parsed: Dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        v = value.strip()
        if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
            v = v[1:-1]
        parsed[key] = v
    return parsed


def _upsert_env_line(lines: List[str], key: str, value: str) -> Tuple[List[str], bool]:
    """기존 KEY=... 라인이 있으면 교체, 없으면 추가. (new_lines, replaced) 반환."""
    target_prefix = f"{key}="
    export_prefix = f"export {key}="
    new_lines: List[str] = []
    replaced = False
    for raw in lines:
        stripped = raw.lstrip()
        if not replaced and (
            stripped.startswith(target_prefix) or stripped.startswith(export_prefix)
        ):
            new_lines.append(f"{key}={value}")
            replaced = True
            continue
        new_lines.append(raw)
    if not replaced:
        new_lines.append(f"{key}={value}")
    return new_lines, replaced


def _atomic_write_env(path: Path, lines: Iterable[str]) -> None:
    text = "\n".join(lines)
    if not text.endswith("\n"):
        text += "\n"
    parent = path.parent if str(path.parent) else Path(".")
    parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".env.tmp.", dir=str(parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except Exception:
        try:
            if os.path.exists(tmp):
                os.unlink(tmp)
        except OSError:
            pass
        raise
    try:
        os.chmod(path, 0o600)
    except OSError:
        # POSIX 권한 비지원 OS (Windows) — 무시.
        pass


def _read_value_from_stdin(stdin: TextIO) -> str:
    raw = stdin.read()
    return raw.strip("\r\n").rstrip("\n").strip()


def _print_redacted(stdout: TextIO, env: Mapping[str, str]) -> None:
    naver_cfg = naver_cfg_mod.load_naver_search_api_config(env=dict(env))
    yt_cfg = yt_cfg_mod.load_youtube_data_api_config(env=dict(env))
    print("[set_api_env_secret] verify (redacted):", file=stdout)
    naver_red = naver_cfg.redacted()
    print(f"  naver.live_enabled={naver_cfg.live_enabled}", file=stdout)
    print(
        "  naver.client_id_present={present} length={length}".format(
            present=naver_red["client_id_present"],
            length=naver_red["client_id_length"],
        ),
        file=stdout,
    )
    print(
        "  naver.client_secret_present={present} length={length}".format(
            present=naver_red["client_secret_present"],
            length=naver_red["client_secret_length"],
        ),
        file=stdout,
    )
    print(f"  naver.base_url={naver_red['base_url']}", file=stdout)
    yt_red = yt_cfg.redacted()
    print(f"  youtube.live_enabled={yt_cfg.live_enabled}", file=stdout)
    print(
        "  youtube.api_key_present={present} length={length}".format(
            present=yt_red["api_key_present"],
            length=yt_red["api_key_length"],
        ),
        file=stdout,
    )
    print(f"  youtube.base_url={yt_red['base_url']}", file=stdout)


def _smoke_command(env: Mapping[str, str]) -> Optional[List[str]]:
    has_naver = bool(env.get("NAVER_CLIENT_ID")) and bool(env.get("NAVER_CLIENT_SECRET"))
    has_youtube = bool(env.get("YOUTUBE_DATA_API_KEY"))
    if has_naver and has_youtube:
        return [
            sys.executable,
            "scripts/research_content.py",
            "--keyword", "소방공사",
            "--naver-types", "blog,news,cafearticle",
            "--naver-display", "3",
            "--youtube-max-results", "3",
            "--youtube-with-details",
            "--live",
            "--json",
        ]
    if has_naver:
        return [
            sys.executable,
            "scripts/search_naver.py",
            "--type", "blog",
            "--query", "소방공사",
            "--display", "3",
            "--live",
            "--json",
        ]
    if has_youtube:
        return [
            sys.executable,
            "scripts/search_youtube.py",
            "--query", "소방공사",
            "--max-results", "3",
            "--with-details",
            "--live",
            "--json",
        ]
    return None


def _run_smoke(
    env: Mapping[str, str],
    stdout: TextIO,
    stderr: TextIO,
    runner: Callable[..., subprocess.CompletedProcess],
) -> int:
    cmd = _smoke_command(env)
    if cmd is None:
        print(
            "[set_api_env_secret] smoke: SKIP — live-ready key 없음 (Naver/Youtube 미설정)",
            file=stderr,
        )
        return 0
    print(f"[set_api_env_secret] smoke: {' '.join(cmd)}", file=stdout)
    proc_env = dict(os.environ)
    for k, v in env.items():
        proc_env[k] = v
    completed = runner(cmd, env=proc_env, cwd=str(_REPO_ROOT))
    return int(getattr(completed, "returncode", 0) or 0)


def _build_effective_env(file_env: Mapping[str, str]) -> Dict[str, str]:
    out: Dict[str, str] = {**os.environ}
    for k in tuple(ALLOWED_KEYS) + _PASSTHROUGH_ENV_KEYS:
        if k in file_env:
            out[k] = file_env[k]
    return out


def main(
    argv: Optional[Sequence[str]] = None,
    stdin: Optional[TextIO] = None,
    stdout: Optional[TextIO] = None,
    stderr: Optional[TextIO] = None,
    runner: Optional[Callable[..., subprocess.CompletedProcess]] = None,
) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    stdin = stdin if stdin is not None else sys.stdin
    stdout = stdout if stdout is not None else sys.stdout
    stderr = stderr if stderr is not None else sys.stderr
    runner = runner if runner is not None else subprocess.run

    args = _build_parser().parse_args(argv)

    if not (args.set_key or args.verify or args.run_smoke):
        print(
            "[set_api_env_secret] ERROR: 작업이 지정되지 않았습니다 — --set / --verify / --run-smoke 중 하나 이상 필요",
            file=stderr,
        )
        return 2

    env_path = Path(args.env_path)

    if args.set_key:
        if not args.value_stdin:
            print(
                "[set_api_env_secret] ERROR: --set 사용 시 --value-stdin 이 필수입니다 (값은 stdin 으로만 받는다)",
                file=stderr,
            )
            return 2

        value = _read_value_from_stdin(stdin)
        if not value:
            print(
                "[set_api_env_secret] ERROR: stdin 에서 빈 값이 입력되었습니다 (등록 거절)",
                file=stderr,
            )
            return 2
        if "\n" in value or "\r" in value or "\x00" in value:
            print(
                "[set_api_env_secret] ERROR: value 에 줄바꿈/제어문자가 포함되었습니다 (등록 거절)",
                file=stderr,
            )
            return 2

        existing_lines: List[str] = []
        if env_path.exists():
            existing_lines = env_path.read_text(encoding="utf-8").splitlines()

        new_lines, replaced = _upsert_env_line(existing_lines, args.set_key, value)
        if replaced:
            print(
                f"[set_api_env_secret] WARN: {args.set_key} 의 기존 값을 덮어씁니다 (.env)",
                file=stderr,
            )
        _atomic_write_env(env_path, new_lines)
        print(
            f"[set_api_env_secret] upserted: key={args.set_key} env_path={env_path}",
            file=stdout,
        )
        # value 는 명시적으로 폐기.
        del value

    file_env = _parse_env_file(env_path)
    effective_env = _build_effective_env(file_env)

    if args.verify:
        _print_redacted(stdout, effective_env)

    if args.run_smoke:
        rc = _run_smoke(effective_env, stdout, stderr, runner=runner)
        if rc != 0:
            return rc

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
