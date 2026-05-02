# 로컬 자산 인벤토리 시스템 (LOCAL INVENTORY BASELINE)

## 1. 개요

### 1.1 정의

**로컬 자산 인벤토리**는 사용자 PC의 설치된 소프트웨어, 레지스트리 정보, COM 클래스를 **메타데이터 수준에서만** 수집하는 오프라인 시스템입니다.

```
┌─────────────────────────────────────────────────────┐
│         로컬 자산 인벤토리 시스템                    │
├─────────────────────────────────────────────────────┤
│                                                     │
│  수집 ─→ 메타데이터 필터 ─→ 인벤토리 저장 (JSON)     │
│   ↓        ↓                                        │
│  스캔   동의/동의    로컬 PC만                       │
│  레벨  (Consent)                                    │
│                                                     │
│  ✓ Program Files 메타데이터                        │
│  ✓ Registry 정보 (read-only)                       │
│  ✓ COM 클래스 등록 상태                            │
│  ✓ DLL 경로 감지                                   │
│                                                     │
│  ✗ 파일 내용                                       │
│  ✗ 개인 정보 (사용자명 마스킹)                      │
│  ✗ 비밀번호/토큰/인증서                            │
│  ✗ 서버 전송                                       │
│                                                     │
└─────────────────────────────────────────────────────┘
```

---

## 2. 왜 필요한가?

### 2.1 배경

한컴(HWP), Excel, AutoCAD 등 대형 애플리케이션은 복잡한 의존성을 가집니다:
- 여러 설치 경로 (Program Files, x86 등)
- 레지스트리 설정
- COM 클래스 등록
- 보조 DLL 및 모듈

이러한 정보는 **파일 변환**, **호환성 검사**, **자산 추적** 시 필수입니다.

### 2.2 설계 원칙

| 원칙 | 이유 |
|------|------|
| **메타데이터만** | 파일 내용은 불필요, 시간/성능 효율 |
| **로컬 저장** | 개인정보 보호, 서버 부하 감소 |
| **동의 기반** | 사용자 신뢰, 규정 준수 |
| **읽기 전용** | 시스템 안전성 보장 |
| **4단계 레벨** | 사용자가 스캔 범위 선택 가능 |

---

## 3. 수집하는 것 (✓ DO COLLECT)

### 3.1 Program Files 메타데이터

**시작하는 경로:**
```
C:\Program Files\*
C:\Program Files (x86)\*
C:\ProgramData\*  (일부)
```

**수집 항목:**
```python
{
    "path": "C:\\Program Files\\HNC\\HOffice 2014",
    "exists": true,
    "size_bytes": 524288000,      # 500 MB
    "modified_time": "2024-12-15T10:30:00Z",
    "extension": ".exe"
}
```

✓ 파일 경로
✓ 파일 크기
✓ 수정 시간
✓ 확장자

### 3.2 Registry 정보

**읽는 경로:**
```
HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall
HKEY_LOCAL_MACHINE\SOFTWARE\HNC
HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Office
HKEY_LOCAL_MACHINE\SOFTWARE\Autodesk
HKEY_LOCAL_MACHINE\SOFTWARE\Classes\CLSID
```

**수집 항목:**
```python
{
    "name": "HNC HOffice 2014",
    "version": "14.0.2000",
    "install_location": "C:\\Program Files\\HNC\\HOffice 2014",
    "publisher": "Hansol Corp"
}
```

✓ 프로그램 이름
✓ 버전 정보
✓ 설치 경로
✓ COM 클래스 등록 여부

### 3.3 COM 클래스 등록

**확인 항목:**
```python
{
    "HWPFrame.HwpObject": true,           # 한컴
    "Excel.Application": true,            # Excel
    "AutoCAD.Application": false,         # AutoCAD
    "Word.Application": true              # Word
}
```

✓ COM ProgID
✓ CLSID 등록 여부

### 3.4 DLL 위치 추적

**감지 대상:**
```
HwpAutomation.dll        (한컴)
ExcelOM.dll              (Excel)
acad.exe / acad.dll      (AutoCAD)
```

---

## 4. 수집하지 않는 것 (✗ DO NOT COLLECT)

| 항목 | 이유 |
|------|------|
| **파일 내용** | 개인정보, 회사 기밀 |
| **사용자명** | 프라이버시 (마스킹됨) |
| **암호/토큰** | 보안 위험 |
| **브라우저 히스토리** | 개인정보 |
| **문서 내용** | 기밀 유지 |
| **네트워크 설정** | 보안 위험 |
| **라이선스 키** | 보안 위험 |

### 4.1 경로 마스킹

사용자명을 자동으로 제거합니다:

```python
# 원본
"C:\\Users\\skyjw\\AppData\\Roaming\\HNC\\HOffice"

# 저장된 형태
"C:\\Users\\<USER>\\AppData\\Roaming\\HNC\\HOffice"
```

### 4.2 민감 경로 필터링

다음 패턴을 포함한 경로는 자동 제외:
```
password
credential
secret
token
api_key
.ssh
.aws
.kube
```

---

## 5. Scan Level (스캔 범위)

### 5.1 4단계 시스템

| 레벨 | 이름 | 범위 | 동의 | 깊이 | 파일 |
|------|------|------|------|------|------|
| **0** | NO_SCAN | 없음 | 불필요 | 0 | 0 |
| **1** | SAFE_INVENTORY | Program Files / Registry / COM | 자동 | 2 | 1,000 |
| **2** | USER_FOLDERS | Level 1 + 사용자 선택 폴더 | 필수 | 3 | 3,000 |
| **3** | DEEP_METADATA | Level 2 + 깊이 스캔 | **명시 동의** | 5 | 10,000 |

### 5.2 상세 설명

#### Level 1: SAFE_INVENTORY (기본값)

**허용 범위:**
```
Program Files
Program Files (x86)
ProgramData (일부)
Registry (Uninstall, Classes, HNC, Office, Autodesk)
COM 클래스
```

**제한:**
- max_depth: 2
- max_files: 1,000 개
- 사용자 폴더 스캔 안 함
- 자동 진행 (동의 저장되면 재확인 안 함)

**예시:**
```python
from agent.local_inventory.diagnostics import InventoryScanParams, run_local_inventory_scan
from agent.local_inventory.scan_level import ScanLevel

params = InventoryScanParams(
    scan_level=ScanLevel.SAFE_INVENTORY,  # 기본값
    force_consent=False,  # 저장된 동의 사용
)

result = run_local_inventory_scan(params)
# {
#   "ok": true,
#   "programs": {...},
#   "dlls": {...},
#   "scan_date": "2026-05-02T...",
# }
```

#### Level 2: USER_FOLDERS

**추가 범위:**
```
%USERPROFILE%\Documents
%USERPROFILE%\Desktop
사용자가 선택한 폴더
```

**요구사항:**
- `user_selected_paths` 파라미터 필수
- 동의 다시 확인 (명시 동의)

**예시:**
```python
params = InventoryScanParams(
    scan_level=ScanLevel.USER_FOLDERS,
    user_selected_paths=[
        "C:\\Users\\skyjw\\Documents",
        "C:\\Users\\skyjw\\Desktop",
    ],
    force_consent=False,
)
```

#### Level 3: DEEP_METADATA

**추가 범위:**
```
전체 드라이브 (사용자 선택)
깊이 최대 5단계
파일 최대 10,000개
```

**특징:**
- 가장 제한적
- 시간 많이 소요
- **명시 동의 필수** (매번 재확인)
- 기본값 비활성

---

## 6. Consent Policy (동의 관리)

### 6.1 동의 흐름

```
사용자 스캔 요청
    ↓
저장된 동의 확인?
    ├─ Yes (Level 1) → 스캔 진행 ✓
    └─ No → 동의 대화 표시
       ↓
    사용자 동의?
       ├─ Yes (y) → 동의 저장, 스캔 진행 ✓
       └─ No (n) → 스캔 차단 ✗
```

### 6.2 동의 저장 위치

```
%LOCALAPPDATA%\HaehanAI\inventory\consent.json
```

**저장 형식:**
```json
{
  "version": "1.1",
  "scopes": [
    "programs",
    "com_registry",
    "hancom",
    "office",
    "cad"
  ],
  "level": 1,
  "granted_at": "2026-05-02T10:00:00Z",
  "saved_at": "2026-05-02T10:00:00Z"
}
```

### 6.3 동의 해제

사용자가 다음 파일을 삭제하면 동의 취소:
```
%LOCALAPPDATA%\HaehanAI\inventory\consent.json
```

다시 스캔 시 동의 대화가 표시됩니다.

---

## 7. 로컬 저장 (Local-Only Storage)

### 7.1 저장 경로

```
%LOCALAPPDATA%\HaehanAI\inventory\
├── local_inventory.json       (스캔 결과)
├── consent.json               (동의 상태)
└── local_inventory.db         (선택적)
```

### 7.2 저장 형식 (JSON)

```json
{
  "metadata": {
    "scan_date": "2026-05-02T10:30:00Z",
    "scan_version": "1.0",
    "scan_level": 1,
    "scopes": ["programs", "com_registry", "hancom", "office", "cad"]
  },
  "programs": {
    "hancom": {
      "name": "HNC HOffice 2014",
      "installed": true,
      "install_paths": ["C:\\Program Files\\HNC\\HOffice 2014"],
      "version": "14.0.2000",
      "com_classes": {
        "HWPFrame.HwpObject": true,
        "HWPFrame.HwpObjForm": true
      },
      "registry_info": {
        "DisplayVersion": "14.0.2000",
        "Path": "C:\\Program Files\\HNC\\HOffice 2014"
      },
      "detection_method": "combined"  # filesystem + registry + com
    },
    "office": {...},
    "cad": {...}
  },
  "dlls": {
    "hwp_automation": [
      {"path": "C:\\...\HwpAutomation.dll", "exists": true, ...}
    ],
    "excel_com": [...],
    "autocad": [...]
  }
}
```

### 7.3 특징

| 특징 | 설명 |
|------|------|
| **로컬만** | 서버 전송 없음 |
| **텍스트** | JSON - 사용자가 직접 확인 가능 |
| **타임스탐프** | 버전 관리, 변경 추적 |
| **자동 백업** | 마지막 스캔 보존 |
| **사용자 삭제** | 언제든 파일 삭제 가능 |

---

## 8. Privacy Filter (개인정보 필터링)

### 8.1 자동 마스킹

#### 사용자명 제거

```python
# 원본 경로
"C:\\Users\\skyjw\\AppData\\Roaming\\HNC"

# 저장된 형태
"C:\\Users\\<USER>\\AppData\\Roaming\\HNC"
```

#### 민감 경로 자동 제외

다음을 포함한 경로는 수집하지 않음:
```
password
credential
secret
token
api_key
.ssh
.aws
.kube
```

### 8.2 구현

```python
from agent.local_inventory.privacy_filter import mask_username, is_sensitive_path

# 마스킹
masked = mask_username("C:\\Users\\skyjw\\Documents")
# "C:\\Users\\<USER>\\Documents"

# 필터링
if is_sensitive_path("C:\\Users\\skyjw\\.ssh"):
    # 이 경로는 수집하지 않음
    pass
```

---

## 9. 애플리케이션 연결 방식

### 9.1 한컴(HWP) 연결

#### 감지 방식

```
1. 파일시스템 확인
   C:\Program Files\HNC\HOffice*
   
2. Registry 조회
   HKEY_LOCAL_MACHINE\SOFTWARE\HNC
   
3. COM 클래스 확인
   HWPFrame.HwpObject
   HWPFrame.HwpObjForm
   
4. 모듈 확인
   HNC\HOffice*\HwpAutomation\Modules
```

#### 사용 예시

```python
from agent.local_inventory.diagnostics import run_local_inventory_scan
from agent.local_inventory.scan_level import ScanLevel, get_level_config

# 레벨 1 스캔
result = run_local_inventory_scan(...)

# 한컴 정보 조회
hancom = result['programs']['hancom']

if hancom['installed']:
    print(f"한컴 {hancom['version']} 설치됨")
    print(f"COM 클래스: {sum(1 for v in hancom['com_classes'].values() if v)}개")
    
    # UI에서 사용 예시
    # - 한컴 문서 변환 활성화
    # - Excel 연계 기능 제안
    # - 호환성 검사 수행
```

### 9.2 Excel 연결

#### 감지 방식

```
1. 파일시스템 확인
   C:\Program Files\Microsoft Office\*
   
2. Registry 조회
   HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Office
   
3. COM 클래스 확인
   Excel.Application
   Excel.Workbook
```

### 9.3 AutoCAD 연결

#### 감지 방식

```
1. 파일시스템 확인
   C:\Program Files\Autodesk\*
   
2. Registry 조회
   HKEY_LOCAL_MACHINE\SOFTWARE\Autodesk
   
3. DLL 매핑
   acad.dll, acad.exe
```

---

## 10. 상용화 UI 흐름

### 10.1 초기 실행

```
┌─────────────────────────────────┐
│  로컬 자산 인벤토리             │
│                                 │
│  이 PC의 소프트웨어를 분석하고  │
│  호환성을 검사합니다.           │
│                                 │
│  ✓ 설치된 프로그램              │
│  ✓ COM 클래스 등록              │
│  ✓ 호환성 검사                  │
│                                 │
│  🔒 개인정보는 PC에만 저장      │
│                                 │
│  [스캔 시작]                    │
└─────────────────────────────────┘
```

### 10.2 스캔 중

```
┌─────────────────────────────────┐
│  스캔 중... (약 10초)           │
│                                 │
│  [████████░░] 50%               │
│                                 │
│  • 프로그램 분석 중...          │
│  • COM 클래스 확인 중...        │
│  • 호환성 검사 중...            │
└─────────────────────────────────┘
```

### 10.3 결과 표시

```
┌──────────────────────────────────┐
│  스캔 완료                        │
│                                  │
│  📦 설치된 프로그램              │
│  • HNC HOffice 2014 v14.0.2000   │
│  • Microsoft Office 365          │
│  • AutoCAD 2024                  │
│                                  │
│  ✓ 호환성: 95% (매우 좋음)      │
│                                  │
│  [상세 보기] [변환 시작] [닫기] │
└──────────────────────────────────┘
```

### 10.4 상세 정보

```
┌──────────────────────────────────┐
│  한컴(HWP)                       │
│                                  │
│  설치 상태: ✓ 설치됨            │
│  버전: 14.0.2000                │
│  설치 경로:                      │
│    C:\Program Files\HNC\HOffice  │
│                                  │
│  COM 클래스:                     │
│  ✓ HWPFrame.HwpObject           │
│  ✓ HWPFrame.HwpObjForm          │
│  ✓ HWPFrame.Shape               │
│                                  │
│  지원 기능:                      │
│  • HWP 파일 변환                │
│  • 메타데이터 추출              │
│  • 호환성 검사                  │
└──────────────────────────────────┘
```

---

## 11. 삭제 및 초기화

### 11.1 인벤토리 삭제

#### 전체 삭제

```
방법 1: 파일 시스템
  1. Windows 탐색기 열기
  2. %LOCALAPPDATA%\HaehanAI\inventory로 이동
  3. 폴더 우클릭 → 삭제
  
방법 2: 애플리케이션
  1. 설정 → 개인정보
  2. [로컬 인벤토리 초기화] 클릭
  3. 확인
```

#### 선택적 삭제

```python
from pathlib import Path

# 인벤토리만 삭제 (동의는 유지)
inventory_path = Path.home() / "AppData" / "Local" / "HaehanAI" / "inventory" / "local_inventory.json"
inventory_path.unlink()  # 인벤토리 파일 삭제

# 동의는 유지되므로 다시 스캔하면 대화 표시 안 함
```

### 11.2 동의 취소

```python
from pathlib import Path

# 동의 상태 삭제
consent_path = Path.home() / "AppData" / "Local" / "HaehanAI" / "inventory" / "consent.json"
consent_path.unlink()  # 동의 파일 삭제

# 다시 스캔 시 동의 대화 표시
```

### 11.3 완전 초기화

```python
import shutil
from pathlib import Path

# 모든 데이터 삭제
inventory_dir = Path.home() / "AppData" / "Local" / "HaehanAI" / "inventory"
shutil.rmtree(inventory_dir)  # 폴더 전체 삭제

# 다음 스캔 시 처음부터 시작
```

### 11.4 자동 정리

```python
# 7일 이상 된 백업 자동 삭제
from agent.local_inventory.inventory_store import InventoryStore
from datetime import datetime, timedelta

store = InventoryStore()
store.cleanup_old_backups(days=7)
```

---

## 12. 기술 스택

### 12.1 파일 구조

```
agent/local_inventory/
├── __init__.py                 # 진입점
├── scan_level.py              # Level 0~3 정의
├── scan_scope.py              # 스코프 (PROGRAMS, COM_REGISTRY 등)
├── consent_policy.py           # 동의 관리
├── diagnostics.py             # 스캔 오케스트레이션
├── filesystem_scanner.py       # 파일 메타데이터 수집
├── registry_scanner.py        # Registry 읽기
├── com_scanner.py             # COM 클래스 확인
├── app_detector.py            # 앱 감지 (종합)
├── dll_mapper.py              # DLL 위치 추적
├── inventory_store.py         # JSON 저장/로드
├── change_watcher.py          # 변경 감지 (diff)
└── privacy_filter.py          # 개인정보 필터링
```

### 12.2 주요 클래스

```python
# 파라미터
from agent.local_inventory.diagnostics import InventoryScanParams

# 스캔 레벨
from agent.local_inventory.scan_level import ScanLevel

# 결과 저장
from agent.local_inventory.inventory_store import InventoryStore

# 변경 감지
from agent.local_inventory.change_watcher import InventoryDiff
```

### 12.3 동작 흐름

```python
# 1. 파라미터 설정
params = InventoryScanParams(
    scan_level=ScanLevel.SAFE_INVENTORY,
    force_consent=False,
)

# 2. 스캔 실행
from agent.local_inventory.diagnostics import run_local_inventory_scan
result = run_local_inventory_scan(params)

# 3. 결과 확인
if result.get('ok'):
    programs = result.get('programs')
    print(f"탐지된 프로그램: {len(programs)}개")

# 4. 저장 위치
from agent.local_inventory.inventory_store import InventoryStore
store = InventoryStore()
inventory = store.load()
```

---

## 13. FAQ

### Q1: 왜 파일 내용을 읽지 않나요?

**A:** 
- 개인정보 보호 (이메일, 개인 문서 등)
- 회사 기밀 유지
- 성능 효율 (메타데이터만으로 충분)
- 규정 준수 (개인정보보호법, GDPR)

### Q2: 왜 Level 3은 기본값이 아닌가요?

**A:**
- 깊이 스캔은 시간 소요 (10초 이상)
- 사용자 선택 폴더까지 스캔하므로 동의 필수
- 대부분의 경우 Level 1로 충분
- 필요한 경우만 사용자가 선택

### Q3: 동의는 어디에 저장되나요?

**A:**
```
%LOCALAPPDATA%\HaehanAI\inventory\consent.json

예: C:\Users\skyjw\AppData\Local\HaehanAI\inventory\consent.json
```

### Q4: 스캔 결과는 서버로 전송되나요?

**A:** 
절대 아니요. 모든 데이터는:
- 사용자 PC에만 저장
- 로컬 JSON 파일
- 서버 전송 없음
- 사용자가 언제든 삭제 가능

### Q5: 스캔이 느려요

**A:**
- Level 1 (기본값): 5~10초
- Level 2 (사용자 폴더): 10~30초
- Level 3 (깊이 스캔): 30초 이상

느리면 Level 1 사용을 권장합니다.

### Q6: Registry 쓰기 호출이 있나요?

**A:** 
절대 없습니다. 사용:
- KEY_READ 플래그만 사용
- QueryValueEx() - 읽기
- EnumKey() - 읽기
- SetValue(), CreateKey() - 호출 없음

---

## 14. 보안 고려사항

### 14.1 위협 모델

| 위협 | 대책 |
|------|------|
| 파일 내용 노출 | 메타데이터만 수집 |
| 개인정보 노출 | 사용자명 마스킹, 경로 필터링 |
| 비밀번호 노출 | 민감 경로 제외 |
| Registry 손상 | KEY_READ 만 사용 |
| 서버 데이터 유출 | 로컬 저장만 |

### 14.2 코드 검증

```bash
# 파일 읽기 확인
grep -r "read()" agent/local_inventory/
# → stat() 만 사용, read() 없음

# Registry 쓰기 확인
grep -r "SetValue\|CreateKey" agent/local_inventory/
# → 호출 없음

# 파일 삭제 확인
grep -r "unlink\|remove" agent/local_inventory/
# → 호출 없음
```

---

## 15. 버전 히스토리

| 버전 | 날짜 | 변경사항 |
|------|------|---------|
| 1.0 | 2026-05-02 | 초기 릴리스 |

---

## 16. Action Registry 연결

### 16.1 등록된 액션

3개 action이 action_registry.py에 등록되어 있습니다.

| Action | 카테고리 | 리스크 | 동의 | 설명 |
|--------|---------|------|------|------|
| local_inventory.scan | inventory | MEDIUM | ✓ | 메타데이터 스캔 |
| local_inventory.status | inventory | LOW | ✗ | 저장된 inventory 조회 |
| local_inventory.compare | inventory | LOW | ✗ | inventory 변경 감지 |

**특징:**
- scan: privacy 영향으로 approval 필수
- status/compare: 저장된 데이터만 사용하므로 approval 불필요

### 16.2 Task Executor 핸들러

3개 handler가 task_executor.py의 _DISPATCH에 연결되어 있습니다.

- _run_local_inventory_scan() → run_local_inventory_scan()
- _run_local_inventory_status() → InventoryStore.load()
- _run_local_inventory_compare() → compare_inventory_snapshots()

### 16.3 사용 예시

```python
from agent.task_executor import execute_task

# Scan 실행 (approval_token 필수)
task = {
    "action": "local_inventory.scan",
    "approval_token": "approval_12345...",
    "scan_level": 1,
}
result = execute_task(task)

# Status 조회 (approval 불필요)
task = {
    "action": "local_inventory.status",
}
result = execute_task(task)

# Compare 실행 (approval 불필요)
task = {
    "action": "local_inventory.compare",
}
result = execute_task(task)
```

---

## 17. Hancom Discovery 통합

### 17.1 local_inventory 우선 사용

hancom/discovery/diagnostics.py의 diagnose_hancom_installation()이 local_inventory를 우선 확인합니다.

**흐름:**
1. local_inventory 로드 시도
2. 있으면 hancom 정보 추출 후 반환 (source: "inventory")
3. 없으면 기존 discovery 방식 사용 (source: "discovery")

### 17.2 Inventory → Discovery 변환

```python
# Inventory에서 추출
hancom = programs.get("hancom", {})

# Discovery 형식으로 변환
result = {
    "installed": True,
    "source": "inventory",
    "registry_status": {...},
    "com_status": {...},
    "installation_status": {...},
    "security_module": {...},
    "summary": f"한컴 {version} (Inventory)",
}
```

### 17.3 비표준 경로 해결

inventory 기반 discovery는 이미 저장된 경로를 사용하므로:
- 비표준 설치 경로 문제 자동 해결
- Program Files 외 위치 자동 감지
- 경로 재스캔 불필요

---

## 18. Change Watcher (변경 감지)

### 18.1 구현

change_watcher.py:
- InventoryDiff: 변경 요약 dataclass
- compare_inventory(): 두 inventory 비교
- format_diff_report(): 사람이 읽을 수 있는 보고서 생성

### 18.2 감지 대상

```python
InventoryDiff(
    added_programs: list[str],      # 신규 설치
    removed_programs: list[str],    # 삭제됨
    changed_programs: dict,          # 경로/버전 변경
    added_dlls: list[str],          # 신규 DLL
    removed_dlls: list[str],        # 삭제된 DLL
    has_changes: bool,              # 변경 여부
)
```

### 18.3 사용

```python
result = compare_inventory_snapshots()
# {
#   "ok": bool,
#   "diff": InventoryDiff dict,
#   "report": str,
#   "error": Optional[str],
# }
```

---

## 19. 테스트 결과

### 19.1 Unit Tests (40개, 모두 PASS)

- test_local_inventory_smoke.py: 8개 ✓
- test_action_registry_unit.py: 8개 ✓
- test_task_executor_unit.py: 24개 ✓

### 19.2 Smoke Test (Level 1)

```
✓ 결과: True
  스캔 레벨: 1
  스캔된 스코프: 5개
  탐지 프로그램: 3개+
  탐지 DLL 유형: 3개+
  ✓ 모든 안전 검증 PASS
```

### 19.3 안전 검증

- ✓ 파일 내용 read() 호출 없음
- ✓ Registry write 호출 없음
- ✓ 파일 삭제 호출 없음
- ✓ 서버 전송 없음
- ✓ Approval token 검증 (scan)

---

## 20. 참고 문서

- [Action Registry](../agent/action_registry.py) - 등록된 액션
- [Task Executor](../agent/task_executor.py) - 핸들러 구현
- [Diagnostics](../agent/local_inventory/diagnostics.py) - 스캔 오케스트레이션
- [Change Watcher](../agent/local_inventory/change_watcher.py) - 변경 감지
- [Hancom Discovery](../agent/hancom/discovery/diagnostics.py) - Hancom 통합
- [Test Cases](../agent/tests/test_local_inventory_smoke.py) - 테스트 사례

---

**최종 수정:** 2026-05-02  
**담당자:** AI Orchestrator Team

---

## 20. 앱 지도 (App Map) 통합

### 20.1 목적

저장된 inventory로부터 사용자 PC의 업무 프로그램을 분류하고
**AI 자동화 가능성을 판단**하여 사용자용 지도를 생성합니다.

### 20.2 동의 정책 개선

#### 기존 저장 inventory 조회 (재동의 불필요)

Level 1 스캔으로 생성된 inventory가 이미 저장되어 있으면:
- `local_inventory.status` — 승인 불필요
- `local_inventory.compare` — 승인 불필요
- `local_inventory.build_app_map` — **승인 필수** (메타데이터 분석)

#### 새 Level 2/3 스캔 (항상 명시 동의)

저장된 inventory가 없거나 새로 스캔하려면:
- `local_inventory.scan` (Level 2+) — **매번 명시 동의 필수**
- 사용자 폴더 스캔 시 범위 확인
- 깊이 스캔 시 소요 시간 안내

### 20.3 새로운 액션

#### local_inventory.build_app_map

```python
{
  "action": "local_inventory.build_app_map",
  "approval_token": "...",  # 필수
  "inventory_path": "...",  # 선택
}
```

결과:
```python
{
  "summary": {
    "total_apps": 12,
    "automation_ready": 3,
    "setup_required": 2,
  },
  "detected_apps": {...},
  "capabilities": {...},
  "recommendations": [...],
}
```

**특징:**
- risk_level: MEDIUM (메타데이터 분석이지만 PC 정보)
- requires_approval: True
- 저장 경로: `%LOCALAPPDATA%\HaehanAI\inventory\local_app_map.json`

#### local_inventory.app_map_status

```python
{
  "action": "local_inventory.app_map_status",
  "app_map_path": "...",  # 선택
}
```

**특징:**
- risk_level: LOW (저장된 데이터만 조회)
- requires_approval: False (재사용 가능)

### 20.4 자동화 가능성 판단

| 프로그램 | 설치 | COM | 보안 | 준비 |
|---------|------|-----|------|------|
| Excel | ✓ | ✓ | - | ✓ |
| 한컴 | ✓ | ✓ | ✗ | ✗ |
| AutoCAD | ✓ | ? | - | ? |

**판단 기준:**
1. 프로그램 설치 확인
2. COM 클래스 등록 확인
3. 보안모듈/라이선스 확인
4. AI 제어 능력 계산

### 20.5 권장사항 생성

**자동 감지:**
```
- 보안모듈 미등록 → "한컴: 보안모듈 등록이 필요합니다"
- COM 미확인 → "AutoCAD: COM 확인이 필요합니다"
- 자동화 불가 → "전문가 검토가 필요합니다"
```

### 20.6 사용 흐름

```python
# 1. 기존 inventory 확인
store = InventoryStore()
inventory = store.load()

# 2. App Map 생성
from agent.local_inventory.app_map import build_app_map
app_map = build_app_map(inventory)

# 3. 사용자에게 표시
summary = app_map["summary"]
recommendations = app_map["recommendations"]

# UI에서:
print(f"자동화 가능: {summary['automation_ready']}개")
print(f"설정 필요: {summary['setup_required']}개")
for rec in recommendations:
    print(f"⚠ {rec}")
```

### 20.7 자세한 설명

[로컬 앱 지도 기준 문서](./local_app_map_baseline.md) 참조.

---

## 21. 버전 히스토리 (업데이트)

| 버전 | 날짜 | 변경사항 |
|------|------|---------|
| 1.2 | 2026-05-02 | App Map 통합, build_app_map/app_map_status 액션 추가 |
| 1.1 | 2026-05-02 | Action registry/executor 연결, Hancom discovery 통합, change_watcher 구현 |
| 1.0 | 2026-05-02 | 초기 릴리스 |
