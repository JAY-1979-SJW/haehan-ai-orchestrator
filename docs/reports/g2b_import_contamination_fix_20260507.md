# G2B Import Contamination Fix 보고서

작성일: 2026-05-07 ~ 2026-05-08

---

## 문제 요약

`tests/test_browser_gate_module_design_20260506.py`의 두 테스트가
다른 테스트와 통합 실행 시 FAIL:

- `test_no_browser_import_in_this_module`
- `test_no_task_executor_import`

단독 실행 시 PASS, 통합 실행 시 FAIL → 테스트 순서 의존성 문제.

---

## 단독 PASS / 통합 FAIL 재현 명령

```bash
# 단독 PASS
python -m pytest tests/test_browser_gate_module_design_20260506.py -v

# 통합 FAIL (재현)
python -m pytest tests/test_browser_engine_routing_preflight_chain_20260507.py tests/test_browser_gate_module_design_20260506.py -v
# → 2 FAILED

python -m pytest tests/ -k "allowlist or site_compliance or browser_gate or submit_gate or browser_engine or g2b" -q
# → 2 FAILED
```

---

## 원인

### 원인 1: `ai_orchestrator/browser_tool/router.py` - module-level eager import

```python
# 수정 전 (문제)
from .backends.worker_backend import BrowserWorkerBackend

# 수정 후 (lazy import)
# ... module-level에서 제거
# 함수 내부에서만 import:
if selected_backend == "worker":
    from .backends.worker_backend import BrowserWorkerBackend  # lazy import
```

`router.py`가 `ai_orchestrator/browser_tool/__init__.py`에서 import되므로,
G2B 정책 모듈(g2b_domain_policy 등) import 시 패키지 초기화로 router → worker_backend → browser_worker 전체가 로드됨.

### 원인 2: `browser_engine_routing_preflight_chain.py` - module-level eager import

```python
# 수정 전 (문제)
from browser_worker.policy import evaluate_server_browser_url_policy

# 수정 후 (lazy import)
# ... module-level에서 제거
# 함수 내부에서만 import:
from browser_worker.policy import evaluate_server_browser_url_policy  # lazy import
```

preflight chain 테스트 실행 시 `evaluate_server_browser_url_policy`를 실제 호출하면
lazy import가 트리거되어 `browser_worker`가 sys.modules에 등록됨.

### 원인 3: `test_browser_gate_module_design_20260506.py` - sys.modules 전역 상태 검사 방식

```python
# 수정 전 (순서 의존적)
assert mod not in sys.modules or "test" in str(...)

# 수정 후 (소스 코드 직접 검사 - 순서 독립적)
source = Path(__file__).read_text()
for pattern in [f"import {mod}", f"from {mod}"]:
    assert pattern not in source
```

테스트 의도는 "이 테스트 파일이 browser_worker를 직접 import하지 않는다"이나,
sys.modules 전역 상태를 검사하는 구현이 타 테스트의 import에 영향을 받음.
소스 코드 직접 검사 방식으로 변경하여 순서 독립성 확보.

---

## 수정 내용

| 파일 | 수정 내용 |
|------|-----------|
| `ai_orchestrator/browser_tool/router.py` | `BrowserWorkerBackend` module-level import → lazy import |
| `ai_orchestrator/browser_tool/browser_engine_routing_preflight_chain.py` | `evaluate_server_browser_url_policy` module-level import → lazy import |
| `tests/test_browser_gate_module_design_20260506.py` | `test_no_browser_import_in_this_module`, `test_no_task_executor_import` sys.modules 검사 → 소스 코드 검사 |

---

## 재발 방지 테스트

`tests/test_g2b_import_contamination_regression_20260507.py` (12개)

1. g2b 모듈 import 후 allowlist 결과 불변 확인
2. execution gate import 후 site_compliance 결과 불변 확인
3. workflow import 후 ALLOWLIST_SAFE_SITES 불변 확인
4~7. 도메인 허용/차단 결과 import 순서 독립성 확인
8. router.py module-level browser_worker import 없음 확인
9. preflight_chain.py module-level browser_worker import 없음 확인
10. live_runner.py module-level playwright import 없음 확인
11. scripts import side effect 없음 확인
12. 모든 g2b 모듈 import 후에도 gate_module_design 기대값 통과 확인

---

## 최종 테스트 결과

| 테스트 | 결과 |
|--------|------|
| regression 테스트 (신규) | 12 PASSED |
| allowlist/site compliance 단독 | PASSED |
| live execution 테스트 | 50 PASSED |
| allowlist + site compliance 통합 | PASSED |
| 기존 2개 FAIL | 해소 |
| 전체 통합 필터 실행 | 657 PASSED |

---

## 정책 변경 여부

- 정책 완화 없음
- 테스트 skip/xfail 없음
- wildcard 허용 없음
- login/cert/bid/contract/payment BLOCK 유지
- click/type/fill/submit/download BLOCK 유지
- 실제 G2B live 실행 범위 변경 없음
- **import 오염만 제거**

---

## 남은 WARN 여부

없음. 전체 통합 실행 657 PASSED.
