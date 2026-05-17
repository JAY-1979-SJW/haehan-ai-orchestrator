"""External Sites Canonical Registry Package.

[ASSISTANT_EXTERNAL_SITE_MANAGEMENT_CANONICAL_REGISTRY_01]

비서앱이 다루는 모든 외부 사이트의 출입 동선, 로그인 정책,
자동화 가능 범위, 위험 게이트를 machine-readable하게 정의한다.

금지:
    실제 사이트 로그인 자동화 금지
    쿠키/토큰/비밀번호 저장 금지
    DNS 저장/변경 금지
    결제/제출/서명 자동 실행 금지
"""

PACKAGE = "external_sites"
VERSION = "1.0.0"
