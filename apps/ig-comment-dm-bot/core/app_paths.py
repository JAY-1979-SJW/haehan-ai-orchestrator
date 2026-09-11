"""실행 방식(개발용 python 실행 vs PyInstaller onefile exe)에 관계없이 항상 같은
데이터 저장 위치를 돌려준다.

PyInstaller onefile 모드에서는 __file__ 이 매 실행마다 새로 만들어지는 임시 압축해제
폴더(sys._MEIPASS)를 가리키므로, 그 경로에 DB/설정을 저장하면 프로그램을 껐다 켤 때마다
데이터가 사라진다. 반드시 exe 파일이 실제로 위치한 폴더를 기준으로 삼아야 한다.
"""

from __future__ import annotations

import sys
from pathlib import Path


def get_data_dir() -> Path:
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).parent
    else:
        base = Path(__file__).parent.parent
    data_dir = base / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir
