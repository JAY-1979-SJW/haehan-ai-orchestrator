# 비즈니스 애플리케이션 지도 (LOCAL APP MAP BASELINE)

## 1. 개요

### 1.1 정의

**로컬 비즈니스 앱 지도**는 사용자 PC의 설치된 업무 프로그램을 **메타데이터 기반**으로 분류하고, **AI 자동화 가능성**을 판단하는 시스템입니다.

```
┌─────────────────────────────────────────────────────┐
│        비즈니스 애플리케이션 지도                    │
├─────────────────────────────────────────────────────┤
│                                                     │
│  Inventory ─→ 프로그램 분류 ─→ AI 능력 판단 ─→ 사용자 지도 │
│   (메타) ↓      ↓           ↓      JSON+요약
│                                                     │
│  ✓ 설치 프로그램 정보                              │
│  ✓ COM 클래스 등록 상태                            │
│  ✓ 파일 확장자 연결                                │
│  ✓ 바로가기 메타데이터                            │
│                                                     │
│  ✗ 파일 내용                                       │
│  ✗ 프로그램 실행                                   │
│  ✗ Registry 쓰기                                   │
│  ✗ 서버 전송                                       │
│                                                     │
└─────────────────────────────────────────────────────┘
```

---

## 2. 아키텍처

### 2.1 모듈 구성

```
agent/local_inventory/app_map/
├── __init__.py                      # 진입점
├── software_catalog.py              # 프로그램 정규화
├── shortcut_scanner.py              # 바로가기 메타데이터
├── file_association_scanner.py      # 파일 확장자 연결
├── portable_app_detector.py         # exe 후보 감지
├── capability_mapper.py             # AI 능력 판단
└── app_map_builder.py               # 통합 + 요약 생성
```

### 2.2 데이터 흐름

```python
# 1. Inventory 로드
inventory = InventoryStore().load()

# 2. 프로그램별 AI 능력 분석
from agent.local_inventory.app_map import build_app_map
app_map = build_app_map(inventory)

# 3. 결과
{
  "generated_at": "2026-05-02T10:30:00Z",
  "scan_source": "inventory",
  "summary": {
    "total_apps": 12,
    "automation_ready": 3,
    "setup_required": 2,
  },
  "detected_apps": {
    "hancom": {"name": "...", "category": "hancom", ...},
    "excel": {...},
    ...
  },
  "capabilities": {
    "hancom": {
      "automation_ready": false,
      "setup_required": true,
      "setup_reason": "security_module_not_registered",
    },
    ...
  },
  "recommendations": [
    "한컴: 보안모듈 등록이 필요합니다",
    ...
  ],
}
```

---

## 3. 프로그램 카테고리

### 3.1 분류

| 카테고리 | 예시 | AI 제어 가능 |
|---------|------|----------|
| **office_excel** | Microsoft Excel | ✓ COM |
| **hancom** | HNC HOffice | ✓ COM (보안모듈 필수) |
| **cad** | AutoCAD | ✓ COM (확인 필요) |
| **pdf** | PDF Reader | ✓ 내보내기 |
| **browser** | Chrome, Firefox | ✓ 웹 조작 |
| **archive** | WinRAR, 7-Zip | ✗ 자동화 제한 |
| **design** | Photoshop, Sketch | ✗ 자동화 제한 |
| **lighting** | 조명계산 프로그램 | ✗ 전문가 검토 필요 |

---

## 4. 능력 판단 (Capability Mapping)

### 4.1 한컴 (Hancom)

**설치 확인:**
- Registry: `HKEY_LOCAL_MACHINE\SOFTWARE\HNC`
- Inventory programs.hancom.installed

**COM 확인:**
```python
{
  "HWPFrame.HwpObject": True,
  "HWPFrame.HwpObjForm": True,
}
```

**보안모듈 확인:**
- `programs.hancom.security_module_registered`
- False → `setup_required: true, setup_reason: "security_module_not_registered"`

**AI 기능:**
```python
capabilities = [
  "hwp_read",
  "hwp_to_hwpx_convert",
  "hwpx_analysis",
  "pdf_export",
]
```

**자동화 준비:**
- `automation_ready = has_com and not setup_required`

### 4.2 Excel

**설치 확인:**
- Registry: `HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Office`
- Inventory programs.excel.installed

**COM 확인:**
```python
{
  "Excel.Application": True,
}
```

**AI 기능:**
```python
capabilities = [
  "read_cell",
  "write_cell",
  "read_sheet",
  "write_formula",
  "save_as",
]
```

**자동화 준비:**
- `automation_ready = has_com`

### 4.3 AutoCAD

**설치 확인:**
- Registry: `HKEY_LOCAL_MACHINE\SOFTWARE\Autodesk`
- Inventory programs.cad.installed

**COM 확인:**
```python
{
  "AutoCAD.Application": True,
}
```

**AI 기능:**
```python
capabilities = [
  "open_drawing",
  "add_text",
  "save_drawing",
]
```

**자동화 준비:**
- `automation_ready = has_com`
- 미등록: `setup_reason: "COM_not_confirmed"`

---

## 5. 사용자용 요약 생성

### 5.1 요약 정보

```python
{
  "summary": {
    "total_apps": 12,              # 설치된 프로그램 수
    "automation_ready": 3,         # AI 자동화 가능 프로그램
    "setup_required": 2,           # 설정 필요
    "not_detected": 0,             # 미설치
    "categories": {
      "office_excel": 1,
      "hancom": 1,
      "cad": 1,
      ...
    }
  }
}
```

### 5.2 권장사항

```python
{
  "recommendations": [
    "한컴: 보안모듈 등록이 필요합니다 (자동화 활성화를 위해)",
    "AutoCAD: COM 확인이 필요합니다",
    ...
  ]
}
```

### 5.3 저장 위치

```
%LOCALAPPDATA%\HaehanAI\inventory\local_app_map.json
```

---

## 6. 액션 등록

### 6.1 local_inventory.build_app_map

**역할:** 저장된 inventory로부터 app_map 빌드

```python
{
  "action": "local_inventory.build_app_map",
  "approval_token": "...",  # 필수
  "inventory_path": "...",  # 선택
}
```

**응답:**
```python
{
  "ok": true,
  "data": {
    "app_map": {...},
    "saved_to": "...",
  },
}
```

**특징:**
- read_only: True
- requires_approval: True (메타데이터 분석이지만 PC 정보 활용)
- risk_level: MEDIUM

### 6.2 local_inventory.app_map_status

**역할:** 저장된 app_map 상태 조회

```python
{
  "action": "local_inventory.app_map_status",
  "app_map_path": "...",  # 선택
}
```

**응답:**
```python
{
  "ok": true,
  "app_map": {...},
}
```

**특징:**
- read_only: True
- requires_approval: False (저장된 데이터만 조회)
- risk_level: LOW

---

## 7. 안전성

### 7.1 보증

| 항목 | 보증 |
|------|------|
| **파일 내용 읽기** | 없음 ✓ |
| **Registry 쓰기** | 없음 ✓ |
| **프로그램 실행** | 없음 ✓ |
| **서버 전송** | 없음 ✓ |
| **파일 삭제** | 없음 ✓ |

### 7.2 메타데이터만 수집

```python
# ✓ 가능
- 파일 경로
- 파일 크기
- 수정 시간
- COM 클래스명
- Registry 값 (read-only)
- 바로가기 이름/경로 (내용 X)

# ✗ 불가능
- 파일 내용
- 문서 정보
- 브라우저 히스토리
- 비밀번호/토큰
```

### 7.3 경로 필터링

민감한 경로는 자동 제외:
```
password, credential, secret, token, api_key,
.ssh, .aws, .kube, .git
```

---

## 8. 상용화 UI 흐름

### 8.1 초기화면

```
┌──────────────────────────────┐
│  업무 프로그램 지도           │
│                              │
│  이 PC의 소프트웨어를       │
│  AI 자동화 가능성과 함께    │
│  표시합니다.                 │
│                              │
│  [지도 생성]                │
└──────────────────────────────┘
```

### 8.2 결과화면

```
┌──────────────────────────────┐
│  ✓ 자동화 가능               │
│  • Microsoft Excel           │
│  • HNC HOffice (보안모듈 필) │
│                              │
│  ⚠ 설정 필요                │
│  • 한컴 보안모듈 등록       │
│                              │
│  ✗ 자동화 불가              │
│  • AutoCAD (COM 확인 필요)   │
│                              │
│  [상세보기] [설정] [닫기]    │
└──────────────────────────────┘
```

### 8.3 상세정보

```
┌────────────────────────────────┐
│  한컴 (HNC HOffice 2014)        │
│                                │
│  설치 상태: ✓ 설치됨           │
│  버전: 14.0.2000               │
│                                │
│  COM 등록:                     │
│  ✓ HWPFrame.HwpObject         │
│  ✓ HWPFrame.HwpObjForm        │
│                                │
│  자동화 가능:                 │
│  ✓ HWP 읽기                   │
│  ✓ HWP→HWPX 변환             │
│  ✗ PDF 내보내기 (보안모듈 필) │
│                                │
│  [설정 도움말] [닫기]          │
└────────────────────────────────┘
```

---

## 9. 기술 스택

### 9.1 의존성

```python
# 표준 라이브러리
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime
import json
import winreg  # Windows only

# 로컬 모듈
from .local_inventory.inventory_store import InventoryStore
from .local_inventory.app_map import build_app_map
```

### 9.2 호출 예시

```python
# 1. Inventory 스캔 (별도)
from agent.local_inventory.diagnostics import run_local_inventory_scan
inventory = run_local_inventory_scan(...)

# 2. App Map 생성
from agent.local_inventory.app_map import build_app_map
app_map = build_app_map(inventory)

# 3. 저장
import json
from pathlib import Path
path = Path.home() / "AppData" / "Local" / "HaehanAI" / "inventory" / "local_app_map.json"
with open(path, "w") as f:
    json.dump(app_map, f, indent=2)
```

---

## 10. 제한사항

### 10.1 Level 1 Inventory만 사용

- Program Files 메타데이터만 분석
- 사용자 폴더 깊이 스캔 안 함
- Level 2/3 거부

### 10.2 COM 감지 제한

- Registry 기반 COM 클래스 확인
- 실제 COM 호출 테스트 안 함
- "등록되었음" ≠ "사용 가능" (호환성 검사 필요)

### 10.3 프로그램 실행 불가

- 설치 경로 확인만 (실행 불가)
- 버전 자동 감지 제한 (Registry 값만 사용)
- 런타임 상태 미반영

---

## 11. 향후 확장

### 11.1 Level 2/3 지원

```python
# 향후: 사용자가 원할 경우
scan_level = ScanLevel.USER_FOLDERS
user_paths = ["C:\\Users\\...", ...]  # 사용자 선택
app_map = build_app_map_with_scan(scan_level, user_paths)
```

### 11.2 실시간 모니터링

```python
# 향후: 설치/삭제 감지
from agent.local_inventory.change_watcher import InventoryDiff
diff = compare_inventory_snapshots()
if diff.added_programs:
    app_map = rebuild_app_map()
```

### 11.3 자동화 점수

```python
# 향후: 자동화 복잡도 평가
{
  "automation_score": 8,  # 1~10
  "difficulty": "low",
  "estimated_setup_hours": 0.5,
}
```

---

## 12. FAQ

### Q: 왜 실제로 프로그램을 실행하지 않나요?

**A:** 
- 보안 위험 (악성 프로그램 가능성)
- 성능 영향 (느린 실행 시간)
- 부작용 (파일 생성, 설정 변경)
- 메타데이터만으로 충분함

### Q: COM 등록은 사용 가능을 보장하나요?

**A:** 아니요. Registry에 등록되었다는 의미일 뿐, 실제 호출 가능성은 별도 검사 필요.

### Q: Inventory 없이 App Map을 생성할 수 있나요?

**A:** 아니요. Inventory 데이터가 필수입니다. (또는 새로 스캔)

### Q: 파일 확장자 연결도 메타데이터만 사용하나요?

**A:** 예. Registry의 확장자 → ProgID → 실행 경로 매핑만 사용.

---

## 13. 보안 고려사항

### 13.1 위협 모델

| 위협 | 대책 |
|------|------|
| 파일 내용 노출 | 메타데이터만 |
| 개인정보 노출 | 사용자명 마스킹 |
| 비밀번호 노출 | 민감 경로 제외 |
| Registry 손상 | KEY_READ만 사용 |
| 서버 유출 | 로컬 저장만 |

### 13.2 코드 검증

```bash
# 파일 읽기 확인
grep -r "\.read()\|open.*read" agent/local_inventory/app_map/
# → read는 JSON 저장 시만

# Registry 쓰기 확인
grep -r "SetValue\|CreateKey" agent/local_inventory/app_map/
# → 없음

# 프로그램 실행 확인
grep -r "subprocess\|os.system" agent/local_inventory/app_map/
# → 없음
```

---

## 14. 버전 히스토리

| 버전 | 날짜 | 변경사항 |
|------|------|---------|
| 1.0 | 2026-05-02 | 초기 릴리스 |

---

## 15. 참고

- [로컬 자산 인벤토리](./local_inventory_baseline.md) - Inventory 스캔 시스템
- [Action Registry](../agent/action_registry.py) - 등록된 액션
- [Task Executor](../agent/task_executor.py) - 핸들러 구현

---

**최종 수정:** 2026-05-02  
**담당자:** AI Orchestrator Team
