import json

from tools.devflow import pre_change_dry_run as pre


def test_build_record_marks_ok_and_scope():
    record = pre.build_record(
        scope="smartstore",
        reason="router change",
        command=["python", "-m", "pytest"],
        exit_code=0,
        output="passed",
    )

    assert record["phase"] == "before_code_update"
    assert record["status"] == "ok"
    assert record["scope"] == "smartstore"
    assert record["output_tail"] == "passed"


def test_save_and_check_latest_for_scope(tmp_path):
    latest = tmp_path / "latest.json"
    history = tmp_path / "history"
    record = pre.build_record(
        scope="naver",
        reason="content guard",
        command=["python", "-m", "pytest"],
        exit_code=0,
    )

    history_path = pre.save_record(record, latest_path=latest, history_dir=history)

    assert history_path.exists()
    assert json.loads(latest.read_text(encoding="utf-8"))["scope"] == "naver"
    assert pre.latest_ok_for_scope("naver", path=latest) is True
    assert pre.latest_ok_for_scope("smartstore", path=latest) is False


def test_failed_record_is_not_ok_for_scope(tmp_path):
    latest = tmp_path / "latest.json"
    record = pre.build_record(
        scope="hiworks",
        reason="negative",
        command=["false"],
        exit_code=1,
    )
    pre.save_record(record, latest_path=latest, history_dir=tmp_path / "history")

    assert pre.latest_ok_for_scope("hiworks", path=latest) is False
