"""서버 결과 필터: result_full 만 긴 문자열을 허용하고 나머지 문자열은 기존처럼 500자로 자른다."""

from ai_orchestrator.agent_hub.redaction import _RESULT_DATA_LONG_KEYS, _strip_result_data


def test_result_full_passes_long_but_others_stay_500():
    out = _strip_result_data({"result": "a" * 3000, "result_full": "b" * 15000, "message": "c" * 900})
    assert len(out["result"]) == 500  # 기존 동작 유지
    assert len(out["message"]) == 500
    assert len(out["result_full"]) == 15000


def test_result_full_has_upper_bound():
    out = _strip_result_data({"result_full": "x" * 50000})
    assert len(out["result_full"]) == _RESULT_DATA_LONG_KEYS["result_full"] == 20000


def test_sensitive_keys_still_dropped():
    out = _strip_result_data({"result_full": "ok", "password": "p", "token": "t"})
    assert out == {"result_full": "ok"}
