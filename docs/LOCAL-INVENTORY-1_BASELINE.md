# [LOCAL-INVENTORY-1] 로컬 자산 인벤토리 맵 - 안전선 기준선

**Date**: 2026-05-02  
**Status**: 설계 단계 (안전선 고정)  
**Scope**: 로컬 PC의 메타데이터 인벤토리화 (파일 내용 읽기 금지)  

---

## 핵심 원칙

### 🔒 금지 사항 (절대 금지)
- ❌ 파일 **내용** 읽기 (file content)
- ❌ 비밀번호, 인증서, 쿠키, 세션 탐색
- ❌ Registry write (read-only만)
- ❌ 파일 삭제, 수정, 생성
- ❌ 서버 전송
- ❌ 무제한 deep scan (모든 파일 무차별)
- ❌ AppData 전체 스캔
- ❌ Windows/System32 전체 스캔

### ✅ 허용 사항 (명시적 동의 기반)
- ✅ 사용자 **명시 동의** 후 스캔
- ✅ 파일/폴더 **메타데이터** 조회 (경로, 크기, 수정시간, 존재여부)
- ✅ 제한된 확장자만 탐색 (.exe, .dll, .txt, .doc 등)
- ✅ 사전정의된 경로만 탐색 (Program Files, Documents, Desktop 등)
- ✅ Registry **read-only** 조회 (KEY_READ만)
- ✅ COM 클래스 read-only 확인
- ✅ DLL 후보 경로 인덱싱
- ✅ 로컬 JSON/SQLite 저장
- ✅ 타임스탐프/해시로 변경 감지

---

## 수집 대상 (명시 동의 기반)

### 1. 한컴 (Hancom)
```
수집: 설치 경로, 버전, COM 클래스, 보안모듈 상태
경로: C:\Program Files\HNC\*
      HKEY_LOCAL_MACHINE\SOFTWARE\HNC
      HKEY_CURRENT_USER\Software\HNC
메타데이터: 폴더 존재, 파일 크기, 수정시간, Registry 값
내용 읽기: ❌ 금지
```

### 2. Microsoft Excel
```
수집: 설치 경로, 버전, COM 클래스, Add-in 정보
경로: C:\Program Files\Microsoft Office\*
      HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Office
메타데이터: 폴더 존재, 파일 크기, 수정시간, Registry 값
내용 읽기: ❌ 금지
```

### 3. AutoCAD/CAD
```
수집: 설치 경로, 버전, COM 클래스
경로: C:\Program Files\Autodesk\*
      HKEY_LOCAL_MACHINE\SOFTWARE\Autodesk
메타데이터: 폴더 존재, 파일 크기, 수정시간, Registry 값
내용 읽기: ❌ 금지
```

### 4. 문서 작업 폴더 (메타데이터만)
```
수집: 폴더 경로, 폴더 크기, 파일 개수, 최근 수정시간
경로: %USERPROFILE%\Documents
      %USERPROFILE%\Downloads
      %USERPROFILE%\Desktop
      %USERPROFILE%\OneDrive\*

확장자: .hwp, .doc, .docx, .xls, .xlsx, .ppt, .pptx, .pdf 등
메타데이터: 파일 경로, 크기, 수정시간, 확장자
내용 읽기: ❌ 금지 (메타만)
```

### 5. 일반 프로그램
```
수집: 설치된 프로그램 목록, 버전, 설치 경로
경로: HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall
메타데이터: 프로그램명, 버전, 설치 경로, 설치 날짜
내용 읽기: ❌ 금지
```

---

## 인벤토리 구조

### 저장 형식
```json
{
  "metadata": {
    "scan_date": "2026-05-02T12:34:56Z",
    "scan_version": "1.0",
    "user_consent": true,
    "scan_scope": ["hancom", "excel", "documents"]
  },
  "programs": {
    "hancom": {
      "installed": true,
      "paths": {
        "installation": "C:\\Program Files\\HNC\\한글2014",
        "bin": "C:\\Program Files\\HNC\\한글2014\\Bin"
      },
      "com_classes": [
        "HWPFrame.HwpObject",
        "HWPFrame.HwpObject.1"
      ],
      "version": "2014",
      "last_modified": "2026-01-15T10:30:00Z"
    },
    "excel": {
      "installed": true,
      "paths": {
        "installation": "C:\\Program Files\\Microsoft Office\\Office16"
      },
      "com_classes": ["Excel.Application"],
      "version": "16.0",
      "last_modified": "2025-12-20T09:00:00Z"
    }
  },
  "folders": {
    "documents": {
      "path": "C:\\Users\\{user}\\Documents",
      "size_bytes": 1073741824,
      "file_count": 245,
      "last_modified": "2026-05-02T10:00:00Z",
      "doc_types": {
        "hwp": 5,
        "docx": 12,
        "xlsx": 8
      }
    }
  },
  "registry": {
    "installed_programs": [
      {
        "name": "한글 2014",
        "version": "14.0",
        "publisher": "한컴",
        "install_date": "2024-01-15"
      }
    ]
  }
}
```

---

## 스캔 정책

### 스캔 경로 (사전 정의, 무제한 아님)

**프로그램 설치 경로:**
```
C:\Program Files\HNC\*          (한컴)
C:\Program Files (x86)\HNC\*   (한컴 32-bit)
C:\Program Files\Microsoft Office\*  (Excel)
C:\Program Files\Autodesk\*    (CAD)
C:\Program Files\Google\Chrome\*
C:\Program Files\Mozilla Firefox\*
```

**사용자 문서 폴더:**
```
%USERPROFILE%\Documents
%USERPROFILE%\Downloads
%USERPROFILE%\Desktop
%USERPROFILE%\OneDrive
```

**Registry 경로:**
```
HKEY_LOCAL_MACHINE\SOFTWARE\HNC
HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Office
HKEY_LOCAL_MACHINE\SOFTWARE\Autodesk
HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall
HKEY_CURRENT_USER\Software\HNC
```

### 제외 경로 (기본 제외)
```
❌ C:\Windows\*             (시스템)
❌ C:\ProgramData\*        (전체 deep scan 금지)
❌ %AppData%\*             (전체 deep scan 금지)
❌ %LocalAppData%\*        (전체 deep scan 금지)
❌ C:\$Recycle.Bin\*       (휴지통)
❌ 숨김/시스템 폴더
```

### 깊이 제한
- 사용자 폴더: 최대 3 depth
- 프로그램 폴더: 최대 2 depth
- Registry: 직접 키만 (하위 재귀 금지)

### 파일 확장자 필터
**수집 대상:**
```
실행파일: .exe, .dll, .ocx
문서: .hwp, .doc, .docx, .xls, .xlsx, .ppt, .pptx, .pdf
설정: .ini, .config, .xml
```

**제외:**
```
임시파일: .tmp, .bak, .~*
시스템: .sys, .drv
압축: .zip, .rar, .7z (메타만)
실행: .bat, .cmd, .ps1, .vbs
```

---

## 사용자 동의 정책

### 동의 전 표시 정보
```
📋 로컬 자산 인벤토리 스캔

다음 정보를 수집합니다 (로컬만 저장, 서버 전송 없음):
✓ 한컴 설치 상태 및 버전
✓ Excel 설치 상태 및 버전
✓ 문서 폴더 메타데이터 (경로, 크기, 수정시간)
✓ 설치된 프로그램 목록

수집되지 않는 정보:
✗ 파일 내용
✗ 비밀번호, 인증서, 쿠키
✗ 브라우저 히스토리
✗ 개인 정보

저장 위치: 로컬 PC (%APPDATA%\haehan-ai-orchestrator\inventory.db)
전송: 없음 (오프라인 사용)
삭제: 사용자가 언제든 삭제 가능

계속 진행하시겠습니까? (y/n):
```

---

## 모듈 구조

### agent/local_inventory/
```
__init__.py              # 패키지 초기화
scanner.py              # 메인 스캔 로직 + 동의 처리
metadata.py             # 메타데이터 수집 (파일, COM, registry)
policy.py               # 정책 (허용 경로, 깊이, 확장자)
inventory.py            # 인벤토리 저장/로드 (JSON, SQLite)
```

---

## 구현 계획

### Phase 1: 기본 틀
- [x] 안전선 기준선 문서
- [ ] scanner.py: 사용자 동의 UI
- [ ] policy.py: 경로/확장자 정책
- [ ] metadata.py: 메타데이터 수집 (파일, registry, COM)

### Phase 2: 인벤토리 관리
- [ ] inventory.py: JSON/SQLite 저장
- [ ] 변경 감지 (timestamp/hash)

### Phase 3: 테스트 & 문서
- [ ] 단위 테스트
- [ ] 통합 테스트
- [ ] 사용 가이드

---

## 안전성 체크리스트

- [x] 파일 내용 읽기 금지 정책 명시
- [x] Registry write 금지 정책 명시
- [x] 서버 전송 금지 정책 명시
- [x] 사용자 동의 필수 명시
- [x] 수집 대상 명확히 정의
- [x] 제외 경로 명확히 정의
- [x] 깊이 제한 명시
- [x] 저장 위치 로컬로 제한

---

## 참고

- HANCOM-SECURITY-2에서 구현한 discovery 모듈 재사용
- agent/hancom/discovery/ 통합
- 다른 프로그램(Excel, CAD)도 같은 패턴 적용
