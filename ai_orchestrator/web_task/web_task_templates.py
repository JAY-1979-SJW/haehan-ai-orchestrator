"""웹 작업 템플릿 (Stage 3 — 간편 실행 인터페이스).

템플릿은 자주 쓰이는 provider/action_type 조합과 기본 입력값을
미리 묶어 둔 프리셋이다. 사용자는 template_id 만 지정하고 일부
override_params 만 넘기면 기존 web-task /run 흐름을 재사용할 수 있다.

보안 원칙:
  - default_params 에 password / token / cookie / client_secret /
    session / secret 등 민감값 절대 저장 금지.
  - 템플릿 조회 API 는 default_params 의 키 목록(default_param_keys) 만
    노출하고 원문 값은 응답에 포함하지 않는다.
  - 템플릿 기반 실행은 기존 승인 게이트와 dry_run 흐름을 그대로 사용한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# default_params 에 절대 들어가서는 안 되는 키 (저장 시점 차단)
_FORBIDDEN_KEYS: frozenset[str] = frozenset(
    {
        "password",
        "passwd",
        "pwd",
        "token",
        "access_token",
        "refresh_token",
        "session_token",
        "cookie",
        "cookies",
        "session",
        "client_secret",
        "secret",
        "api_secret",
        "api_key",
        "auth",
        "authorization",
    }
)


@dataclass(frozen=True)
class WebTaskTemplate:
    template_id: str
    provider: str
    action_type: str
    description: str
    default_params: dict = field(default_factory=dict)
    required_fields: list[str] = field(default_factory=list)


def _assert_no_secrets(template_id: str, default_params: dict) -> None:
    for k in default_params:
        if k.lower() in _FORBIDDEN_KEYS:
            raise ValueError(f"템플릿 {template_id}: default_params 에 민감 키({k}) 저장 금지")


def _build_templates() -> dict[str, WebTaskTemplate]:
    templates = [
        WebTaskTemplate(
            template_id="hiworks_default",
            provider="hiworks",
            action_type="developer_apply",
            description="하이웍스 개발자 센터 앱 등록 신청 기본 템플릿",
            default_params={
                "company_name": "해한",
                "purpose": "내부 자동화 연동",
            },
            required_fields=["app_name"],
        ),
        WebTaskTemplate(
            template_id="naver_default",
            provider="naver",
            action_type="app_register",
            description="네이버 개발자 센터 앱 등록 기본 템플릿",
            default_params={
                "company_name": "해한",
                "service_url": "https://haehan-ai.kr",
                "purpose": "내부 자동화 연동",
            },
            required_fields=["app_name"],
        ),
        WebTaskTemplate(
            template_id="google_default",
            provider="google",
            action_type="oauth_submit",
            description="Google Cloud Console OAuth 클라이언트 등록 기본 템플릿",
            default_params={
                "company_name": "해한",
                "service_url": "https://haehan-ai.kr",
                "redirect_uri": "https://haehan-ai.kr/oauth/callback",
                "purpose": "내부 자동화 연동",
            },
            required_fields=["app_name"],
        ),
    ]

    out: dict[str, WebTaskTemplate] = {}
    for t in templates:
        _assert_no_secrets(t.template_id, t.default_params)
        out[t.template_id] = t
    return out


_TEMPLATES: dict[str, WebTaskTemplate] = _build_templates()


def get_template(template_id: str) -> WebTaskTemplate | None:
    """template_id 로 조회. 미등록 시 None."""
    if not template_id:
        return None
    return _TEMPLATES.get(template_id)


def list_templates() -> list[dict]:
    """템플릿 목록 (default_params 원문 제외, 키 목록만 노출)."""
    return [
        {
            "template_id": t.template_id,
            "provider": t.provider,
            "action_type": t.action_type,
            "description": t.description,
            "required_fields": list(t.required_fields),
            "default_param_keys": sorted(t.default_params.keys()),
        }
        for t in _TEMPLATES.values()
    ]


def merge_params(template: WebTaskTemplate, override_params: dict) -> dict:
    """default_params + override_params 병합. override 가 우선."""
    merged: dict = dict(template.default_params)
    if override_params:
        merged.update(override_params)
    return merged


__all__ = [
    "WebTaskTemplate",
    "get_template",
    "list_templates",
    "merge_params",
]
