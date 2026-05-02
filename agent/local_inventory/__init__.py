"""로컬 자산 인벤토리.

사용자 PC의 프로그램 설치 상태, 문서 폴더 메타데이터를
명시 동의 기반으로 로컬에서 인벤토리화.

- 파일 내용 읽기 안 함
- 서버 전송 안 함
- 로컬만 저장
"""
from agent.local_inventory.scanner import scan_local_inventory
from agent.local_inventory.inventory import LocalInventory

__all__ = [
    "scan_local_inventory",
    "LocalInventory",
]
