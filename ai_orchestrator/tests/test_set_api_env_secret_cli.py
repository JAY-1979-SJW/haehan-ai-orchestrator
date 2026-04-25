"""Tests for scripts/set_api_env_secret.py (F-4S-4K).

검증 포인트:
- stdin 으로 받은 value 가 .env 에 upsert 된다.
- stdout / stderr 에 value 원문이 절대 노출되지 않는다.
- 기존 key 는 덮어쓰기 가능, 다른 라인은 보존된다.
- 허용되지 않은 key 는 argparse 단계에서 거절된다.
- .env 전체 내용은 출력되지 않는다.
- --verify 는 redacted 출력만 한다 (원문/length 만 노출).
- --run-smoke 는 키가 없으면 SKIP, 있으면 적절한 명령을 호출한다 (실제 호출은 mock).
"""
from __future__ import annotations

import io
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import List

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
_SCRIPTS_DIR = _REPO_ROOT / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import set_api_env_secret as mod  # type: ignore  # noqa: E402


SECRET_VALUE = "super-secret-value-not-to-leak-XYZ"
OTHER_LINE_KEY = "OPENAI_API_KEY"
OTHER_LINE_VALUE = "sk-existing-untouched-line-VALUE"


def _run(argv, stdin_text="", env_keys_to_strip=("NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET", "YOUTUBE_DATA_API_KEY"), monkeypatch=None, runner=None):
    """main() 호출 + stdout/stderr 캡처 헬퍼."""
    if monkeypatch is not None:
        for k in env_keys_to_strip:
            monkeypatch.delenv(k, raising=False)
    out = io.StringIO()
    err = io.StringIO()
    rc = mod.main(
        argv=argv,
        stdin=io.StringIO(stdin_text),
        stdout=out,
        stderr=err,
        runner=runner if runner is not None else _no_runner,
    )
    return rc, out.getvalue(), err.getvalue()


def _no_runner(*args, **kwargs):
    raise AssertionError("subprocess runner must not be called in this test")


def _make_completed(returncode=0):
    return SimpleNamespace(returncode=returncode)


# ---------------------------------------------------------------------------
# Upsert behavior
# ---------------------------------------------------------------------------

def test_set_writes_value_into_env_file(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    rc, out, err = _run(
        ["--set", "NAVER_CLIENT_ID", "--value-stdin", "--env-path", str(env_path)],
        stdin_text=SECRET_VALUE + "\n",
        monkeypatch=monkeypatch,
    )
    assert rc == 0
    text = env_path.read_text(encoding="utf-8")
    assert f"NAVER_CLIENT_ID={SECRET_VALUE}" in text


def test_secret_value_is_not_leaked_to_stdout_or_stderr(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    rc, out, err = _run(
        ["--set", "NAVER_CLIENT_SECRET", "--value-stdin", "--env-path", str(env_path)],
        stdin_text=SECRET_VALUE + "\n",
        monkeypatch=monkeypatch,
    )
    assert rc == 0
    assert SECRET_VALUE not in out
    assert SECRET_VALUE not in err
    # key name only — len(value) 등 길이 노출도 아직은 없음.
    assert "NAVER_CLIENT_SECRET" in out
    assert str(len(SECRET_VALUE)) not in out


def test_existing_key_is_replaced_and_warned(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "# header comment\n"
        f"{OTHER_LINE_KEY}={OTHER_LINE_VALUE}\n"
        "NAVER_CLIENT_ID=PREVIOUS_VALUE_XXX\n"
        "TRAILING_KEY=trail\n",
        encoding="utf-8",
    )
    rc, out, err = _run(
        ["--set", "NAVER_CLIENT_ID", "--value-stdin", "--env-path", str(env_path)],
        stdin_text=SECRET_VALUE + "\n",
        monkeypatch=monkeypatch,
    )
    assert rc == 0
    text = env_path.read_text(encoding="utf-8")
    assert f"NAVER_CLIENT_ID={SECRET_VALUE}" in text
    assert "PREVIOUS_VALUE_XXX" not in text
    # 다른 라인은 보존
    assert f"{OTHER_LINE_KEY}={OTHER_LINE_VALUE}" in text
    assert "TRAILING_KEY=trail" in text
    assert "# header comment" in text
    # WARN 표시
    assert "WARN" in err
    assert "NAVER_CLIENT_ID" in err
    # 기존 값도 stderr 에 노출되지 않음
    assert "PREVIOUS_VALUE_XXX" not in err
    assert "PREVIOUS_VALUE_XXX" not in out


def test_unknown_key_rejected_by_argparse(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    out = io.StringIO()
    err = io.StringIO()
    with pytest.raises(SystemExit) as excinfo:
        mod.main(
            argv=["--set", "OPENAI_API_KEY", "--value-stdin", "--env-path", str(env_path)],
            stdin=io.StringIO(SECRET_VALUE),
            stdout=out,
            stderr=err,
            runner=_no_runner,
        )
    assert excinfo.value.code != 0
    assert SECRET_VALUE not in out.getvalue()
    assert SECRET_VALUE not in err.getvalue()
    assert not env_path.exists()


def test_set_requires_input_mode_flag(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    rc, out, err = _run(
        ["--set", "NAVER_CLIENT_ID", "--env-path", str(env_path)],
        stdin_text="",
        monkeypatch=monkeypatch,
    )
    assert rc != 0
    # 새 에러는 두 입력 모드 중 하나를 요구한다.
    assert "--prompt" in err and "--value-stdin" in err
    assert not env_path.exists()


def test_empty_stdin_value_rejected(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    rc, out, err = _run(
        ["--set", "NAVER_CLIENT_ID", "--value-stdin", "--env-path", str(env_path)],
        stdin_text="\n",
        monkeypatch=monkeypatch,
    )
    assert rc != 0
    assert "빈 값" in err or "empty" in err.lower()
    assert not env_path.exists()


def test_no_action_returns_error(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    rc, out, err = _run(
        ["--env-path", str(env_path)],
        monkeypatch=monkeypatch,
    )
    assert rc != 0


# ---------------------------------------------------------------------------
# .env 전체 내용 미노출
# ---------------------------------------------------------------------------

def test_env_file_contents_not_dumped_to_stdout(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    other_value = "ANOTHER_SECRET_VALUE_PLEASE_HIDE"
    env_path.write_text(
        f"{OTHER_LINE_KEY}={other_value}\n"
        "YOUTUBE_DATA_API_KEY=yt-existing-do-not-print\n",
        encoding="utf-8",
    )
    rc, out, err = _run(
        ["--set", "NAVER_CLIENT_ID", "--value-stdin", "--env-path", str(env_path)],
        stdin_text=SECRET_VALUE + "\n",
        monkeypatch=monkeypatch,
    )
    assert rc == 0
    combined = out + err
    assert other_value not in combined
    assert "yt-existing-do-not-print" not in combined
    assert SECRET_VALUE not in combined


# ---------------------------------------------------------------------------
# --verify
# ---------------------------------------------------------------------------

def test_verify_only_prints_redacted_summary(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text(
        f"NAVER_CLIENT_ID={SECRET_VALUE}\n"
        f"NAVER_CLIENT_SECRET={SECRET_VALUE}-2\n"
        f"YOUTUBE_DATA_API_KEY={SECRET_VALUE}-3\n",
        encoding="utf-8",
    )
    rc, out, err = _run(
        ["--verify", "--env-path", str(env_path)],
        monkeypatch=monkeypatch,
    )
    assert rc == 0
    # 원문 secret 미노출
    assert SECRET_VALUE not in out
    assert SECRET_VALUE not in err
    # redacted 핵심 항목 노출
    assert "naver.live_enabled=True" in out
    assert "naver.client_id_present=True" in out
    assert "naver.client_secret_present=True" in out
    assert "youtube.live_enabled=True" in out
    assert "youtube.api_key_present=True" in out
    # length 만 표시
    assert f"length={len(SECRET_VALUE)}" in out


def test_verify_when_no_keys_reports_not_live(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text("# empty\n", encoding="utf-8")
    rc, out, err = _run(
        ["--verify", "--env-path", str(env_path)],
        monkeypatch=monkeypatch,
    )
    assert rc == 0
    assert "naver.live_enabled=False" in out
    assert "youtube.live_enabled=False" in out


# ---------------------------------------------------------------------------
# --run-smoke
# ---------------------------------------------------------------------------

def test_run_smoke_skips_when_no_keys(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text("# empty\n", encoding="utf-8")
    calls: List[list] = []

    def runner(cmd, env=None, cwd=None):
        calls.append(cmd)
        return _make_completed(0)

    rc, out, err = _run(
        ["--run-smoke", "--env-path", str(env_path)],
        monkeypatch=monkeypatch,
        runner=runner,
    )
    assert rc == 0
    assert calls == []
    assert "SKIP" in err


def test_run_smoke_invokes_naver_only_when_only_naver_keys(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text(
        f"NAVER_CLIENT_ID={SECRET_VALUE}\n"
        f"NAVER_CLIENT_SECRET={SECRET_VALUE}-2\n",
        encoding="utf-8",
    )
    captured = {}

    def runner(cmd, env=None, cwd=None):
        captured["cmd"] = cmd
        captured["env"] = env
        return _make_completed(0)

    rc, out, err = _run(
        ["--run-smoke", "--env-path", str(env_path)],
        monkeypatch=monkeypatch,
        runner=runner,
    )
    assert rc == 0
    cmd = captured["cmd"]
    assert any("search_naver.py" in part for part in cmd)
    assert "--live" in cmd
    # subprocess env 에는 키가 전달됨, 콘솔에는 노출되지 않음
    assert captured["env"]["NAVER_CLIENT_ID"] == SECRET_VALUE
    assert SECRET_VALUE not in out
    assert SECRET_VALUE not in err


def test_run_smoke_invokes_youtube_only_when_only_youtube_key(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text(f"YOUTUBE_DATA_API_KEY={SECRET_VALUE}\n", encoding="utf-8")
    captured = {}

    def runner(cmd, env=None, cwd=None):
        captured["cmd"] = cmd
        return _make_completed(0)

    rc, out, err = _run(
        ["--run-smoke", "--env-path", str(env_path)],
        monkeypatch=monkeypatch,
        runner=runner,
    )
    assert rc == 0
    cmd = captured["cmd"]
    assert any("search_youtube.py" in part for part in cmd)
    assert "--live" in cmd


def test_run_smoke_invokes_research_when_both_present(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text(
        f"NAVER_CLIENT_ID={SECRET_VALUE}\n"
        f"NAVER_CLIENT_SECRET={SECRET_VALUE}-2\n"
        f"YOUTUBE_DATA_API_KEY={SECRET_VALUE}-3\n",
        encoding="utf-8",
    )
    captured = {}

    def runner(cmd, env=None, cwd=None):
        captured["cmd"] = cmd
        return _make_completed(0)

    rc, out, err = _run(
        ["--run-smoke", "--env-path", str(env_path)],
        monkeypatch=monkeypatch,
        runner=runner,
    )
    assert rc == 0
    cmd = captured["cmd"]
    assert any("research_content.py" in part for part in cmd)
    assert "--live" in cmd
    assert "--json" in cmd


# ---------------------------------------------------------------------------
# --prompt (no-echo) — F-4S-4K-b
# ---------------------------------------------------------------------------

PROMPT_SECRET = "prompt-secret-NEVER-print-ZZZ"


def test_prompt_calls_getpass_and_writes_value(tmp_path, monkeypatch):
    """--prompt 가 기본적으로 getpass.getpass 를 호출하고 값을 .env 에 저장한다."""
    env_path = tmp_path / ".env"
    monkeypatch.delenv("NAVER_CLIENT_ID", raising=False)
    monkeypatch.delenv("NAVER_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("YOUTUBE_DATA_API_KEY", raising=False)

    calls = []

    def fake_getpass(prompt: str = "") -> str:
        calls.append(prompt)
        return PROMPT_SECRET

    monkeypatch.setattr(mod.getpass, "getpass", fake_getpass)

    out = io.StringIO()
    err = io.StringIO()
    rc = mod.main(
        argv=["--set", "NAVER_CLIENT_ID", "--prompt", "--env-path", str(env_path)],
        stdin=io.StringIO(""),
        stdout=out,
        stderr=err,
        runner=_no_runner,
    )
    assert rc == 0
    assert len(calls) == 1
    # 프롬프트 메시지 자체는 secret 을 포함하지 않아야 한다.
    assert PROMPT_SECRET not in calls[0]
    assert "NAVER_CLIENT_ID" in calls[0]
    assert "no echo" in calls[0].lower()

    text = env_path.read_text(encoding="utf-8")
    assert f"NAVER_CLIENT_ID={PROMPT_SECRET}" in text


def test_prompt_value_is_not_leaked_to_stdout_or_stderr(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    monkeypatch.setattr(mod.getpass, "getpass", lambda prompt="": PROMPT_SECRET)

    out = io.StringIO()
    err = io.StringIO()
    rc = mod.main(
        argv=[
            "--set", "YOUTUBE_DATA_API_KEY",
            "--prompt",
            "--env-path", str(env_path),
            "--verify",
        ],
        stdin=io.StringIO(""),
        stdout=out,
        stderr=err,
        runner=_no_runner,
    )
    assert rc == 0
    assert PROMPT_SECRET not in out.getvalue()
    assert PROMPT_SECRET not in err.getvalue()
    # redacted 출력에 length 만 노출
    assert f"length={len(PROMPT_SECRET)}" in out.getvalue()


def test_prompt_can_be_injected_via_main_for_testability(tmp_path, monkeypatch):
    """prompt_reader 파라미터로 주입한 함수가 사용된다 (terminal 의존 제거)."""
    env_path = tmp_path / ".env"
    monkeypatch.delenv("NAVER_CLIENT_ID", raising=False)
    monkeypatch.delenv("NAVER_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("YOUTUBE_DATA_API_KEY", raising=False)

    seen = []

    def fake_reader(prompt: str) -> str:
        seen.append(prompt)
        return PROMPT_SECRET

    out = io.StringIO()
    err = io.StringIO()
    rc = mod.main(
        argv=["--set", "NAVER_CLIENT_SECRET", "--prompt", "--env-path", str(env_path)],
        stdin=io.StringIO(""),
        stdout=out,
        stderr=err,
        runner=_no_runner,
        prompt_reader=fake_reader,
    )
    assert rc == 0
    assert len(seen) == 1
    assert PROMPT_SECRET not in out.getvalue()
    assert PROMPT_SECRET not in err.getvalue()
    text = env_path.read_text(encoding="utf-8")
    assert f"NAVER_CLIENT_SECRET={PROMPT_SECRET}" in text


def test_prompt_and_value_stdin_are_mutually_exclusive(tmp_path, monkeypatch):
    """argparse 의 mutually-exclusive 그룹이 동시 사용을 거절한다."""
    env_path = tmp_path / ".env"
    monkeypatch.setattr(mod.getpass, "getpass", lambda prompt="": PROMPT_SECRET)

    out = io.StringIO()
    err = io.StringIO()
    with pytest.raises(SystemExit) as excinfo:
        mod.main(
            argv=[
                "--set", "NAVER_CLIENT_ID",
                "--prompt",
                "--value-stdin",
                "--env-path", str(env_path),
            ],
            stdin=io.StringIO(SECRET_VALUE + "\n"),
            stdout=out,
            stderr=err,
            runner=_no_runner,
        )
    assert excinfo.value.code != 0
    # 실패 후 .env 에 secret 이 기록되지 않는다.
    assert not env_path.exists()
    assert PROMPT_SECRET not in out.getvalue()
    assert PROMPT_SECRET not in err.getvalue()
    assert SECRET_VALUE not in out.getvalue()
    assert SECRET_VALUE not in err.getvalue()


def test_prompt_empty_value_rejected(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    monkeypatch.setattr(mod.getpass, "getpass", lambda prompt="": "   \n")

    out = io.StringIO()
    err = io.StringIO()
    rc = mod.main(
        argv=["--set", "NAVER_CLIENT_ID", "--prompt", "--env-path", str(env_path)],
        stdin=io.StringIO(""),
        stdout=out,
        stderr=err,
        runner=_no_runner,
    )
    assert rc != 0
    assert not env_path.exists()


def test_prompt_eof_returns_error_without_writing(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"

    def raise_eof(prompt: str = "") -> str:
        raise EOFError

    monkeypatch.setattr(mod.getpass, "getpass", raise_eof)

    out = io.StringIO()
    err = io.StringIO()
    rc = mod.main(
        argv=["--set", "NAVER_CLIENT_ID", "--prompt", "--env-path", str(env_path)],
        stdin=io.StringIO(""),
        stdout=out,
        stderr=err,
        runner=_no_runner,
    )
    assert rc != 0
    assert not env_path.exists()
