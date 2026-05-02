"""비즈니스 애플리케이션 지도 (app_map) 모듈.

사용자 PC의 업무 프로그램을 메타데이터 기반으로 분류하고
AI 자동화 가능성을 판단하는 시스템.

- read-only 메타데이터 스캔만 수행
- 파일 내용 읽기 금지
- 프로그램 실행 금지
- 레지스트리 쓰기 금지
- 서버 전송 금지
"""
from .app_map_builder import (
    AppMap,
    AppMapBuilder,
    build_app_map,
    get_app_map_status,
)

__all__ = [
    "AppMap",
    "AppMapBuilder",
    "build_app_map",
    "get_app_map_status",
]
