"""Windows 로컬 Excel COM POC 실행기 (B안 1단계).

목적:
- Windows PC 에 설치된 Excel 데스크톱 앱을 ``win32com.client`` 로 실제 구동해
  파일 열기/셀 읽기/셀 쓰기/저장 4종 동작을 확인한다.
- 개발자가 손으로 돌려보는 수동 검증 스크립트이며, 서버 파이프라인 / agent
  action_registry 에 아직 연결되지 않는다.

사용 예:
    python scripts/excel_com_poc.py --file-path C:\\tmp\\sample.xlsx
    python scripts/excel_com_poc.py --file-path C:\\tmp\\sample.xlsx --save-as C:\\tmp\\out.xlsx
    python scripts/excel_com_poc.py --file-path C:\\tmp\\sample.xlsx --visible false

Exit code:
    0 — POC 성공
    1 — availability 단계 실패 (Windows 아님 / pywin32 미설치 / Excel 미설치)
    2 — POC 중 실패 (열기/읽기/쓰기/저장 단계)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _parse_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "y", "on")


def _ensure_sample_xlsx(path: Path) -> None:
    """샘플 xlsx 가 없으면 openpyxl 로 생성한다. A1='HELLO'."""
    if path.exists():
        return
    try:
        from openpyxl import Workbook
    except ImportError as e:  # 개발 환경에 openpyxl 은 이미 있어야 함
        raise SystemExit(
            f"openpyxl 이 필요합니다 (샘플 파일 생성용): {e}"
        )
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws["A1"] = "HELLO"
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(path))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Local Windows Excel COM POC"
    )
    parser.add_argument("--file-path", required=True, help="대상 xlsx 절대경로")
    parser.add_argument("--sheet-name", default="Sheet1")
    parser.add_argument(
        "--visible", default="true",
        help="Excel 창 표시 여부 (true/false, 기본 true)",
    )
    parser.add_argument(
        "--save-as", default=None,
        help="다른 이름 저장 절대경로. 지정 시 원본 overwrite 를 피한다.",
    )
    args = parser.parse_args(argv)

    # agent 패키지를 가져오기 위해 repo 루트 경로 보정
    repo_root = Path(__file__).resolve().parent.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    file_path = Path(args.file_path)
    if not file_path.is_absolute():
        print(json.dumps(
            {"ok": False, "error": "file_path_must_be_absolute",
             "file_path": str(file_path)},
            ensure_ascii=False, indent=2,
        ))
        return 2

    _ensure_sample_xlsx(file_path)

    from agent.connectors import excel_com_connector as com

    availability = com.is_excel_available()
    payload = {"availability": availability, "poc": None}

    if not availability.get("ok"):
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        return 1

    result = com.run_basic_poc(
        str(file_path),
        sheet_name=args.sheet_name,
        visible=_parse_bool(args.visible),
        save_as=args.save_as,
    )
    payload["poc"] = result
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
