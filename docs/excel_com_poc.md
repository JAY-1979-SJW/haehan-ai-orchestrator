# Excel COM POC (B안 1단계)

## 1. 목적

로컬 Windows PC 에서 **실제 Microsoft Excel 데스크톱 앱**을 `win32com.client`
로 제어할 수 있는지 증명한다. 이번 단계는 다음 4가지 동작이 실제로
된다는 것만 검증한다.

1. Excel 프로그램 실행
2. xlsx 파일 열기
3. 셀 읽기 / 쓰기
4. 저장 (권장: 다른 이름 저장)

openpyxl 기반 기존 파이프라인(`excel_read_sheet` 외)은 전혀 건드리지
않으며, agent action_registry 에도 아직 편입하지 않는다. 서버/MCP/작업
큐 연결은 이 단계의 범위 밖이다.

## 2. 전제 조건

- Windows 10/11 (데스크톱 PC — 서버 Windows 가 아니어도 됨)
- Microsoft Excel **데스크톱** 설치 (Microsoft 365 또는 Office 2016+)
  - Excel Online / UWP 버전은 COM 대상이 아님
  - 32bit/64bit 모두 가능하나 Python 과 Office 의 bitness 가 달라도 COM 은 동작
- Python 3.10+ (venv 권장)
- `pywin32` 설치 (Windows 에서만)
  ```
  pip install -r requirements.txt
  ```
  `requirements.txt` 는 `pywin32>=306; sys_platform == "win32"` 환경 마커로
  분리되어 있어 Linux 서버에서는 자동 스킵된다.

## 3. 실행 방법

### 3-1. 사용 가능 여부만 점검

```powershell
python -c "from agent.connectors import excel_com_connector as c; import json; print(json.dumps(c.is_excel_available(), ensure_ascii=False, indent=2))"
```

정상 출력 예:

```json
{
  "ok": true,
  "platform": "win32",
  "excel_available": true,
  "version": "16.0"
}
```

### 3-2. 전체 POC 실행 스크립트

```powershell
# 기본 (visible=true, 샘플 파일 자동 생성, 원본에 저장)
python scripts/excel_com_poc.py --file-path C:\tmp\excel_poc\sample.xlsx

# 다른 이름 저장 (원본 overwrite 방지 — 권장)
python scripts/excel_com_poc.py `
    --file-path C:\tmp\excel_poc\sample.xlsx `
    --save-as C:\tmp\excel_poc\out.xlsx

# Excel 창을 띄우지 않고 실행
python scripts/excel_com_poc.py --file-path C:\tmp\excel_poc\sample.xlsx --visible false
```

스크립트는 표준 출력으로 JSON 한 덩어리를 찍는다:

```json
{
  "availability": {
    "ok": true, "platform": "win32", "excel_available": true, "version": "16.0"
  },
  "poc": {
    "ok": true,
    "file_path": "C:\\tmp\\excel_poc\\sample.xlsx",
    "sheet_name": "Sheet1",
    "excel_visible": true,
    "save_as": "C:\\tmp\\excel_poc\\out.xlsx",
    "dispatched": true,
    "workbook_opened": true,
    "read_cell": "A1",
    "read_value": "HELLO",
    "written_cell": "B2",
    "written_value": "POC_OK",
    "saved": true,
    "closed": true,
    "quit": true,
    "error": null
  }
}
```

Exit code:

| code | 의미 |
|------|------|
| 0 | POC 성공 |
| 1 | availability 단계 실패 (Windows 아님 / pywin32 없음 / Excel 없음) |
| 2 | POC 도중 실패 (열기 / 읽기 / 쓰기 / 저장) |

## 4. 성공 기준

다음이 모두 관찰되어야 PASS 로 판정한다.

1. `availability.ok == true`
2. Excel 창이 잠깐 뜬다 (`--visible true` 기본값)
3. `poc.read_value == "HELLO"` (샘플 자동 생성 시 A1)
4. `poc.written_value == "POC_OK"` 가 B2 에 반영
5. `poc.saved == true` 그리고 `save_as` 경로가 실제로 생성됨
6. `poc.closed == true && poc.quit == true`
7. `poc.error == null`

## 5. 실패 시 점검 포인트

### 5-1. `excel_com_not_supported`
- 비 Windows 환경에서 스크립트를 돌린 경우다. 대표 PC 에서 실행했는지
  확인.

### 5-2. `excel_com_dispatch_failed`
- `win32com.client` import 실패 — pywin32 가 설치되지 않은 상태.
- 해결:
  ```
  pip install "pywin32>=306"
  python -m pywin32_postinstall -install    # 관리자 권한 필요
  ```

### 5-3. `excel_app_not_found`
- `Dispatch("Excel.Application")` 자체가 실패.
- 점검:
  - Excel 데스크톱이 실제로 설치되어 있는가 (`where excel` / 시작메뉴)
  - Office bitness 와 Python bitness 가 달라 Dispatch 가 안 되는 것은
    아닌가 (32bit Python + 64bit Office 조합에서 드물게 문제).
    같은 bitness 를 권장.
  - COM 등록이 깨졌는가 — Office 복구(Repair) 실행.
  - Office 를 **한 번도** 실행한 적 없는 계정이면 최초 activation
    대화상자 때문에 COM 이 응답하지 않을 수 있음. 수동으로 Excel 한
    번 띄워 activation 완료.

### 5-4. `workbook_open_failed`
- 파일 경로가 올바르지만 Excel 이 열지 못하는 경우.
- 점검:
  - 파일이 다른 Excel 세션에 잠겨 있는가 (작업 관리자에서 EXCEL.EXE
    정리).
  - 파일이 암호 걸려 있지 않은가.
  - OneDrive 동기화 중 파일이 일시적으로 잠겼을 가능성.

### 5-5. `cell_read_failed` / `cell_write_failed`
- 셀 참조가 잘못되었거나 시트 보호가 걸려있는 경우.
- 점검:
  - `--sheet-name` 으로 전달한 이름이 실제 탭 이름과 정확히 일치하는가.
  - 해당 시트가 "시트 보호" 로 잠겨 있지 않은가.

### 5-6. `workbook_save_failed`
- 원본 경로가 읽기 전용이거나 OneDrive / SharePoint 경로에서 동시 편집
  중이어서 저장이 거부됨.
- 해결: `--save-as` 옵션으로 로컬 디스크(C:\tmp 등) 쓰기 권한이 있는
  경로로 지정.

### 5-7. Excel.exe 유령 프로세스가 남는다
- POC 스크립트가 비정상 종료되면 EXCEL.EXE 가 백그라운드에 남을 수
  있다. 작업 관리자에서 종료하거나:
  ```
  taskkill /F /IM EXCEL.EXE
  ```

## 6. 자동화 테스트 범위

실제 Excel 을 띄우는 동작은 CI 에서 돌릴 수 없으므로, 자동화된 단위
테스트는 `agent/tests/test_excel_com_connector_unit.py` 에서 mock
기반으로만 검증한다:

- 비 Windows → `excel_com_not_supported`
- pywin32 미설치 → `excel_com_dispatch_failed`
- Dispatch 실패 → `excel_app_not_found`
- 경로 가드 (empty / relative / missing)
- `workbook_open_failed`, `cell_read_failed`, `cell_write_failed`, `workbook_save_failed`
- `run_basic_poc` 정상 흐름에서 Save / Close / Quit 가 모두 호출됨
- 중간 실패 시에도 finally 로 Close / Quit 호출

실제 Excel 동작 확인은 반드시 위 수동 절차(§3–§4) 로 검증한다.

## 7. 범위 밖 (다음 단계 이후)

- agent action_registry / policy 편입
- 서버에서 원격 실행을 위한 작업 큐 / RPC 래핑
- 차트/수식/서식 복사, 복수 Workbook 병렬 실행
- 장기 세션 유지, Excel 프로세스 풀
