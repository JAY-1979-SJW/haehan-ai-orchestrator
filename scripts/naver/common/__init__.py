"""네이버 공용 기반 — 하위 도구(blog·cafe·smartstore·mail·automation)가 함께 쓰는 모듈. 재수출 없음.

auth·auth_window_gate(로그인), live_safety(실사이트 안전), router_common(CLI 옵션 파싱),
calendar·mybox·place·talk·content(여러 도구가 쓰는 개인 서비스 래퍼).
scripts/naver/ 최상위(CLI 진입부·services)는 이 폴더와 하위 도구를 한 방향으로만 import 하고,
이 폴더는 scripts/naver/ 최상위나 하위 도구를 import 하지 않는다.
"""
