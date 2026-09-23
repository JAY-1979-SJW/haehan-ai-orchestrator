"""앱 동작 디스패처 — 완전성(누락 0) + 안전성(위험동작 자동실행 금지) 회귀 테스트."""

import re

from ai_orchestrator.routers import app_actions

# 위험·민감 키워드: 이 키워드가 들어간 동작은 절대 SAFE(자동실행)면 안 된다.
_DANGER = re.compile(
    r"send|발송|전송|결제|구매|송금|이체|삭제|delete|remove|투찰|입찰|submit|제출|발행|publish|"
    r"게시|approve|승인|reject|upload|업로드|배포|deploy|webhook|login|signup|register|revoke|"
    r"fax|팩스|setup|reset|export|dispatch|consent|cancel|환불",
    re.IGNORECASE,
)


def test_manifest_covers_all_post_routes():
    """매니페스트가 모든 POST 라우트를 빠짐없이 포함(introspect 기반 → 항상 일치)."""
    man = app_actions.build_manifest()
    routes = app_actions._post_routes()
    assert len(man) == len(routes), "매니페스트 수 != POST 라우트 수 (누락 발생)"
    assert len(man) > 50, "동작이 비정상적으로 적음(introspect 실패 의심)"


def test_destructive_actions_never_auto_safe():
    """발송·결제·삭제·발행·승인·로그인·팩스 등 위험 동작이 SAFE로 분류되면 안 된다."""
    bad = [
        a
        for a in app_actions.build_manifest()
        if a["risk"] == "SAFE" and _DANGER.search(f"{a['path']} {a['func']} {a['desc']}")
    ]
    assert not bad, f"위험 동작이 SAFE(자동실행)로 분류됨: {[a['path'] for a in bad]}"


def test_run_action_gates_destructive():
    """위험 동작 실행 요청은 needs_confirm 으로 차단되어야 한다(자동 실행 금지)."""
    owner = {"actor": "test", "role": "owner"}
    for path in ("/api/v1/gmail/send", "/api/v1/hanafax/send"):
        r = app_actions.run_action(path, {}, owner)
        assert r.get("needs_confirm") is True, f"{path} 가 차단되지 않음(위험!)"
        assert r.get("ok") is not True


def test_run_action_unknown_path():
    """없는 path 는 안전하게 오류 반환(크래시 금지)."""
    r = app_actions.run_action("/api/v1/__nope__", {}, {"role": "owner"})
    assert r.get("ok") is not True
    assert "찾을 수 없" in r.get("error", "")
