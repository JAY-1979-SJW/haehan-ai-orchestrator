# CAD COM POC (B안 1단계 — AutoCAD 연결)

## 1. 목적

로컬 Windows PC 에서 **실제 AutoCAD 데스크톱 앱**을 `win32com.client`
로 제어할 수 있는지 증명한다. 이번 단계는 다음 6가지만 검증한다.

1. AutoCAD 프로그램 실행 (`AutoCAD.Application.XX.X` → 폴백 `AutoCAD.Application`)
2. DWG 문서 열기 (`app.Documents.Open`)
3. 문서 정보 읽기 (`Name`, `FullName`, `ModelSpace.Count`, `ActiveLayout.Name`)
4. ModelSpace 에 테스트 텍스트 1개 추가 (`ModelSpace.AddText`)
5. 다른 이름 저장 (`doc.SaveAs`, 원본 overwrite 금지 기본)
6. 문서/앱 종료 (`doc.Close`, `app.Quit`)

Excel COM POC (`docs/excel_com_poc.md`), HWP COM POC (`docs/hwp_com_poc.md`)
와 완전히 독립되어 있으며, 기존 `excel_com_connector` / `hwp_com_connector` /
`local_agent` / `approval` / `spool` / `action_registry` 구조는 건드리지
않는다. 서버 연동 / MCP 래핑 / action_registry 편입은 이번 단계의 범위
밖이다.

## 2. 전제 조건

- Windows 10/11 (데스크톱 PC — 서버 Windows 아님)
- **정식 AutoCAD 데스크톱 설치** (Autodesk AutoCAD 2020 이상 권장)
  - **AutoCAD LT / Mac 은 이번 단계 지원 대상이 아니다.** LT 는 ActiveX
    인터페이스가 차단되어 있어 `Documents.Open` 이후 ModelSpace 편집이
    불가능하다. 커넥터가 `ProductName` 을 점검해 `lt_or_limited` 플래그
    로 노출만 하고, 실행은 일반 AutoCAD 기준으로 동작한다.
  - AutoCAD 를 계정에 연결한 뒤 **최소 한 번은 수동으로 띄워** 라이선스
    activation / 시작 프롬프트를 모두 닫아야 COM 자동화가 정상 응답한다.
  - Python 비트니스와 AutoCAD 비트니스가 달라도 COM 은 동작하지만, 같은
    비트니스(둘 다 64bit 권장) 에서 검증이 가장 단순하다.
- Python 3.10+ (venv 권장)
- `pywin32` 설치 (Windows 에서만)
  ```
  pip install -r requirements.txt
  ```
  `requirements.txt` 는 `pywin32>=306; sys_platform == "win32"` 환경 마커로
  분리되어 있어 Linux 서버에서는 자동 스킵된다.
- 테스트용 DWG 파일 하나를 미리 준비 — AutoCAD 에서 빈 도면을 열어
  `C:\tmp\cad_poc\sample.dwg` 로 저장해두면 충분하다.

## 3. 실행 방법

### 3-1. 사용 가능 여부만 점검

```powershell
python -c "from agent.connectors import cad_com_connector as c; import json; print(json.dumps(c.is_cad_available(), ensure_ascii=False, indent=2))"
```

정상 출력 예:

```json
{
  "ok": true,
  "platform": "win32",
  "cad_available": true,
  "prog_id": "AutoCAD.Application.24.3",
  "version": "24.3",
  "product_name": "AutoCAD",
  "lt_or_limited": false
}
```

> `prog_id` 는 커넥터가 후보 ProgID 를 순차 시도해 **최초 성공한** 값을
> 돌려준다. 설치된 버전에 따라 `AutoCAD.Application.25.0`,
> `AutoCAD.Application.24.3`, ..., `AutoCAD.Application` 등으로 달라진다.

### 3-2. 전체 POC 실행 스크립트

> 절대경로만 허용된다. 샘플 DWG 는 **미리 준비**해야 한다.

```powershell
# 기본 (visible=true, 원본 저장 없이 텍스트만 추가)
python scripts/cad_com_poc.py --file-path C:\tmp\cad_poc\sample.dwg

# 다른 이름 저장 (원본 overwrite 방지 — 권장)
python scripts/cad_com_poc.py `
    --file-path C:\tmp\cad_poc\sample.dwg `
    --save-as  C:\tmp\cad_poc\out.dwg

# AutoCAD 창을 띄우지 않고 실행 (GUI 없이 가능한지 확인용)
python scripts/cad_com_poc.py `
    --file-path C:\tmp\cad_poc\sample.dwg `
    --save-as  C:\tmp\cad_poc\out.dwg `
    --visible false

# 삽입 좌표 / 높이 지정
python scripts/cad_com_poc.py `
    --file-path C:\tmp\cad_poc\sample.dwg `
    --save-as  C:\tmp\cad_poc\out.dwg `
    --text "POC_OK" --x 10 --y 20 --z 0 --height 5
```

스크립트는 표준 출력으로 JSON 한 덩어리를 찍는다:

```json
{
  "availability": {
    "ok": true, "platform": "win32", "cad_available": true,
    "prog_id": "AutoCAD.Application.24.3", "version": "24.3",
    "product_name": "AutoCAD", "lt_or_limited": false
  },
  "poc": {
    "ok": true,
    "file_path": "C:\\tmp\\cad_poc\\sample.dwg",
    "visible": true,
    "save_as": "C:\\tmp\\cad_poc\\out.dwg",
    "dispatched": true,
    "document_opened": true,
    "document_info": {
      "name": "sample.dwg",
      "full_name": "C:\\tmp\\cad_poc\\sample.dwg",
      "model_space_count": 12,
      "active_layout": "Model"
    },
    "added_entity": {
      "type": "Text",
      "text": "POC_OK",
      "handle": "2A7",
      "object_name": "AcDbText"
    },
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
| 1 | availability 단계 실패 (Windows 아님 / pywin32 없음 / AutoCAD 없음) |
| 2 | POC 도중 실패 (열기 / 정보 / 엔터티 추가 / 저장) |

## 4. 성공 기준

다음이 모두 관찰되어야 PASS 로 판정한다.

1. `availability.ok == true` 그리고 `lt_or_limited == false`
2. AutoCAD 창이 잠깐 뜬다 (`--visible true` 기본값)
3. `poc.dispatched == true`
4. `poc.document_opened == true`
5. `poc.document_info.name` 이 대상 DWG 의 파일명과 일치
6. `poc.added_entity.type` 이 `Text` (또는 MText) 이고 `text == "POC_OK"`
7. `poc.saved == true` 그리고 `--save-as` 경로가 실제로 생성됨
8. `poc.closed == true && poc.quit == true`
9. `poc.error == null`
10. `out.dwg` 를 AutoCAD 로 다시 열어 **POC_OK 텍스트가 시각적으로 존재**
11. 원본 `sample.dwg` 는 **무변경** (`--save-as` 를 주었을 때)

## 5. 실패 시 점검 포인트

### 5-1. `cad_com_not_supported`
- 비 Windows 환경에서 스크립트를 돌린 경우다. 대표 PC 에서 실행했는지
  확인.

### 5-2. `cad_com_dispatch_failed`
- `win32com.client` import 실패 — pywin32 가 설치되지 않은 상태.
- 해결:
  ```
  pip install "pywin32>=306"
  python -m pywin32_postinstall -install    # 관리자 권한 필요
  ```

### 5-3. `cad_app_not_found`
- 모든 후보 ProgID 에 대한 `Dispatch` 가 실패.
- 점검:
  - AutoCAD 가 실제로 설치되어 있는가 (시작메뉴, `acad.exe` 경로).
  - AutoCAD 를 **한 번도** 실행한 적 없는 계정이면 최초 라이선스
    activation 때문에 COM 이 응답하지 않을 수 있음. 수동으로 AutoCAD 를
    한 번 띄워 시작화면을 닫고 재시도.
  - 설치된 제품이 **AutoCAD LT** 면 여기서 실패하거나, Dispatch 는
    성공하되 이후 `ModelSpace` 접근에서 실패한다. `availability.lt_or_limited`
    값으로 확인.
  - COM 등록이 깨진 경우 — AutoCAD 설치 관리자의 "복구(Repair)" 를 수행.
  - Python 비트니스 vs AutoCAD 비트니스 — 같은 64bit 로 맞춰 재시도.

### 5-4. `cad_document_open_failed`
- ProgID 는 뜨지만 `Documents.Open` 이 실패.
- 점검:
  - 파일이 다른 AutoCAD 세션에 잠겨 있는가 (작업 관리자에서 `acad.exe`
    정리).
  - OneDrive 동기화 중 파일이 일시적으로 잠겼을 가능성 — `C:\tmp` 등
    **로컬 디스크 경로**로 샘플을 옮겨 재시도.
  - 파일이 **상위 버전** DWG 포맷이어서 현재 설치된 AutoCAD 가 못 여는
    경우 — DWG TrueView 로 다운그레이드하거나, 현재 AutoCAD 에서 다른
    이름 저장으로 호환 포맷 생성.
  - 파일이 손상되었을 가능성 — 같은 샘플이 AutoCAD UI 에서 정상적으로
    열리는지 먼저 확인.

### 5-5. `cad_document_info_failed`
- 문서는 열렸지만 `ModelSpace` / `ActiveLayout` 접근이 실패한 경우.
- 대표 원인:
  - 설치된 제품이 **AutoCAD LT** — ActiveX 가 차단.
  - 문서가 아직 완전히 로드되지 않은 상태에서 COM 이 읽기를 시도 — 
    재시도하거나, 수동으로 한 번 포커스를 준 뒤 재실행.

### 5-6. `cad_entity_add_failed`
- `ModelSpace.AddText` 자체가 실패.
- 점검:
  - 문서가 **편집 불가 모드**(읽기 전용 / 외부 참조만) 인가.
  - LT / 뷰어 모드인가.
  - 좌표값이 잘못 전달되었는가 (스크립트는 float 로 파싱하지만, 극단
    값이나 NaN 은 COM 이 거부).
  - height 가 0 또는 음수로 넘어갔는가 — 커넥터 자체 가드가 0 이하를
    차단하므로 스크립트에서 음수가 넘어가면 여기서 먼저 실패.

### 5-7. `cad_document_save_failed`
- `SaveAs` / `Save` 가 실패.
- 점검:
  - 출력 경로 상위 디렉토리에 쓰기 권한이 있는가.
  - 대상 파일이 AutoCAD 의 다른 세션에 잠겨 있는가.
  - OneDrive / SharePoint 경로에서 동시 편집 중이어서 저장이 거부됨 —
    `C:\tmp\cad_poc\` 같은 **순수 로컬 경로**로 지정.
  - 파일시스템이 대소문자/유니코드 이슈를 일으키는 경로인가.

### 5-8. `output_file_exists`
- `--save-as` 경로에 이미 파일이 존재하는 경우. 이번 단계는 기본
  **overwrite 금지**.
- 해결: 새로운 출력 경로 지정, 또는 기존 파일 삭제 후 재시도.

### 5-9. acad.exe 유령 프로세스가 남는다
- POC 스크립트가 비정상 종료되면 `acad.exe` 가 백그라운드에 남을 수
  있다. 작업 관리자에서 종료하거나:
  ```
  taskkill /F /IM acad.exe
  ```
- "RPC 서버를 사용할 수 없습니다" / "서버 실행에 실패했습니다" 류
  에러도 보통 유령 프로세스/프로필 문제다. 재부팅 후 재시도가 가장
  확실한 복구.

## 6. 수동 검증 절차

1. AutoCAD 에서 빈 도면 하나를 만들어 `C:\tmp\cad_poc\sample.dwg` 로 저장
   (이 파일이 POC 의 입력 원본이 된다).
2. `is_cad_available()` 결과에서 `ok=true` 와 `lt_or_limited=false` 확인.
3. 아래 명령을 실행.
   ```powershell
   python scripts/cad_com_poc.py `
       --file-path C:\tmp\cad_poc\sample.dwg `
       --save-as  C:\tmp\cad_poc\out.dwg
   ```
4. JSON 출력에서 모두 확인.
   - `dispatched == true`
   - `document_opened == true`
   - `added_entity.type` 이 `Text` 또는 `MText`
   - `saved == true`
   - `closed == true`
   - `quit == true`
   - `error == null`
5. AutoCAD 로 `out.dwg` 를 열어 `POC_OK` 텍스트가 삽입되었는지 시각 확인.
6. 원본 `sample.dwg` 를 열어 **텍스트가 삽입되지 않았음**(=무변경) 을 확인.

## 7. 자동화 테스트 범위

실제 AutoCAD 를 띄우는 동작은 CI 에서 돌릴 수 없으므로, 자동화된 단위
테스트는 `agent/tests/test_cad_com_connector_unit.py` 에서 mock 기반으로만
검증한다:

- 비 Windows → `cad_com_not_supported`
- pywin32 미설치 → `cad_com_dispatch_failed`
- 모든 ProgID Dispatch 실패 → `cad_app_not_found`
- 버전 ProgID 실패 → unversioned ProgID 폴백 성공
- 경로 가드 (empty / relative / missing)
- `cad_document_open_failed` / `cad_document_info_failed` /
  `cad_entity_add_failed` / `cad_document_save_failed`
- `save_document_as` overwrite 금지 기본
- `run_basic_poc` 정상 흐름에서 Close / Quit 가 모두 호출됨
- 중간 실패 시에도 finally 로 Close / Quit 호출

실제 AutoCAD 동작 확인은 반드시 위 수동 절차(§3–§6) 로 검증한다.

## 8. 범위 밖 (다음 단계 이후)

- agent action_registry / policy 편입
- approval / result_spool / local_agent 파이프라인 편입
- 서버에서 원격 실행을 위한 작업 큐 / RPC 래핑
- MCP 서버 래핑
- AutoCAD LT 지원 (본 커넥터 구조로는 불가 — 별도 경로 필요)
- 블록 / 레이어 / 속성 편집, DXF / DWG 버전 변환
- 장기 세션 유지, AutoCAD 프로세스 풀 / 병렬 처리
- Plot / 인쇄 자동화, DWG ↔ PDF 변환
- 파괴적 편집(블록 explode, purge 등) 및 임의 COM command 전달
