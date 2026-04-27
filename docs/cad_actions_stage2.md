# CAD 액션 편입 (2단계)

## 1. 목표

POC 실증이 끝난 `cad_com_connector` 를 기존 `action_registry` /
`approval_policy` / `task_executor` / `local_agent` 파이프라인에
**최소 범위로** 편입한다.

이 단계의 목표는 "실제로 검증된 CAD COM 기능이 기존 자동화 시스템 안
에서 안전한 액션 3종으로 호출 가능해지는 것" 이다. MCP 공개, 고급 도면
분석, block/layer 대량 편집, 서버형 CAD 자동화는 **이번 단계의 목표가
아니다.**

## 2. 지원 액션 3종

| Action | category | risk | read_only | requires_file_path | 비고 |
|--------|----------|------|-----------|--------------------|------|
| `cad.health` | `cad` | `low` | true | **false** | AutoCAD 사용 가능 여부 점검 |
| `cad.open_info` | `cad` | `low` | true | true | DWG 열어 기본 정보만 읽음 |
| `cad.add_text_save_as` | `cad` | `medium` | false | true | ModelSpace 에 Text 1개 추가 → 반드시 save_as |

### 2.1 cad.health

AutoCAD 가 실제로 Dispatch 되는지, 어떤 ProgID·버전이 응답하는지만
확인한다. 문서를 열지 않고 파일 경로도 받지 않는다.

**입력**
```json
{ "action": "cad.health", "visible": false }
```
`visible` 은 선택 (Dispatch 직후 바로 Quit 되므로 보통 생략).

**응답 예 (성공)**
```json
{
  "ok": true,
  "data": {
    "platform": "win32",
    "cad_available": true,
    "prog_id": "AutoCAD.Application.24.3",
    "version": "24.3s (LMS Tech)",
    "product_name": "AutoCAD",
    "lt_or_limited": false
  },
  "error": null
}
```

**응답 예 (실패 — 비 Windows)**
```json
{
  "ok": false,
  "data": {
    "platform": "linux",
    "cad_available": false
  },
  "error": "cad_com_not_supported"
}
```

### 2.2 cad.open_info

대상 DWG 를 연 뒤 `Name` / `FullName` / `ModelSpace.Count` /
`ActiveLayout.Name` 만 돌려주고 닫는다. **저장하지 않는다.** 원본 파일은
수정되지 않는다.

**입력**
```json
{
  "action": "cad.open_info",
  "file_path": "C:\\tmp\\cad_poc\\sample.dwg",
  "visible": false
}
```

**응답 예 (성공)**
```json
{
  "ok": true,
  "data": {
    "name": "sample.dwg",
    "full_name": "C:\\tmp\\cad_poc\\sample.dwg",
    "active_layout": "Model",
    "model_space_count": 0
  },
  "error": null
}
```

### 2.3 cad.add_text_save_as

ModelSpace 에 **단일 Text 엔터티 하나만** 추가하고, **반드시 다른 이름으로
저장(save_as)** 한다. `save_as == file_path` 는 executor 레벨에서
`cad_overwrite_forbidden` 으로 거부된다.

**입력**
```json
{
  "action": "cad.add_text_save_as",
  "file_path": "C:\\tmp\\cad_poc\\sample.dwg",
  "save_as":   "C:\\tmp\\cad_poc\\out.dwg",
  "text": "POC_OK",
  "x": 0.0, "y": 0.0, "z": 0.0, "height": 2.5,
  "visible": false,

  "approval_token": "...",
  "approved_by": "alice"
}
```
`risk_level=medium` 이므로 **기존 정책대로** `approval_token` 이 없으면
`approval_policy` 에서 `approval_required` 로 거부된다.

**응답 예 (성공)**
```json
{
  "ok": true,
  "data": {
    "document_opened": true,
    "added_entity": {
      "type": "Text", "text": "POC_OK",
      "handle": "8B", "object_name": "AcDbText"
    },
    "saved_as": "C:\\tmp\\cad_poc\\out.dwg",
    "closed": true,
    "quit": true
  },
  "error": null
}
```

## 3. 전제 조건

- Windows 10/11 데스크톱 PC (서버 Windows 가 아닌 실제 사용자 PC)
- **정식 AutoCAD** 설치 (2020 이상 권장, 본 POC 실증 버전은 2024)
- **AutoCAD LT / Mac 은 이번 단계 지원 대상이 아니다.** LT 는 ActiveX 가
  차단되어 `ModelSpace` 접근 자체가 실패한다. `cad.health` 가
  `lt_or_limited=true` 를 돌려주면 write 액션은 호출하지 말 것.
- Python 3.10+ / `pywin32>=306` (Windows 에서만 설치, `requirements.txt`
  의 `sys_platform == "win32"` 환경 마커로 분리).
- 라이선스 activation 이 끝난 계정에서 AutoCAD 를 **최소 한 번 수동
  실행** 한 이후여야 COM 이 정상 응답한다.

## 4. approval / policy 정리

이번 단계는 기존 정책을 **그대로 사용한다 (완화 없음)**.

- `action_registry.ActionMeta` 에 `requires_file_path: bool = True` 필드
  추가 (기본값 True — 기존 모든 액션의 의미 그대로).
  - `cad.health` 만 `requires_file_path=False` 로 설정되어 approval_policy
    의 file_path 강제 검사를 통과한다.
- `policy.ALLOWED_ACTIONS` 에 `cad.*` 3종 추가. 기존 정책의 whitelist
  계약은 유지.
- `approval_policy.evaluate()` 는 `meta.requires_file_path` 를 조회해
  cad.health 에만 파일 경로 요구를 면제. 나머지 로직은 변경 없음.
- `cad.add_text_save_as` 는 Excel 의 `excel.write_cell` / `excel.save_as`
  와 같은 medium risk — 기존 approval_token 요구가 그대로 적용된다.
- `file_policy.resolve_output_path` 는 `save_as == source_path` 케이스를
  `output_path_not_allowed` 로 이미 거르고 있다. executor 에서는
  단독 호출 경로 방어용으로 `cad_overwrite_forbidden` 을 별도 반환한다.

## 5. executor 연결 방식

`agent/task_executor.py` 에서 동일 `_DISPATCH` dict 에 CAD 핸들러를 등록.

- `cad.health`           → `cad_com_connector.is_cad_available()`
- `cad.open_info`        → `open_cad_app` → `open_document` →
  `get_document_info` → `close_document` → `quit_cad`
- `cad.add_text_save_as` → `open_cad_app` → `open_document` →
  `add_test_text` → `save_document_as` → `close_document` → `quit_cad`

모든 핸들러는 `finally` 로 `close_document` / `quit_cad` 을 호출해
프로세스 잔존을 최소화한다. COM 호출 실패는 connector 가 이미 CAD_* /
FILE_* 표준 코드를 돌려주므로 executor 에서 추가 변환하지 않는다.

POC 에서 확인된 **단일 Dispatch 원칙** (is_cad_available + open_cad_app
순차 호출 시 RPC_E_SERVERFAULT 발생) 을 executor 에서도 유지: cad.open_info
와 cad.add_text_save_as 는 `is_cad_available()` 을 호출하지 않는다.

## 6. 에러 코드

이번 단계에서 신규 추가된 CAD executor 레벨 코드:

| 코드 | 의미 |
|------|------|
| `cad_invalid_path` | 절대경로가 아니거나 허용 디렉터리 밖 (예약) |
| `cad_overwrite_forbidden` | `save_as == file_path` — 원본 overwrite 시도 |
| `cad_invalid_argument` | 텍스트 타입/길이 또는 좌표·높이 타입 검증 실패 |

POC 단계에서 이미 등록된 코드 (connector 가 반환):
`cad_com_not_supported`, `cad_com_dispatch_failed`, `cad_app_not_found`,
`cad_document_open_failed`, `cad_document_info_failed`,
`cad_entity_add_failed`, `cad_document_save_failed`.

## 7. 금지되는 CAD 작업 (이번 단계)

- erase / delete / explode / purge
- plot / publish
- 임의 `SendCommand` 기반 범용 실행
- block redefine, layer mass change, object bulk edit
- 원본 `save` (overwrite) — write 는 오직 `save_as` 로만 허용
- command injection 류 호출

이 중 하나라도 요구되면 다음 단계 설계에서 별도 승인을 받아야 한다.

## 8. 예시 payload

로컬 agent 가 서버에서 받는 task dict 형식 예시 (id/action + CAD 필드).

```json
{
  "id": "t-001",
  "action": "cad.health"
}
```

```json
{
  "id": "t-002",
  "action": "cad.open_info",
  "file_path": "C:\\tmp\\cad_poc\\sample.dwg",
  "visible": false
}
```

```json
{
  "id": "t-003",
  "action": "cad.add_text_save_as",
  "file_path": "C:\\tmp\\cad_poc\\sample.dwg",
  "save_as":   "C:\\tmp\\cad_poc\\out.dwg",
  "text": "POC_OK",
  "x": 0.0, "y": 0.0, "z": 0.0, "height": 2.5,
  "visible": false,
  "approval_token": "tok-...",
  "approved_by": "alice"
}
```

## 9. 자동화 테스트 범위

- `agent/tests/test_task_executor_cad.py` — CAD 액션의 dispatch/검증/
  finally 경로를 mock 스텁으로 검증 (실 AutoCAD 의존 없음).
- `agent/tests/test_task_executor_unit.py` — `supported_actions` 에
  cad.* 3종이 포함됨을 확인.
- `agent/tests/test_action_standardization.py` — registry & policy
  whitelist 에 cad.* 3종 포함을 확인, CAD 메타 플래그 확인.
- `agent/tests/test_cad_com_connector_unit.py` (기존) — connector 자체
  단위 테스트는 POC 단계에서 작성된 상태를 유지.

실제 AutoCAD 상 실행 확인은 기존 `docs/cad_com_poc.md` §6 수동 절차를
그대로 사용한다. CI 강제 항목으로 만들지 않는다.

## 10. 아직 미포함 범위 (차기 단계)

- MCP 도구로의 공개
- block 삽입, 레이어 편집, 속성 대량 변경, 경로 편집
- 도면 분석·치수 추출·리비전 비교
- 멀티 도면 배치 처리 / AutoCAD 프로세스 풀
- plot / PDF export
- DXF 변환 파이프라인
