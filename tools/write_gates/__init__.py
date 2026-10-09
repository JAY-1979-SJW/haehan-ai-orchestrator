"""Write 훅(prewrite_capability_check.py)이 사용하는 개별 검사 게이트 모음.

각 게이트 모듈은 `check(file_path: str, content: str) -> str | None`을 제공한다.
반환값이 문자열이면 차단 사유, None이면 통과.
"""
