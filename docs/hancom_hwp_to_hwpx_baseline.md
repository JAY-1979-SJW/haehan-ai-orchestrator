# 한컴 HWP → HWPX 변환 Worker - 기준선 사양

**Date:** 2026-05-02  
**Status:** 기준선 확정 + 최종 검증 완료  
**Testing:** 36개 테스트 모두 통과 (경로 11 + HWPX 검증 7 + Workflow 4 + Handler 5 + COM Smoke 9)

---

## 개요

한컴 HwpObject 자동화를 사용하여 HWP 파일을 HWPX (ODP 호환 XML 패키지)로 변환하는 worker.

**핵심 원칙:** 
- 공식 보안모듈 RegisterModule을 통한 보안 팝업 처리
- 원본 HWP 파일 보호 (read-only + SaveAs 기반)
- 변환 결과 HWPX는 이후 XML 분석/감리서식 자동작성 worker의 입력

---

## 모듈 구조

### 1. agent/hancom/hwp/security_module.py
보안모듈 레지스트리 확인 및 공식 등록.

**함수:**
- `check_security_module_registered()`: 보안모듈 등록 상태 확인
- `check_module_registry()`: Windows 레지스트리 fallback 확인
- `register_security_module_if_available()`: 공식 보안모듈 등록 (선택)
- `get_security_module_status()`: 상태 조회

**정책:**
- 보안모듈 미등록 시 자동 우회 금지 → error_code 반환
- 팝업 자동 클릭 금지 → 공식 방식만 허용

### 2. agent/hancom/hwp/automation_connector.py
HwpObject COM 객체 생성 및 저수준 파일 조작.

**함수:**
- `check_hancom_available()`: 한컴 COM 가용성 확인
- `create_hwp_object(visible=False)`: HwpObject 생성
- `open_hwp_file(hwp, path, read_only=True)`: 파일 열기
- `close_hwp_file(hwp, save_changes=False)`: 파일 닫기
- `save_hwp_as(hwp, output_path, file_format="HWPX")`: SaveAs 또는 FileSaveAs_S
- `quit_hwp(hwp)`: HwpObject 종료

**원본 보호:**
- read_only=True로 항상 열기 (원본 수정 방지)
- SaveAs만 사용 (원본 저장 금지)

### 3. agent/hancom/hwp/path_policy.py
파일 경로 검증 및 원본 보호.

**함수:**
- `validate_input_hwp_path(path)`: 입력 HWP 경로 검증
  - 절대 경로 확인
  - .hwp 확장자 검증
  - 파일 존재 + 읽기 가능 확인
- `validate_output_hwpx_path(path)`: 출력 HWPX 경로 검증
  - .hwpx 확장자 강제
  - 부모 디렉토리 쓰기 가능 확인
- `check_original_overwrite(input, output)`: 원본 덮어쓰기 방지
- `validate_conversion_paths(input, output)`: 종합 검증

**정책:**
- 입력 == 출력 이면 거부 (OUTPUT_SAME_AS_INPUT)
- 상대 경로 거부 (절대 경로만 허용)

### 4. agent/hancom/hwp/converter.py
HWP → HWPX 변환 엔진.

**함수:**
- `convert_hwp_to_hwpx(input, output, visible=False)`: 변환 실행
  1. 경로 검증
  2. 보안모듈 확인 (미등록 시 중단)
  3. HwpObject 생성
  4. HWP 읽기 전용으로 열기
  5. HWPX로 SaveAs
  6. 출력 파일 검증

- `get_conversion_status(path)`: 변환 결과 상태 조회

**반환값:**
```python
{
    "success": bool,
    "input_path": str | None,
    "output_path": str | None,
    "output_size": int | None,
    "error": str | None,  # 에러 코드
}
```

### 5. agent/hancom/hwpx/package_validator.py
HWPX ZIP 패키지 구조 검증.

**함수:**
- `validate_hwpx_package(path)`: ZIP 및 내부 구조 검증
- `get_hwpx_structure(path)`: 내부 구조 분석
- `extract_hwpx_metadata(path)`: 메타데이터 추출

**검증 규칙:**
- ZIP 파일 형식 확인 (magic number: PK..)
- Contents/ 디렉토리 필수
- content.hpf 또는 섹션 XML (.hml, .xml) 필수
- 섹션 최소 1개 이상 필수

### 6. agent/hancom/hwp/workflows.py
Orchestration 레이어.

**함수:**
- `convert_hwp_to_hwpx_copy(params)`: 전체 워크플로우 실행
  - 경로 검증
  - 보안모듈 확인
  - 변환 실행
  - 결과 검증

**파라미터:**
```python
{
    "input_path": str,       # 입력 HWP 경로 (절대, .hwp)
    "output_path": str,      # 출력 HWPX 경로 (절대, .hwpx)
    "visible": bool,         # UI 표시 여부 (선택, 기본값: False)
}
```

**반환값:**
```python
{
    "success": bool,
    "input_path": str | None,
    "output_path": str | None,
    "output_size": int | None,
    "hwpx_valid": bool,
    "hwpx_file_count": int,
    "hwpx_sections": int,
    "error": str | None,
}
```

### 7. 액션 레지스트리 및 Task Executor 통합
Task 디스패치 시스템에 완전 통합됨.

**agent/action_registry.py:**
- `CATEGORY_HANCOM` 상수 정의
- `"hancom.convert_hwp_to_hwpx_copy"` 등록:
  - category: `CATEGORY_HANCOM`
  - risk_level: `RISK_MEDIUM`
  - requires_file_path: `True`
  - requires_save_as: `True`
  - read_only: `False` (변환 출력을 위해)

**agent/task_executor.py:**
- `_run_hancom_convert_hwp_to_hwpx_copy(task)` 핸들러
  - 입력: `input_path` 또는 `file_path` (별칭)
  - 입력: `output_path` 또는 `save_as` (별칭)
  - 선택: `visible` (기본값: False)
  - 에러: `INPUT_OUTPUT_PATH_REQUIRED` (경로 누락)
  - 반환: 표준 result dict (ok, error, data)

---

## 에러 코드

### 경로 검증
- `PATH_REQUIRED`: 경로 필수
- `ABSOLUTE_PATH_REQUIRED`: 절대 경로 필수
- `INPUT_FILE_NOT_FOUND`: 입력 파일 없음
- `INPUT_NOT_HWP_FILE`: 입력 .hwp 아님
- `OUTPUT_PATH_REQUIRED`: 출력 경로 필수
- `OUTPUT_MUST_BE_HWPX`: 출력 .hwpx 아님
- `OUTPUT_SAME_AS_INPUT`: 입력과 같은 경로
- `OUTPUT_DIR_NOT_FOUND`: 출력 디렉토리 없음
- `OUTPUT_DIR_NOT_WRITABLE`: 출력 디렉토리 쓰기 불가

### 보안모듈
- `MODULE_NOT_REGISTERED`: 보안모듈 미등록 (중단, 우회 금지)
- `SECURITY_MODULE_NOT_AVAILABLE`: 보안모듈 불가
- `MODULE_CHECK_FAILED`: 확인 실패

### 한컴 COM
- `HANCOM_NOT_INSTALLED`: 한컴 미설치
- `WIN32COM_NOT_AVAILABLE`: win32com 불가
- `FILE_OPEN_FAILED`: 파일 열기 실패
- `FILE_SAVE_AS_FAILED`: SaveAs 실패
- `FILE_CLOSE_FAILED`: 파일 닫기 실패
- `QUIT_FAILED`: 종료 실패

### 변환 결과
- `OUTPUT_FILE_NOT_CREATED`: 출력 파일 미생성
- `OUTPUT_FILE_EMPTY`: 출력 파일 비어있음

### HWPX 검증
- `NOT_A_ZIP_FILE`: ZIP 아님
- `CONTENTS_DIR_NOT_FOUND`: Contents 디렉토리 없음
- `CONTENT_FILE_NOT_FOUND`: content.hpf 또는 섹션 없음
- `NO_SECTIONS_FOUND`: 섹션 없음
- `HWPX_VALIDATION_FAILED:...`: 검증 실패

---

## 사용 예시

### Python
```python
from agent.hancom.hwp.workflows import convert_hwp_to_hwpx_copy

result = convert_hwp_to_hwpx_copy({
    "input_path": "C:\\Documents\\report.hwp",
    "output_path": "C:\\Output\\report.hwpx",
    "visible": False,
})

if result["success"]:
    print(f"변환 성공: {result['output_path']}")
    print(f"파일 크기: {result['output_size']} bytes")
    print(f"섹션: {result['hwpx_sections']} 개")
else:
    print(f"변환 실패: {result['error']}")
```

---

## 제약사항 및 알려진 한계

### 제약사항
1. **보안모듈 필수**: 보안모듈이 등록되어 있어야 함 (미등록 시 error 반환)
2. **팝업 우회 금지**: 보안 팝업은 공식 방식(RegisterModule)으로만 처리
3. **원본 보호**: 입력 == 출력 불가 (항상 copy-based)
4. **읽기 전용 열기**: HWP는 read_only=True로 항상 열기

### 한계
1. **비상업 문제**: 한컴 HwpObject 자동화는 상업적 사용 시 별도 라이선스 필요
   - 한컴 개발자 문서: "상업적 솔루션 사용 시 별도 승인 필요"
   - https://developers.hancom.com/ 참조
2. **COM 기반**: Windows 전용 (COM)
3. **VBA 미지원**: 매크로/VBA는 SaveCopyAs에서 미보존 (기본 제약)
4. **포맷 호환성**: HWPX는 ODP 호환이지만, 한컴 고유 기능은 제한
5. **성능**: 대량 파일 변환 시 성능 최적화 필요

---

## 테스트 기준선

**총 36개 테스트 통과:**

### 경로 검증 (11개) — test_hancom_hwp_path_policy.py
- 유효한 HWP 경로 검증 ✅
- 존재하지 않는 파일 ✅
- 잘못된 확장자 ✅
- 상대 경로 거부 ✅
- 유효한 HWPX 경로 검증 ✅
- HWPX 확장자 강제 ✅
- 원본 덮어쓰기 방지 (같은 경로) ✅
- 다른 경로는 안전함 ✅
- 종합 경로 검증 성공 ✅
- 종합 경로 검증 실패 (입력 없음) ✅
- 경로 정보 조회 ✅

### HWPX 패키지 검증 (7개) — test_hancom_hwpx_package_validator.py
- 유효한 HWPX 검증 ✅
- 파일 없음 ✅
- ZIP 아님 ✅
- Contents 없음 ✅
- 섹션 없음 ✅
- 구조 분석 ✅
- 메타데이터 추출 ✅

### Workflow 통합 (4개) — test_hancom_hwp_workflows.py
- 변환 성공 (mock) ✅
- 변환 실패 ✅
- HWPX 검증 실패 ✅
- 필수 파라미터 누락 ✅

### Task Executor 핸들러 (5개) — test_task_executor_unit.py
- 입력 경로 누락 시 오류 ✅
- 출력 경로 누락 시 오류 ✅
- 워크플로우로 위임 ✅
- file_path/save_as 별칭 지원 ✅
- 에러 전파 ✅

### 실제 COM Smoke 테스트 (9개) — test_hancom_hwp_com_smoke.py
- 한컴 COM 가용성 확인 ✅
- HwpObject 생성 ✅
- 보안모듈 상태 조회 ✅
- HWP 파일 읽기 전용 열기 ✅
- HWP → HWPX 변환 (읽기 전용) ✅
- HWPX ZIP 구조 검증 ✅
- 원본 HWP 파일 무수정 확인 ✅
- Workflow 모듈을 통한 변환 ✅
- 실제 COM 객체 생성/삭제 ✅

**Smoke 테스트 실행:**
```bash
# 한컴 설치 필수, 보안모듈 등록 권장
pytest agent/tests/test_hancom_hwp_com_smoke.py -v
```

---

## 보안팝업 제거 (RegisterModule)

### 문제
HWP 파일을 Open할 때 한컴 보안 승인 팝업이 표시됨:
```
"한글을 이용하여 위 파일에 접근하려는 시도가 감지되었습니다.
[접근 허용] [모두 허용] [허용 안 함] [모두 안 함]"
```

### 원인
한컴 자동화 API의 보안 정책으로, HwpObject.Open() 호출 시 사용자 승인 필요.

### 해결: RegisterModule 방식 (공식)

**금지되는 방식:**
- ❌ 팝업 자동 클릭 (UIAutomation, 키 입력)
- ❌ 보안 우회 (registry 우회, 환경변수 조작)

**허용되는 방식:**
- ✅ 공식 보안모듈 + RegisterModule API

### 구현 순서

```python
# 1단계: 보안모듈 registry 확인
module_info = security_module.get_security_module_details("FilePathCheckerModuleExample")
if not module_info["registered"]:
    return "HANCOM_SECURITY_MODULE_NOT_REGISTERED"  # SETUP_REQUIRED

# 2단계: RegisterModule 호출 (Open 직전)
success, error = security_module.register_module_before_open(
    hwp,
    module_name="FilePathCheckerModuleExample"
)
if not success:
    return error  # HANCOM_REGISTER_MODULE_FAILED

# 3단계: 안전하게 Open 호출
hwp.Open(file_path, 0, '')  # 팝업 없음
```

### Registry 경로

```
HKEY_CURRENT_USER\Software\HNC\HwpAutomation\Modules
  ├─ FilePathCheckerModuleExample: "C:\Program Files\...\module.dll"
  └─ (다른 모듈들...)

또는

HKEY_CURRENT_USER\Software\Hnc\HwpAutomation\Modules  # 대소문자 변형
```

### 필수 조건

1. **보안모듈 등록 필수**
   - Windows registry의 HwpAutomation\Modules에 등록되어야 함
   - DLL 파일이 실제로 존재해야 함
   - 미등록이면 `SETUP_REQUIRED` 반환

2. **module_name 일치**
   - RegisterModule의 매개변수는 registry 이름과 정확히 일치해야 함
   - 일반적으로: `FilePathCheckerModuleExample`

3. **호출 순서 준수**
   - RegisterModule → Open (반드시 이 순서)
   - Open 전에 RegisterModule 호출하지 않으면 팝업 발생

### 설정값

```python
# 우선순위:
# 1. task params.module_name
# 2. 환경변수 HANCOM_SECURITY_MODULE_NAME
# 3. 기본값 FilePathCheckerModuleExample

params = {
    "input_path": "input.hwp",
    "output_path": "output.hwpx",
    "module_name": "FilePathCheckerModuleExample",  # 선택사항
}
result = workflows.convert_hwp_to_hwpx_copy(params)
```

### 에러 코드

| 코드 | 의미 | 해결 |
|------|------|------|
| `HANCOM_SECURITY_MODULE_NOT_REGISTERED` | 보안모듈 미등록 | `python scripts/setup_hancom_security_module.py`로 등록 |
| `DLL_PATH_NOT_FOUND` | DLL 자동 탐색 실패 | `--dll-path` 옵션으로 한컴 설치 경로 명시 지정 |
| `DLL_PATH_NOT_EXISTS` | registry에 있지만 DLL 파일 없음 | 한컴 재설치 또는 경로 확인 |
| `HANCOM_REGISTER_MODULE_FAILED` | RegisterModule 호출 실패 | 모듈 호환성 확인 |
| `REGISTRY_PERMISSION_DENIED` | registry 쓰기 권한 없음 | 관리자 권한으로 setup script 재실행 |

### 단위 테스트

```bash
pytest agent/tests/test_hancom_hwp_security_module_detailed.py -v
```

- ✅ 보안모듈 미등록 시 SETUP_REQUIRED
- ✅ registry에 module이 없으면 접근 금지
- ✅ RegisterModule 호출 여부 검증
- ✅ Open 호출 차단 조건 확인
- ✅ registry write 함수 호출 없음 (read-only)

### 보안모듈 자동 등록 (사용자 명시 승인)

**setup_hancom_security_module.py 스크립트:**

보안모듈이 등록되지 않은 경우, 다음 스크립트로 사용자 명시 승인 후 자동으로 registry에 등록할 수 있습니다.

```bash
# 자동 DLL 탐색으로 등록
python scripts/setup_hancom_security_module.py

# 또는 명시적 DLL 경로 지정
python scripts/setup_hancom_security_module.py --dll-path "C:\Program Files\HNC\한글2014\Bin\HwpAutomation.dll"
```

**스크립트 동작:**

1. **현재 상태 확인**: 보안모듈 등록 여부 표시
2. **사용자 승인 요청**: "계속 진행하시겠습니까? (y/n):"
3. **DLL 자동 탐색**: 표준 설치 경로에서 HwpAutomation.dll 찾기
4. **Registry 등록**: y 입력 시에만 HKEY_CURRENT_USER에 module 등록
5. **등록 검증**: registry 읽기 후 설정 확인

**보안 정책:**

- ✅ n 입력 시: 사용자 승인 없음 → registry write 없음 → 안전 종료
- ✅ y 입력 시에만: registry에 module 등록
- ✅ 팝업 자동 클릭 없음: 공식 방식(RegisterModule)만 사용
- ✅ 원본 파일 보호: 변환 workflow에서 registry write 차단

**실행 예시:**

```bash
C:\Users\skyjw> python scripts/setup_hancom_security_module.py
======================================================================
한컴 보안모듈 자동 등록
======================================================================

[1단계] 현재 보안모듈 상태 확인...
  등록 여부: ❌ 미등록

[2단계] 사용자 승인 확인...

보안모듈을 Registry에 등록하시겠습니까?
(이 작업은 관리자 권한이 필요할 수 있습니다.)

계속 진행하시겠습니까? (y/n): y

[3단계] 보안모듈 자동 등록 중...

✅ 보안모듈 등록 완료
   모듈명: FilePathCheckerModuleExample
   DLL 경로: C:\Program Files\HNC\한글2014\Bin\HwpAutomation.dll
   Registry: HKEY_CURRENT_USER\Software\HNC\HwpAutomation\Modules

[4단계] 등록 확인...
  ✅ 보안모듈 확인됨: FilePathCheckerModuleExample
  ✅ DLL 경로 확인됨: C:\Program Files\HNC\한글2014\Bin\HwpAutomation.dll

======================================================================
✅ 보안모듈 등록이 완료되었습니다.
======================================================================

이제 HWP → HWPX 변환 시 보안팝업이 뜨지 않습니다.
```

**에러 처리:**

- `DLL_PATH_NOT_FOUND`: 한컴 미설치 또는 비표준 경로 → `--dll-path` 옵션으로 명시 지정
- `REGISTRY_PERMISSION_DENIED`: 관리자 권한 없음 → 관리자 권한으로 재실행
- `DLL_PATH_NOT_EXISTS`: 지정된 경로에 DLL 없음 → 한컴 설치 경로 확인

**주의:**

- 관리자 권한 필요할 수 있음 (registry write)
- 사용자가 명시적으로 y를 입력할 때만 registry 수정
- 한 번 등록되면 재등록 불필요

---

## 향후 개선사항

1. **UI 통합**: 변환 진행률 표시
2. **배치 처리**: 대량 파일 변환 최적화
3. **형식 확장**: DOCX, ODP 등 추가 형식 지원
4. **XML 분석**: HWPX 내부 XML 구조 분석 및 추출
5. **감리서식**: 자동 감리서식 생성 (문서 구조 분석 기반)
6. **캐싱**: 변환 결과 캐싱 및 재사용

---

## 유지보수

- **기준선 검토**: 분기별 또는 주요 기능 추가 시
- **보안모듈 정책**: 한컴 공식 업데이트 시 반영
- **테스트**: 신규 기능 추가 시 회귀 테스트 필수

---

**기준선 확정:** 2026-05-02  
**보안모듈 setup 추가:** 2026-05-02  
**검증 완료:** 2026-05-02 (setup script y/n 정책, registry write 격리, 팝업 자동 클릭 없음, unit tests 100%)  
**다음 검토:** 2026-08-02  
**관리자:** AI Orchestrator Team
