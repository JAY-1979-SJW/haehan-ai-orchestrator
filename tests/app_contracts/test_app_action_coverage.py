"""앱 동작 디스패처 — 완전성(누락 0) + 안전성(위험동작 자동실행 금지) 회귀 테스트."""

import re

import ai_orchestrator.asgi  # noqa: F401 — 앱을 만들면서 app_actions 에 앱을 주입한다
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
    # 2026-09-29 defect_index #39: FastAPI _IncludedRouter 버그로 build_manifest() 가
    # 계속 빈 리스트를 반환해 이 테스트가 그동안 비교대상 0건으로 공허하게 통과하고
    # 있었음(수정 완료, ai_orchestrator/routers/app_actions.py). 실제 데이터로 처음
    # 돌려보니 register/upload/setup/reset/publish 계열 SAFE 오분류가 드러나
    # _DESTRUCTIVE 를 확장해 해결. 아래 2건은 "게시글"(명사=post) 이 "게시"(동사=
    # publish) 와 겹치는 한국어 동형이의어 오탐으로 직접 코드 확인(읽기전용 추출/분석,
    # 쓰기 없음) — _DANGER 의 "게시" 를 없애면 이 검사의 탐지력이 전반적으로 약해지므로
    # 정규식 대신 여기서 알려진 예외로 명시.
    _KNOWN_SAFE_FALSE_POSITIVES = {
        "/api/v1/community/extract",  # 게시글 목록 추출(읽기전용) — "게시"= 명사
        "/api/v1/community/analyze",  # 게시글 트렌드 분석(읽기전용) — "게시"= 명사
    }
    man = app_actions.build_manifest()
    # 공허한 통과 방지 가드: man 이 비면 아래 filter 는 항상 빈 리스트를 만들어 assert가
    # 항상 통과하고, 이 검사 자체가 아무 일도 안 하고 있었던 걸 계속 숨긴다(이번에 실제로
    # 벌어졌던 사고, 위 주석 참고) — test_manifest_covers_all_post_routes 의 가드와 동일.
    assert len(man) > 50, "동작이 비정상적으로 적음(introspect 실패 의심) — 아래 검사가 공허하게 통과할 위험"
    bad = [
        a
        for a in man
        if a["risk"] == "SAFE"
        and a["path"] not in _KNOWN_SAFE_FALSE_POSITIVES
        and _DANGER.search(f"{a['path']} {a['func']} {a['desc']}")
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
