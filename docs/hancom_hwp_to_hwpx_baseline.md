# 한컴 HWP → HWPX 변환 Worker - 기준선 사양

**Date:** 2026-05-02  
**Status:** 기준선 확정  
**Testing:** 18개 테스트 모두 통과 (경로 11 + HWPX 검증 7)

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

**총 18개 테스트 통과:**

### 경로 검증 (11개)
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

### HWPX 패키지 검증 (7개)
- 유효한 HWPX 검증 ✅
- 파일 없음 ✅
- ZIP 아님 ✅
- Contents 없음 ✅
- 섹션 없음 ✅
- 구조 분석 ✅
- 메타데이터 추출 ✅

### Workflow (4개)
- 변환 성공 (mock) ✅
- 변환 실패 ✅
- HWPX 검증 실패 ✅
- 필수 파라미터 누락 ✅

---

## 향후 개선사항

1. **UI 통합**: 변환 진행률 표시
2. **배치 처리**: 대량 파일 변환 최적화
3. **형식 확장**: DOCX, ODP 등 추가 형식 지원
4. **XML 분석**: HWPX 내부 XML 구조 분석 및 추출
5. **감리서식**: 자동 감리서식 생성 (문서 구조 분석 기반)
6. **캐싱**: 변환 결과 캐싱 및 재사용

---

## 라이선스 고지

**한컴 HwpObject 자동화 상업적 사용:**

한컴 오피스의 COM 자동화(HwpObject)는 상업적 목적의 솔루션에서 사용 시 별도 라이선스 또는 승인이 필요합니다.

- 개발자: https://developers.hancom.com/
- 문서: 자동화 API 상업적 사용 정책 확인 필수
- 영업: contact@hancom.com

본 worker를 상업 환경에 배포하기 전에 한컴과 라이선스 협의를 진행하세요.

---

## 유지보수

- **기준선 검토**: 분기별 또는 주요 기능 추가 시
- **보안모듈 정책**: 한컴 공식 업데이트 시 반영
- **테스트**: 신규 기능 추가 시 회귀 테스트 필수

---

**기준선 확정:** 2026-05-02  
**다음 검토:** 2026-08-02  
**관리자:** AI Orchestrator Team
