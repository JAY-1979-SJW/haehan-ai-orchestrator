"""LocalRunner hardening tests (P1-FIX).

Verifies P1-FIX changes to desktop/local_runner.py:
1. Popen 직후 poll 검증 — 즉시 죽는 프로세스 false-positive 차단
2. stdout/stderr 파일 redirect — PIPE buffer block 방지
3. start() 결과가 실제 프로세스 상태를 반영
4. 로그 파일에 secret 노출 없음
"""
from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

# desktop/local_runner.py has no pystray/PIL dependency — direct import is safe.
from desktop.local_runner import LocalRunner


# ---------------------------------------------------------------------------
# Test scripts (created on the fly into tmp dir)
# ---------------------------------------------------------------------------

_LONG_RUNNING_SCRIPT = (
    "import time\n"
    "while True:\n"
    "    time.sleep(0.1)\n"
)

_IMMEDIATE_EXIT_SCRIPT = (
    "import sys\n"
    "sys.exit(1)\n"
)

_QUICK_OUTPUT_SCRIPT = (
    "import sys\n"
    "sys.stdout.write('runner stdout marker\\n')\n"
    "sys.stderr.write('runner stderr marker\\n')\n"
    "sys.stdout.flush()\n"
    "sys.stderr.flush()\n"
    "import time; time.sleep(0.5)\n"
)


class _TmpScriptCase(unittest.TestCase):
    """Base class providing a tmp dir + helper to write a runner script."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _write_script(self, body: str, name: str = "runner.py") -> Path:
        p = self.tmp_path / name
        p.write_text(body, encoding="utf-8")
        return p


# ---------------------------------------------------------------------------
# 1. Process starts and remains running
# ---------------------------------------------------------------------------

class TestLocalRunnerStartVerification(_TmpScriptCase):
    def test_long_running_process_reports_running(self):
        script = self._write_script(_LONG_RUNNING_SCRIPT)
        log_dir = self.tmp_path / "logs"
        runner = LocalRunner(runner_script=script, log_dir=log_dir)

        try:
            ok = runner.start()
            self.assertTrue(ok, "start() should return True for long-running script")
            self.assertEqual(runner.get_status(), "running")
            self.assertIsNotNone(runner.get_pid())
        finally:
            runner.stop()

    def test_immediate_exit_reports_error(self):
        """Process that exits during verify window must NOT be reported as running."""
        script = self._write_script(_IMMEDIATE_EXIT_SCRIPT)
        log_dir = self.tmp_path / "logs"
        runner = LocalRunner(runner_script=script, log_dir=log_dir,
                              start_verify_delay=0.3)

        ok = runner.start()
        self.assertFalse(ok, "start() must return False for immediately-dying script")
        self.assertEqual(runner.get_status(), "error")
        self.assertIsNotNone(runner.get_last_error())
        self.assertIn("immediately", runner.get_last_error().lower())

    def test_double_start_is_idempotent_when_running(self):
        script = self._write_script(_LONG_RUNNING_SCRIPT)
        log_dir = self.tmp_path / "logs"
        runner = LocalRunner(runner_script=script, log_dir=log_dir)

        try:
            self.assertTrue(runner.start())
            pid1 = runner.get_pid()
            # Second start should not spawn a second process
            self.assertTrue(runner.start())
            pid2 = runner.get_pid()
            self.assertEqual(pid1, pid2)
        finally:
            runner.stop()


# ---------------------------------------------------------------------------
# 2. stdout/stderr file redirect (no PIPE buffer block)
# ---------------------------------------------------------------------------

class TestLocalRunnerLogRedirect(_TmpScriptCase):
    def test_stdout_stderr_redirected_to_log_files(self):
        """Runner must redirect stdout/stderr to files, not subprocess.PIPE."""
        script = self._write_script(_QUICK_OUTPUT_SCRIPT)
        log_dir = self.tmp_path / "logs"
        runner = LocalRunner(runner_script=script, log_dir=log_dir)

        try:
            self.assertTrue(runner.start())
            # Wait for the script to flush and exit
            time.sleep(1.0)
            # Log dir should now contain stdout/stderr files
            log_files = list(log_dir.glob("local_runner_*.log"))
            self.assertGreaterEqual(
                len(log_files), 2,
                f"Expected ≥2 log files (stdout+stderr), got: {log_files}"
            )

            # Find which is stdout, which is stderr
            stdout_files = list(log_dir.glob("*.stdout.log"))
            stderr_files = list(log_dir.glob("*.stderr.log"))
            self.assertEqual(len(stdout_files), 1)
            self.assertEqual(len(stderr_files), 1)

            stdout_content = stdout_files[0].read_text(encoding="utf-8", errors="replace")
            stderr_content = stderr_files[0].read_text(encoding="utf-8", errors="replace")
            self.assertIn("runner stdout marker", stdout_content)
            self.assertIn("runner stderr marker", stderr_content)
        finally:
            runner.stop()

    def test_runner_does_not_use_pipe(self):
        """Source must NOT pass subprocess.PIPE for stdout/stderr (avoids buffer block)."""
        import inspect
        from desktop import local_runner as lr
        src = inspect.getsource(lr)
        # Find the Popen call and verify no PIPE for stdout/stderr
        # Look for "stdout=subprocess.PIPE" or "stderr=subprocess.PIPE"
        self.assertNotIn("stdout=subprocess.PIPE", src)
        self.assertNotIn("stderr=subprocess.PIPE", src)


# ---------------------------------------------------------------------------
# 3. Logs do not expose secrets
# ---------------------------------------------------------------------------

class TestLocalRunnerLogSafety(_TmpScriptCase):
    def test_log_filename_has_no_secret_segments(self):
        """Log filenames must be deterministic, no token/secret values."""
        script = self._write_script(_LONG_RUNNING_SCRIPT)
        log_dir = self.tmp_path / "logs"
        runner = LocalRunner(runner_script=script, log_dir=log_dir)
        try:
            runner.start()
            log_files = [p.name for p in log_dir.iterdir()]
            for name in log_files:
                lower = name.lower()
                for forbidden in ["approval_token", "token_hash", "password",
                                  "device_token", "cookie", "session_token"]:
                    self.assertNotIn(forbidden, lower,
                                     f"Log filename leaks secret pattern: {name}")
        finally:
            runner.stop()


# ---------------------------------------------------------------------------
# 4. stop() and restart() resilience
# ---------------------------------------------------------------------------

class TestLocalRunnerStopRestart(_TmpScriptCase):
    def test_stop_after_immediate_exit_does_not_corrupt(self):
        """Stop after a failed start should leave a clean state."""
        script = self._write_script(_IMMEDIATE_EXIT_SCRIPT)
        log_dir = self.tmp_path / "logs"
        runner = LocalRunner(runner_script=script, log_dir=log_dir,
                              start_verify_delay=0.2)
        runner.start()
        self.assertTrue(runner.stop())
        # State should be settled, not in 'starting'
        self.assertIn(runner.get_status(), {"stopped", "error"})

    def test_restart_revives_running_process(self):
        script = self._write_script(_LONG_RUNNING_SCRIPT)
        log_dir = self.tmp_path / "logs"
        runner = LocalRunner(runner_script=script, log_dir=log_dir)
        try:
            self.assertTrue(runner.start())
            pid_before = runner.get_pid()
            self.assertTrue(runner.restart())
            pid_after = runner.get_pid()
            self.assertNotEqual(pid_before, pid_after,
                                "restart must spawn a new process")
            self.assertEqual(runner.get_status(), "running")
        finally:
            runner.stop()


if __name__ == "__main__":
    unittest.main()
