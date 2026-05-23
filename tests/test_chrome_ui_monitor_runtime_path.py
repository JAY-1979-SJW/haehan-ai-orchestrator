from scripts.archive.misc import chrome_ui_monitor


def test_chrome_ui_monitor_state_file_is_runtime_data_path():
    rel = chrome_ui_monitor.STATE_FILE.relative_to(chrome_ui_monitor.REPO_ROOT).as_posix()

    assert rel == "data/runtime/chrome_ui_monitor_state.json"
    assert "scripts/archive/data" not in rel
