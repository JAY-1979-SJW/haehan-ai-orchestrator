"""페이지 구조 탐색 패키지.

모듈:
  - page_snapshot: 단일 페이지의 모든 프레임에서 links/inputs/buttons/forms/
                   headings 메타데이터 추출 + JSON 저장
  - tab_explorer: 탭 인터페이스(예: button.tab_link)를 순회하며 각 활성 패널의
                  콘텐츠를 추출 + JSON 저장

설계 원칙:
  - 페이지 상태 보존: 탐색 후 원래 탭/스크롤 위치로 복귀
  - 비파괴: 폼 전송/제출 액션 금지, 데이터 읽기 전용
"""
from . import page_snapshot, tab_explorer

__all__ = ["page_snapshot", "tab_explorer", "run"]


def run(task: str, args: list[str]) -> None:
    """CLI 디스패처. task: page | tabs"""
    match task:
        case "page":
            page_snapshot.run_cli(args)
        case "tabs":
            tab_explorer.run_cli(args)
        case _:
            print(f"  [오류] 알 수 없는 작업: {task}")
            print("  사용 가능: page | tabs")
