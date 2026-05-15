"""Windows 로컬 한글(HWP) COM POC 실행기 (B안 1단계).

목적:
- Windows PC 에 설치된 한글 데스크톱 앱을 ``win32com.client`` 로 실제 구동해
  앱 실행 / 문서 열기 / 텍스트 미리보기 / 텍스트 삽입 / 다른 이름 저장
  이 가능한지 최소 범위로 확인한다.
- 개발자가 손으로 돌려보는 수동 검증 스크립트이며, 서버 파이프라인 /
  agent action_registry 에 아직 연결되지 않는다.

사용 예:
    python scripts/hwp_com_poc.py --file-path C:\\tmp\\hwp_poc\\sample.hwp
    python scripts/hwp_com_poc.py --file-path C:\\tmp\\hwp_poc\\sample.hwp ^
        --save-as C:\\tmp\\hwp_poc\\out.hwp
    python scripts/hwp_com_poc.py --file-path C:\\tmp\\hwp_poc\\sample.hwp ^
        --register-module true --module-name FilePathCheckerModule

Exit code:
    0 — POC 성공
    1 — availability 단계 실패 (Windows 아님 / pywin32 미설치 / HWP 미설치)
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


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Local Windows HWP COM POC"
    )
    parser.add_argument(
        "--file-path", required=True, help="대상 hwp/hwpx 절대경로",
    )
    parser.add_argument(
        "--visible", default="true",
        help="한글 창 표시 여부 (true/false, 기본 true)",
    )
    parser.add_argument(
        "--save-as", default=None,
        help="다른 이름 저장 절대경로. 지정 시 원본 overwrite 를 피한다.",
    )
    parser.add_argument(
        "--write-text", default="POC_OK",
        help="문서에 삽입할 테스트 문자열 (빈 문자열이면 삽입 skip)",
    )
    parser.add_argument(
        "--register-module", default="false",
        help="RegisterModule(FilePathCheckDLL, ...) 호출 여부 (true/false)",
    )
    parser.add_argument(
        "--module-name", default=None,
        help="RegisterModule 에 넘길 모듈 이름 (미지정 시 기본값 사용)",
    )
    parser.add_argument(
        "--preview-chars", default="200",
        help="본문 미리보기 최대 글자수 (기본 200)",
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

    try:
        preview_chars = int(args.preview_chars)
    except (TypeError, ValueError):
        preview_chars = 200

    from agent.connectors import hwp_com_connector as com

    availability = com.is_hwp_available()
    payload = {"availability": availability, "poc": None}

    if not availability.get("ok"):
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        return 1

    result = com.run_basic_poc(
        str(file_path),
        visible=_parse_bool(args.visible),
        save_as=args.save_as,
        register_module=_parse_bool(args.register_module),
        module_name=args.module_name,
        write_text=args.write_text or "",
        preview_chars=preview_chars,
    )
    payload["poc"] = result
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
