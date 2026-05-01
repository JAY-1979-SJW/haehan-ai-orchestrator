# 한컴 로컬 설치 탐색 - 기준선 사양

**Date:** 2026-05-02  
**Status:** Read-only 진단 구현 완료  
**Current PC Status:** `HANCOM_SECURITY_SETUP_REQUIRED` (Exit Code: 1)  
**Current PC Details:**
- Hancom COM: ✓ Detected (HWPFrame.HwpObject)
- HwpAutomation.dll: ✗ Not Found
- Security Module: ✗ Not Registered
- Action Required: `python scripts/setup_hancom_security_module.py --dll-path "[경로]"`
**Testing:** 23개 discovery + 12개 DLL resolver = 35개 테스트 모두 통과

---

## 개요

로컬 PC의 한컴 설치 상태, COM 등록 상태, 보안모듈 상태를 read-only로 자동 탐색하는 discovery 모듈.

**특징:**
- Registry read-only 조회 (write 없음)
- COM 클래스 등록 상태 진단
- 설치 경로 및 DLL 후보 경로 탐색
- 보안모듈 registry 상태 조회
- 통합 진단 리포트 및 추천사항 생성

**원칙:**
- 모든 작업은 read-only (진단)
- Registry write 금지
- HWP 파일 열기 금지
- HwpObject 객체 생성/조작 금지
- 제한된 경로만 검색 (C드라이브 무제한 검색 금지)

---

## 모듈 구조

### 1. agent/hancom/discovery/registry.py
Windows Registry read-only 조회 및 한컴 설치 상태 진단.

**함수:**
- `read_registry_value(hkey, path, value_name)`: Registry 값 조회
- `check_registry_path_exists(hkey, path)`: Registry 경로 존재 확인
- `list_registry_subkeys(hkey, path)`: Registry 하위 키 목록
- `list_registry_values(hkey, path)`: Registry 값 목록
- `check_hancom_registry_installation()`: 한컴 Registry 설치 상태 확인
- `check_security_module_registry()`: 보안모듈 Registry 상태 조회

**정책:**
- 모든 작업은 KEY_READ로 read-only 열기
- SetValueEx, OpenKey(KEY_WRITE) 사용 금지
- 오류 시 None/False 반환 (예외 발생 금지)

### 2. agent/hancom/discovery/com.py
COM 클래스 등록 상태 및 가용성 진단.

**상수:**
- `HWPOBJECT_CLASSES`: 지원 HwpObject 클래스 목록 (우선순위 순서)
  - HWPFrame.HwpObject
  - HWPFrame.HwpObject.1
  - HWPFrame.HwpObject.2
  - HwpObject.HwpObject

**함수:**
- `check_com_class_registered(class_name)`: COM 클래스 등록 상태 (registry 기반)
- `get_com_class_clsid(class_name)`: COM 클래스 CLSID 조회
- `check_all_hwpobject_classes()`: 모든 지원 클래스 진단
- `get_hwpobject_class_priority()`: 등록된 클래스 우선순위
- `check_com_dispatch_available(class_name)`: COM Dispatch 가능성
- `diagnose_com_status()`: COM 종합 진단

**정책:**
- HwpObject Dispatch 확인은 GetObject만 시도 (생성하지 않음)
- CLSID는 registry에서만 조회 (COM 객체 생성 금지)

### 3. agent/hancom/discovery/installation.py
한컴 설치 경로 탐색 및 DLL 후보 경로 발견.

**상수:**
- `STANDARD_INSTALLATION_PATHS`: 탐색 대상 표준 설치 경로 (24개)
  - C:\Program Files\HNC\HOffice 2014-2018
  - C:\Program Files (x86)\HNC\HOffice 2014-2018
  - 한글/HOffice 조합
- `DLL_CANDIDATES`: ["HwpAutomation.dll"]
- `SEARCH_SUBDIRS`: ["Bin", "bin", ""] (하위 디렉토리)

**함수:**
- `check_path_exists(path)`: 경로 존재 확인
- `check_file_readable(path)`: 파일 읽기 가능 확인
- `find_dll_in_path(install_path)`: 설치 경로에서 DLL 탐색
- `find_dll_from_registry()`: Registry 보안모듈 정보에서 DLL 추출
- `discover_installation_paths()`: 존재하는 설치 경로 목록
- `discover_dll_candidates()`: DLL 후보 경로 발견
- `diagnose_installation_status()`: 설치 상태 진단

**정책:**
- 제한된 표준 경로만 검색 (C드라이브 무제한 검색 금지)
- 파일 시스템 접근은 os.path만 사용 (registry 필요 시 별도 모듈 호출)
- DLL 후보는 "found_readable" 또는 "found_readable_from_registry" 상태로 표시

### 4. agent/hancom/discovery/diagnostics.py
모든 진단 정보를 통합하는 orchestration 레이어.

**함수:**
- `diagnose_hancom_installation()`: 한컴 설치 종합 진단
  - 반환값: {installed, registry_status, com_status, installation_status, security_module, summary, recommendations}
- `print_diagnosis_report(diag_result)`: 사용자 친화적 진단 보고서 출력

**반환 구조:**
```python
{
    "installed": bool,  # 설치 여부
    "registry_status": {
        "HKEY_LOCAL_MACHINE_HOffice": bool,
        "HKEY_CURRENT_USER_HOffice": bool,
        "HKEY_LOCAL_MACHINE_Classes_HWPFrame": bool,
        "HKEY_LOCAL_MACHINE_Classes_HwpObject": bool,
    },
    "com_status": {
        "win32com_available": bool,
        "hwpobject_classes": {...},
        "available_classes": [클래스명],
        "dispatch_status": {...},
    },
    "installation_status": {
        "installation_paths": [경로],
        "dll_candidates": {경로: 상태},
        "primary_dll": str | None,
    },
    "security_module": {
        "registered": bool,
        "module_names": [모듈명],
        "registry_path_used": str | None,
        "details": {모듈명: DLL경로},
    },
    "summary": str,  # "Registry ✓ | COM ✓ | DLL ✓ | 보안모듈 ✓"
    "recommendations": [추천사항],
}
```

---

## 사용 예시

### Python
```python
from agent.hancom.discovery.diagnostics import diagnose_hancom_installation, print_diagnosis_report

# 진단 실행
result = diagnose_hancom_installation()

# 보고서 출력
print_diagnosis_report(result)

# 프로그래밍 활용
if result["installed"]:
    if result["security_module"]["registered"]:
        print("HWP → HWPX 변환 가능")
    else:
        print("보안모듈 등록 필요")
else:
    print("한컴 설치 필요")
```

### CLI
```bash
# 진단 스크립트 실행
python scripts/diagnose_hancom_installation.py

# Exit code:
# 0: 완전히 설치됨 (한컴 + 보안모듈)
# 1: 설치됨 (한컴만, 보안모듈 미등록)
# 2: 미설치
```

---

## 진단 결과 해석

### Summary 문자열
- `Registry ✓`: HwpObject COM 클래스 등록
- `COM ✓`: win32com 가용 + HwpObject 클래스 확인
- `DLL ✓`: HwpAutomation.dll 발견
- `보안모듈 ✓`: 보안모듈 registry 등록

### 설치 상태 판정
```
installed = registry_ok AND (com_ok OR install_ok)
```

| 상태 | 판정식 | 설명 | Exit Code | 권장사항 |
|------|--------|------|-----------|----------|
| **HANCOM_FULLY_INSTALLED** | installed=True + security_module.registered=True | 한컴 자동화 완전 설치 + 보안모듈 등록 | 0 | HWP→HWPX 변환 가능 |
| **HANCOM_SECURITY_SETUP_REQUIRED** | installed=True + security_module.registered=False | 한컴 자동화 COM 감지 + 보안모듈 미등록 | 1 | `python scripts/setup_hancom_security_module.py` 실행 |
| **HANCOM_INSTALLATION_REQUIRED** | installed=False | 한컴 자동화 미설치 | 2 | https://developers.hancom.com/ 에서 한컴 설치 |

**현재 PC 상태 (2026-05-02):**
```
Status:              HANCOM_SECURITY_SETUP_REQUIRED
Registry Status:     ✓ HWPFrame.HwpObject 클래스 등록
COM Status:          ✓ win32com 가용, HWPFrame.HwpObject v1/v2 감지
DLL Status:          ✗ HwpAutomation.dll 미발견
Security Module:     ✗ 보안모듈 미등록
Summary:             Registry ✓ | COM ✓
Diagnostics Result:  한컴 자동화 COM은 감지되었으나 보안모듈 등록이 필요
Exit Code:           1
Next Action:         python scripts/setup_hancom_security_module.py --dll-path "[경로]"
```

**상태별 설명:**

- **HANCOM_FULLY_INSTALLED** (Exit Code: 0)
  - ✓ Registry, COM, DLL, 보안모듈 모두 준비됨
  - ✓ HWP 파일을 HWPX로 변환 가능
  - ✓ RegisterModule을 통한 보안 팝업 제거 됨

- **HANCOM_SECURITY_SETUP_REQUIRED** (Exit Code: 1) ← 현재 상태
  - ✓ 한컴 자동화 COM 클래스 등록됨 (HWPFrame.HwpObject)
  - ✓ win32com 모듈 가용
  - ✗ HwpAutomation.dll 미발견 또는 보안모듈 미등록
  - 📌 행동 필요: `python scripts/setup_hancom_security_module.py` 실행
  - 옵션: `--dll-path "경로"` 로 DLL 경로 명시 지정

- **HANCOM_INSTALLATION_REQUIRED** (Exit Code: 2)
  - ✗ 한컴 자동화 COM 클래스 미등록
  - ✗ 한컴 미설치 또는 COM 등록 실패
  - 📌 행동 필요: https://developers.hancom.com/ 에서 한컴 설치

---

## 테스트 기준선

**총 23개 테스트 통과:**

### Registry 진단 (6개)
- 유효한/유효하지 않은 Registry 경로 확인
- Registry 값/하위 키 조회
- 한컴 Registry 설치 상태 확인
- 보안모듈 Registry 상태 확인

### COM 진단 (6개)
- COM 클래스 정의
- COM 클래스 등록 상태 확인
- CLSID 조회
- 모든 HwpObject 클래스 진단
- 우선순위 목록
- COM 종합 진단

### 설치 탐색 (8개)
- 표준 경로 목록 확인
- 경로 존재/파일 읽기 확인
- DLL 탐색
- 설치 경로 발견
- DLL 후보 발견
- 설치 상태 진단

### 통합 진단 (3개)
- 한컴 설치 종합 진단
- Recommendations 타입 검증
- 진단 보고서 출력 (에러 없음)

### 보안 검증 (1개)
- ✅ 진단에서 registry write 없음 (SetValueEx 호출 안 됨)

---

## 제약사항 및 한계

### 제약사항
1. **Registry read-only**: 진단만 수행, write 금지
2. **HwpObject 생성 금지**: Dispatch 확인만 수행
3. **HWP 파일 접근 금지**: 설치 상태 확인만 수행
4. **제한된 경로 검색**: 표준 설치 경로만 탐색

### 한계
1. **설치 경로 자동 감지**: 비표준 경로는 탐색 불가
   - 해결: `--install-path` 옵션으로 명시 지정 (향후)
2. **다중 설치 버전**: 여러 버전 설치 시 primary만 반환
   - 해결: dll_candidates 딕셔너리에서 전체 목록 확인
3. **라이선스 정보**: 설치 버전의 상업/비상업 구분 불가
   - 제약: HwpObject 자동화는 상업적 사용 시 별도 라이선스 필요

---

## 향후 개선사항

1. **비표준 경로 지원**: `--install-path` 옵션 추가
2. **버전 정보 추출**: 설치된 한컴 버전 자동 감지
3. **라이선스 확인**: 상업/비상업 라이선스 판정
4. **자동 등록**: setup_hancom_security_module.py와 통합
5. **시스템 트레이**: 백그라운드 진단 및 알림

---

## 유지보수

- **진단 테스트**: 분기별 한컴 버전 업데이트 시
- **표준 경로**: 새로운 한컴 버전 설치 경로 추가 시
- **COM 클래스**: 한컴 API 변경 시 클래스 목록 갱신

---

## 현재 PC 기준 상태 기록

**기준선 확정:** 2026-05-02  
**현재 상태 기록:** 2026-05-02

| 항목 | 상태 | 설명 |
|------|------|------|
| **진단 상태** | HANCOM_SECURITY_SETUP_REQUIRED | 한컴 자동화 COM은 감지됨, 보안모듈 등록 필요 |
| **Registry** | ✓ Detected | HWPFrame.HwpObject 클래스 등록 |
| **COM** | ✓ Detected | win32com 가용, HWPFrame.HwpObject v1/v2 감지 |
| **DLL** | ✗ Not Found | HwpAutomation.dll 미발견 |
| **Security Module** | ✗ Not Registered | 보안모듈 미등록 |
| **Exit Code** | 1 | 한컴 설정 필요 |
| **다음 단계** | `python scripts/setup_hancom_security_module.py --dll-path "[경로]"` | DLL 경로 명시 지정 후 실행 |

**참고:**
- "한컴 미설치" ❌ → "한컴 자동화 COM은 감지되었으나 보안모듈 등록이 필요" ✅
- "팝업 없는 변환 완료" ❌ → "보안모듈 등록 후 RegisterModule을 통해 팝업 제거 가능" ✅
- "완전 변환 가능" ❌ → "보안모듈 등록 시 HWP→HWPX 변환 가능" ✅

**다음 검토:** 2026-08-02  
**관리자:** AI Orchestrator Team
