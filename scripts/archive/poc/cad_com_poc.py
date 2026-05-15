"""Windows 로컬 AutoCAD COM POC 실행기 (B안 1단계).

목적:
- Windows PC 에 설치된 정식 AutoCAD 데스크톱 앱을 ``win32com.client`` 로
  실제 구동해 앱 실행 / DWG 열기 / 문서 정보 읽기 / 테스트 엔터티 추가 /
  다른 이름 저장 / 종료 가 가능한지 최소 범위로 확인한다.
- 개발자가 손으로 돌려보는 수동 검증 스크립트이며, 서버 파이프라인 /
  agent action_registry 에 아직 연결되지 않는다.

사용 예:
    python scripts/cad_com_poc.py --file-path C:\\tmp\\cad_poc\\sample.dwg
    python scripts/cad_com_poc.py --file-path C:\\tmp\\cad_poc\\sample.dwg ^
        --save-as C:\\tmp\\cad_poc\\out.dwg

Exit code:
    0 — POC 성공
    1 — availability 단계 실패 (Windows 아님 / pywin32 미설치 / AutoCAD 미설치)
    2 — POC 중 실패 (열기 / 정보 / 엔터티 추가 / 저장 단계)
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


def _parse_float(value, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Local Windows AutoCAD COM POC",
    )
    parser.add_argument(
        "--file-path", required=True, help="대상 DWG 절대경로",
    )
    parser.add_argument(
        "--visible", default="true",
        help="AutoCAD 창 표시 여부 (true/false, 기본 true)",
    )
    parser.add_argument(
        "--save-as", default=None,
        help="다른 이름 저장 절대경로. 지정 시 원본 overwrite 를 피한다.",
    )
    parser.add_argument(
        "--text", default="POC_OK",
        help="ModelSpace 에 추가할 테스트 문자열",
    )
    parser.add_argument(
        "--x", default="0.0", help="삽입 X 좌표 (double)",
    )
    parser.add_argument(
        "--y", default="0.0", help="삽입 Y 좌표 (double)",
    )
    parser.add_argument(
        "--z", default="0.0", help="삽입 Z 좌표 (double)",
    )
    parser.add_argument(
        "--height", default="2.5", help="텍스트 높이 (double, 기본 2.5)",
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

    from agent.connectors import cad_com_connector as com

    # 주의: is_cad_available() 을 POC 직전에 별도로 호출하면 AutoCAD 를 한 번
    # Dispatch+Quit 한 뒤 POC 가 재Dispatch 하게 되어, AutoCAD 가 잠시
    # RPC_E_SERVERFAULT 로 Documents.Open 을 거부할 수 있다. 여기서는
    # run_basic_poc 를 한 번만 호출하고, 그 결과에서 availability 정보를
    # 합성한다.
    result = com.run_basic_poc(
        str(file_path),
        visible=_parse_bool(args.visible),
        save_as=args.save_as,
        text=args.text or "POC_OK",
        x=_parse_float(args.x, 0.0),
        y=_parse_float(args.y, 0.0),
        z=_parse_float(args.z, 0.0),
        height=_parse_float(args.height, 2.5),
    )

    availability = {
        "ok": bool(result.get("dispatched")),
        "platform": sys.platform,
        "cad_available": bool(result.get("dispatched")),
        "prog_id": result.get("prog_id"),
        "version": result.get("version", ""),
        "product_name": result.get("product_name", ""),
        "lt_or_limited": bool(result.get("lt_or_limited")),
    }
    if not availability["ok"] and result.get("error"):
        availability["error"] = result["error"]

    payload = {"availability": availability, "poc": result}
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    if not availability["ok"]:
        return 1
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
