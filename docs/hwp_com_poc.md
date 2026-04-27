# HWP COM POC (B안 1단계 — 한컴 연결)

## 1. 목적

로컬 Windows PC 에서 **실제 한글(HWP) 데스크톱 앱**을 `win32com.client`
로 제어할 수 있는지 증명한다. 이번 단계는 다음 5가지만 검증한다.

1. 한글 프로그램 실행 (`HWPFrame.HwpObject` Dispatch)
2. HWP / HWPX 문서 열기
3. 본문 미리보기 읽기 (`GetTextFile`)
4. 테스트 문자열 삽입 (`HAction InsertText` + 폴백)
5. 다른 이름 저장 (`SaveAs`, 원본 overwrite 금지 기본)

Excel COM POC(`docs/excel_com_poc.md`) 와 완전히 독립되어 있으며, 기존
`excel_com_connector` / `local_agent` / `approval` / `spool` 구조는 건드리지
않는다. 서버 연동 / MCP 래핑 / action_registry 편입은 이번 단계의 범위
밖이다.

## 2. 전제 조건

- Windows 10/11 (데스크톱 PC — 서버 Windows 아님)
- **한글 데스크톱 설치** (한컴오피스 2018/2020/2022/NEO/Hancom Office)
  - 웹 한글 / viewer-only 버전은 COM 대상이 아님
  - Python 비트니스와 한글 비트니스가 달라도 COM 은 동작하지만, 같은
    비트니스(둘 다 64bit 권장) 에서 검증이 가장 단순하다
- Python 3.10+ (venv 권장)
- `pywin32` 설치 (Windows 에서만)
  ```
  pip install -r requirements.txt
  ```
  `requirements.txt` 는 `pywin32>=306; sys_platform == "win32"` 환경 마커로
  분리되어 있어 Linux 서버에서는 자동 스킵된다.
- **보안모듈 등록(선택)** — 한글 COM 자동화는 기본적으로 파일 경로 접근
  시 보안 확인 다이얼로그를 띄울 수 있다. 이를 회피하려면
  `RegisterModule("FilePathCheckDLL", "<모듈명>")` 를 호출해야 하며,
  해당 DLL 이 사전에 설치·등록되어 있어야 한다. 이 단계에서는 **호출
  성공/실패만** 결과에 기록하고, DLL 배포 자동화는 하지 않는다.

## 3. 실행 방법

### 3-1. 사용 가능 여부만 점검

```powershell
python -c "from agent.connectors import hwp_com_connector as c; import json; print(json.dumps(c.is_hwp_available(), ensure_ascii=False, indent=2))"
```

정상 출력 예:

```json
{
  "ok": true,
  "platform": "win32",
  "hwp_available": true,
  "version": "11.0.0.1",
  "security_module_registered": true
}
```

> `security_module_registered` 는 Dispatch 직후 `RegisterModule` 메서드가
> 호출 가능한 상태인지 간접적으로만 표시한다. **실제 DLL 등록 상태는
> 별도로 확인**해야 한다.

### 3-2. 전체 POC 실행 스크립트

> 절대경로만 허용된다. 샘플 hwp 파일은 **미리 준비**해야 한다
> (Excel POC 와 달리 HWP 는 openpyxl 상응 라이브러리가 없어 자동 생성을
> 하지 않는다). 한글 앱에서 "빈 문서 → 다른 이름 저장"으로 한 번
> 만들어두면 충분하다.

```powershell
# 기본 (visible=true, 원본 저장 없이 쓰기·미리보기만)
python scripts/hwp_com_poc.py --file-path C:\tmp\hwp_poc\sample.hwp

# 다른 이름 저장 (원본 overwrite 방지 — 권장)
python scripts/hwp_com_poc.py `
    --file-path C:\tmp\hwp_poc\sample.hwp `
    --save-as  C:\tmp\hwp_poc\out.hwp

# 한글 창을 띄우지 않고 실행
python scripts/hwp_com_poc.py --file-path C:\tmp\hwp_poc\sample.hwp --visible false

# 보안 모듈 등록을 함께 시도 (모듈명은 환경에 맞게 교체)
python scripts/hwp_com_poc.py `
    --file-path C:\tmp\hwp_poc\sample.hwp `
    --save-as  C:\tmp\hwp_poc\out.hwp `
    --register-module true `
    --module-name FilePathCheckerModule

# HWPX 확장자도 지원 (SaveAs 포맷은 확장자에서 유추)
python scripts/hwp_com_poc.py `
    --file-path C:\tmp\hwp_poc\sample.hwpx `
    --save-as  C:\tmp\hwp_poc\out.hwpx
```

스크립트는 표준 출력으로 JSON 한 덩어리를 찍는다:

```json
{
  "availability": {
    "ok": true, "platform": "win32", "hwp_available": true,
    "version": "11.0.0.1", "security_module_registered": true
  },
  "poc": {
    "ok": true,
    "file_path": "C:\\tmp\\hwp_poc\\sample.hwp",
    "visible": true,
    "save_as": "C:\\tmp\\hwp_poc\\out.hwp",
    "register_module": true,
    "module_name": "FilePathCheckerModule",
    "dispatched": true,
    "security_module": {"ok": true, "module_name": "FilePathCheckerModule", "return_value": 1},
    "document_opened": true,
    "text_preview": "문서 본문 앞부분...",
    "written_text": "POC_OK",
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
| 1 | availability 단계 실패 (Windows 아님 / pywin32 없음 / 한글 없음) |
| 2 | POC 도중 실패 (열기 / 읽기 / 쓰기 / 저장) |

## 4. 성공 기준

다음이 모두 관찰되어야 PASS 로 판정한다.

1. `availability.ok == true`
2. 한글 창이 잠깐 뜬다 (`--visible true` 기본값)
3. `poc.document_opened == true`
4. `poc.text_preview` 가 null 이 아니며 문서 본문 일부가 보인다
5. `poc.written_text == "POC_OK"` — HAction 또는 폴백 경로 중 하나로 삽입 성공
6. `poc.saved == true` 그리고 `--save-as` 경로가 실제로 생성됨
7. `poc.closed == true && poc.quit == true`
8. `poc.error == null`

`--register-module true` 를 줬다면 추가로:

9. `poc.security_module.ok == true` — RegisterModule 호출이 성공

## 5. 실패 시 점검 포인트

### 5-1. `hwp_com_not_supported`
- 비 Windows 환경에서 스크립트를 돌린 경우다. 대표 PC 에서 실행했는지
  확인.

### 5-2. `hwp_com_dispatch_failed`
- `win32com.client` import 실패 — pywin32 가 설치되지 않은 상태.
- 해결:
  ```
  pip install "pywin32>=306"
  python -m pywin32_postinstall -install    # 관리자 권한 필요
  ```

### 5-3. `hwp_app_not_found`
- `Dispatch("HWPFrame.HwpObject")` 자체가 실패.
- 점검:
  - 한글 데스크톱이 실제로 설치되어 있는가 (시작메뉴 / `Hwp.exe`
    경로 확인)
  - 한글을 **한 번도** 실행한 적 없는 계정이면 최초 activation 때문에
    COM 이 응답하지 않을 수 있음. 수동으로 한글을 한 번 띄워 최초
    실행 대화상자를 모두 닫고 재시도.
  - COM 등록이 깨진 경우 — 한컴오피스 복구(수리) 설치.
  - Python 비트니스 vs 한글 비트니스 — 같은 64bit 로 맞춰 재시도.

### 5-4. `hwp_security_module_required` *(보안 모듈 분기)*
- `--register-module true` 로 호출했으나 `RegisterModule` 이 실패한
  경우.
- 원인 후보:
  - `--module-name` 으로 넘긴 DLL 이 실제로 등록되어 있지 않음.
  - DLL 은 있으나 레지스트리 등록이 빠져 있음.
  - 한글 버전에 따라 `RegisterModule` 이 제공되지 않음.
- 해결:
  - 한컴에서 제공한 FilePathCheckerModule 계열 DLL 을 배포·등록
    (레지스트리 방식은 환경별로 다름. 본 POC 범위 밖).
  - 임시로는 `--register-module false` 로 두고, 열기/저장 시 뜨는
    보안 다이얼로그를 수동 승인하여 나머지 단계는 진행.

### 5-5. `hwp_document_open_failed`
- 파일 경로가 올바르지만 한글이 열지 못하는 경우.
- 점검:
  - 파일이 다른 한글 세션에 잠겨 있는가 (작업 관리자에서 `Hwp.exe`
    정리).
  - 파일이 암호 걸려 있지 않은가 / DRM 적용되어 있지 않은가.
  - OneDrive 동기화 중 파일이 일시적으로 잠겼을 가능성.
  - 보안모듈 미등록으로 인해 **경로 확인 다이얼로그가 떠서** Open 이
    블로킹되었을 가능성 — `--register-module true` 시도 또는 수동으로
    다이얼로그를 닫고 재시도.

### 5-6. `hwp_text_read_failed` / `hwp_text_write_failed`
- `GetTextFile("TEXT", "")` 또는 `HAction InsertText` 경로가 둘 다 실패.
- 점검:
  - 문서가 **편집 불가 모드**(보기 전용 / 서식 보호)인가.
  - 한글이 로드 직후 아직 활성 문서 프레임을 갖추지 못한 상태 — 수동
    으로 한 번 포커스를 주고 재시도.
  - 극히 오래된 한글 버전에서 `HAction` 인터페이스 이름이 다를 수
    있음. 커넥터는 `InsertText()` 폴백을 제공하지만 여전히 실패하면
    해당 버전은 지원 대상 밖.

### 5-7. `hwp_document_save_failed`
- 원본 경로가 읽기 전용이거나 OneDrive / SharePoint 경로에서 동시 편집
  중이어서 저장이 거부됨. 또는 DRM 적용 문서.
- 해결: `--save-as` 옵션으로 로컬 디스크(`C:\tmp` 등) 쓰기 권한이 있는
  경로로 지정.

### 5-8. `output_file_exists`
- `--save-as` 경로에 이미 파일이 존재하는 경우. 이번 단계는 기본
  **overwrite 금지**.
- 해결: 새로운 출력 경로 지정, 또는 기존 파일 삭제 후 재시도.

### 5-9. Hwp.exe / RPC 유령 프로세스가 남는다
- POC 스크립트가 비정상 종료되면 `Hwp.exe` 가 백그라운드에 남을 수
  있다. 작업 관리자에서 종료하거나:
  ```
  taskkill /F /IM Hwp.exe
  ```
- "RPC 서버를 사용할 수 없습니다" / "서버 실행에 실패했습니다" 류
  에러도 보통 유령 프로세스/프로필 문제다. 재부팅 후 재시도가 가장
  확실한 복구.

## 6. 자동화 테스트 범위

실제 한글을 띄우는 동작은 CI 에서 돌릴 수 없으므로, 자동화된 단위
테스트는 `agent/tests/test_hwp_com_connector_unit.py` 에서 mock 기반으로만
검증한다:

- 비 Windows → `hwp_com_not_supported`
- pywin32 미설치 → `hwp_com_dispatch_failed`
- Dispatch 실패 → `hwp_app_not_found`
- 경로 가드 (empty / relative / missing)
- `hwp_document_open_failed` / `hwp_text_read_failed` / `hwp_text_write_failed`
- `save_document_as` overwrite 금지, 확장자별 포맷(HWP/HWPX) 확인
- `register_file_path_check_module` 성공/실패/미지원 분기
- `run_basic_poc` 정상 흐름에서 Close / Quit 가 모두 호출됨
- 중간 실패 시에도 finally 로 Close / Quit 호출

실제 한글 동작 확인은 반드시 위 수동 절차(§3–§4) 로 검증한다.

## 7. 범위 밖 (다음 단계 이후)

- agent action_registry / policy 편입
- 서버에서 원격 실행을 위한 작업 큐 / RPC 래핑 (approval, spool 포함)
- 보안모듈 DLL 배포·레지스트리 등록 자동화
- 표/필드/블록 단위 편집, 수식·양식 자동화
- 장기 세션 유지, HWP 프로세스 풀 / 병렬 처리
- HWP ↔ PDF 변환, 인쇄 자동화
