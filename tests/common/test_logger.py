import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / ".."))


def _fresh_logger_module(tmp_logs_dir: str):
    """logger 모듈을 재로드하여 임시 경로 주입"""
    import orchestrator_v1.core.logger as lg_mod

    original = lg_mod.LOGS_DIR
    lg_mod.LOGS_DIR = Path(tmp_logs_dir)
    # 기존 핸들러 제거해서 새 경로로 재생성 가능하게
    for name in list(logging.Logger.manager.loggerDict.keys()):
        if name.startswith("orchestrator.test_"):
            lobj = logging.getLogger(name)
            lobj.handlers.clear()
    return lg_mod, original


def test_logs_dir_created_on_get_logger(tmp_path):
    import orchestrator_v1.core.logger as lg_mod

    original = lg_mod.LOGS_DIR
    try:
        new_dir = str(tmp_path / "test_logs")
        lg_mod.LOGS_DIR = new_dir
        # 핸들러 없는 새 이름으로 호출
        lg = lg_mod.get_logger("test_init_dir")  # noqa: F841
        assert Path(new_dir).is_dir(), "logs 디렉토리 자동 생성 실패"
    finally:
        lg_mod.LOGS_DIR = original


def test_orchestrator_log_written(tmp_path):
    import orchestrator_v1.core.logger as lg_mod

    original = lg_mod.LOGS_DIR
    try:
        new_dir = str(tmp_path / "test_logs2")
        lg_mod.LOGS_DIR = new_dir
        lg = lg_mod.get_logger("test_write_check")
        lg.info(
            "test message hello",
            extra={"event_type": "TASK_RECEIVED", "task_id": "t-001", "action_type": "read_file", "actor": "tester"},
        )
        # 핸들러 flush
        for h in lg.handlers:
            h.flush()
        log_file = Path(new_dir) / "orchestrator.log"
        assert log_file.is_file(), "orchestrator.log 미생성"
        content = log_file.open(encoding="utf-8").read()
        assert "test message hello" in content
        assert "TASK_RECEIVED" in content
    finally:
        lg_mod.LOGS_DIR = original


def test_error_log_separated(tmp_path):
    import orchestrator_v1.core.logger as lg_mod

    original = lg_mod.LOGS_DIR
    try:
        new_dir = str(tmp_path / "test_logs3")
        lg_mod.LOGS_DIR = new_dir
        lg = lg_mod.get_logger("test_error_sep")
        lg.error(
            "critical error occurred",
            extra={"event_type": "EXECUTION_FAILED", "task_id": "t-err", "action_type": "run_shell", "actor": "system"},
        )
        for h in lg.handlers:
            h.flush()
        error_file = Path(new_dir) / "orchestrator.error.log"
        main_file = Path(new_dir) / "orchestrator.log"
        assert error_file.is_file(), "orchestrator.error.log 미생성"
        err_content = error_file.open(encoding="utf-8").read()
        assert "critical error occurred" in err_content
        # error는 main log에도 포함됨 (INFO+ 핸들러)
        main_content = main_file.open(encoding="utf-8").read()
        assert "critical error occurred" in main_content
    finally:
        lg_mod.LOGS_DIR = original


def test_log_event_helper(tmp_path):
    import orchestrator_v1.core.logger as lg_mod

    original = lg_mod.LOGS_DIR
    try:
        new_dir = str(tmp_path / "test_logs4")
        lg_mod.LOGS_DIR = new_dir
        lg = lg_mod.get_logger("test_helper")
        lg_mod.log_event(
            lg,
            logging.INFO,
            "helper test",
            event_type="PLAN_CREATED",
            task_id="t-plan",
            action_type="edit_config",
            actor="app",
        )
        for h in lg.handlers:
            h.flush()
        content = (Path(new_dir) / "orchestrator.log").open(encoding="utf-8").read()
        assert "PLAN_CREATED" in content
        assert "t-plan" in content
    finally:
        lg_mod.LOGS_DIR = original
