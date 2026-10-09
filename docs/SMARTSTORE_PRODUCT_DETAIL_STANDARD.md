# 스마트스토어 제품 상세페이지 고도화 기준서

> 작성일: 2026-05-29  
> 대상: `ai_orchestrator/connectors/smartstore_router.py` / `admin-web/src/app/naver/smartstore/` / `scripts/naver/smartstore/`  
> 레이어: L3(Connector) / L6(Workflow) / L8(Router) / L9(UI)

---

## 1. 현황 진단

### 1-1. 구현 완료

| 영역 | 항목 | 비고 |
|------|------|------|
| 백엔드 | 상품 목록 수집/조회 (`/smartstore/products`) | CDP 자동화 |
| 백엔드 | 주문·정산·리뷰·통계·마케팅 수집/조회 | CDP 자동화 |
| 백엔드 | 상품 등록 5단계 가이드 (`product-register-guide`) | 정적 |
| 백엔드 | 액션 카탈로그 (`/smartstore/status`) | 정적 |
| 프론트 | 7탭 UI (대시보드/상품/주문/리뷰/통계/마케팅/카탈로그) | 완성 |
| 프론트 | 수집 → 조회 워크플로우 | 완성 |

### 1-2. 미구현 (고도화 대상)

| 영역 | 항목 | 우선순위 |
|------|------|---------|
| 백엔드 | **개별 상품 상세 조회** | P0 |
| 백엔드 | **상품 필드별 편집** (상품명/가격/재고/설명) | P0 |
| 백엔드 | **상품 이미지 조회** | P1 |
| 백엔드 | **상품 옵션 조회/편집** | P1 |
| 백엔드 | **재고 실시간 동기화** | P1 |
| 백엔드 | **상품 상태 변경** (판매중/품절/숨김) | P2 |
| 프론트 | 상품 상세 드로어/모달 | P0 |
| 프론트 | 인라인 필드 편집 UX | P1 |
| 프론트 | 상품별 통계 연결 | P2 |

---

## 2. 아키텍처 기준

### 2-1. 레이어 구조

```
L9  admin-web/src/app/naver/smartstore/products/
    ├── page.tsx                    ← 상품 목록 (기존)
    ├── [productId]/page.tsx        ← 상품 상세 (신규)
    └── ProductDetailDrawer.tsx     ← 상세 드로어 컴포넌트 (신규)

L8  ai_orchestrator/connectors/smartstore_router.py
    ├── GET  /smartstore/products                ← 기존
    ├── GET  /smartstore/products/{product_id}   ← 신규 (상세)
    ├── POST /smartstore/products/{product_id}/collect  ← 신규 (CDP 수집)
    └── PUT  /smartstore/products/{product_id}   ← 신규 (편집, approval_gated)

L6  ai_orchestrator/workflows/smartstore_product_workflow.py  ← 신규
    ├── collect_product_detail()    ← CDP로 상세 수집
    ├── patch_product_field()       ← 필드 편집 (approval_gated)
    └── sync_product_stock()        ← 재고 동기화

L3  scripts/naver/smartstore/product/
    ├── detail_collector.py         ← 신규: 상세 CDP 추출
    ├── field_editor.py             ← 신규: 필드 편집 자동화
    └── models.py                   ← 기존: 데이터 모델 확장
```

### 2-2. 의존성 방향

```
L9(UI) → L8(Router) → L6(Workflow) → L3(Connector/CDP)
                                    → L7(data/smartstore/)
```

금지:
- Router에서 직접 Playwright 호출
- Workflow에서 UI 모델 import
- 서로 다른 도메인 간 직접 호출

---

## 3. 데이터 모델 표준

### 3-1. 상품 상세 스키마 (`ProductDetail`)

```python
# scripts/naver/smartstore/product/models.py 에 추가

@dataclass
class ProductDetail:
    # ── 식별자 ──────────────────────────────
    product_id: str           # 스마트스토어 상품 번호
    channel_product_id: str   # 채널 상품 번호

    # ── 기본 정보 ────────────────────────────
    name: str                 # 상품명 (최대 100자)
    category: str             # 카테고리 전체 경로
    status: str               # SALE / OUTOFSTOCK / SUSPENSION / CLOSE

    # ── 가격·재고 ────────────────────────────
    price: int                # 판매가 (원)
    original_price: int | None  # 정가 (할인 전)
    stock: int                # 재고 수량
    min_purchase: int         # 최소 구매 수량
    max_purchase: int | None  # 최대 구매 수량

    # ── 이미지 ──────────────────────────────
    main_image_url: str | None   # 대표 이미지 URL
    images: list[str]            # 추가 이미지 URL 목록

    # ── 상세 설명 ────────────────────────────
    description_html: str | None  # 상세설명 HTML
    summary: str | None           # 상품 요약

    # ── 옵션 ────────────────────────────────
    has_options: bool
    options: list[ProductOption]

    # ── 배송 ────────────────────────────────
    delivery_fee: int        # 배송비 (0 = 무료)
    delivery_method: str     # DELIVERY / VISIT_RECEIPT / QUICK

    # ── 통계 (수집 가능 시) ──────────────────
    view_count: int | None
    order_count: int | None
    review_count: int | None
    review_score: float | None

    # ── 메타 ────────────────────────────────
    registered_at: str | None
    updated_at: str | None
    collected_at: str          # 수집 시각 (ISO)
    source: str                # "cdp" | "cache"


@dataclass
class ProductOption:
    option_name: str           # 옵션명 (예: "색상")
    option_value: str          # 옵션값 (예: "블랙")
    price_diff: int            # 추가 가격
    stock: int                 # 옵션별 재고
    option_id: str | None
```

### 3-2. 편집 요청 스키마 (`ProductPatch`)

```python
@dataclass
class ProductPatch:
    product_id: str
    fields: dict[str, Any]    # 변경할 필드만 포함 (partial update)
    reason: str               # 편집 사유 (감사 로그용)
    dry_run: bool = True      # 기본 dry-run

# 허용 편집 필드 (approval_gated 아닌 것)
PATCHABLE_FIELDS_SAFE = {"price", "stock", "status"}

# approval_gated 필드 (토큰 필수)
PATCHABLE_FIELDS_GATED = {"name", "category", "description_html", "images", "options"}
```

### 3-3. 캐시 파일 위치

```
data/smartstore/
├── products.json                        # 목록 (기존)
├── products/
│   ├── {product_id}.json                # 상세 캐시 (신규)
│   └── {product_id}_history.jsonl       # 편집 이력 (신규)
└── product_index.json                   # product_id → 이름 인덱스 (신규)
```

---

## 4. CDP 수집 기준

### 4-1. 상세 수집 절차

```
1. 세션 확인: ensure_naver_login(page) → LOGGED_IN 확인
2. 목록 페이지 진입: sell.smartstore.naver.com/#/products/list
3. 상품 클릭: product_id 기반 행 탐색 → 클릭
4. 상세 페이지 로드 대기: networkidle or 특정 셀렉터 등장
5. 필드 추출: JS evaluate로 각 필드 셀렉터 순회
6. 이미지 URL 추출: img[src] 목록
7. 옵션 테이블 추출: table.option-table tr
8. data/smartstore/products/{product_id}.json 저장
```

### 4-2. 셀렉터 관리 원칙

```python
# scripts/naver/smartstore/product/page_selectors.py 에 집중 관리
SELECTORS = {
    "product_name":     'input[name="productName"]',
    "price":            'input[name="salePrice"]',
    "stock":            'input[name="stockQuantity"]',
    "status_badge":     '.product-status-badge',
    "main_image":       '.representative-image img',
    "option_table":     'table.option-management-table',
    "description_area": 'iframe.description-editor',
}
```

- 셀렉터는 `selectors.py` 한 파일에만 정의 → 네이버 UI 변경 시 한 곳만 수정
- 셀렉터 실패 시 fallback 셀렉터 배열로 순서대로 시도
- 실패한 셀렉터는 로그에 기록 → 정기 점검 트리거

### 4-3. 수집 실패 처리

```python
# 수집 실패 등급
FAIL_PARTIAL   = "partial"   # 일부 필드 누락 → 누락 필드 목록과 함께 반환
FAIL_NO_PAGE   = "no_page"   # 상세 페이지 진입 실패 → 재시도 1회
FAIL_SESSION   = "session"   # 세션 만료 → SessionManager.check_and_recover()
FAIL_RATE_LIMIT= "rate_limit"# 네이버 봇 감지 → 30초 대기 후 재시도
```

---

## 5. API 엔드포인트 표준

### 5-1. 상품 상세 조회

```
GET /api/v1/smartstore/products/{product_id}

Query:
  refresh: bool = false   # true면 CDP 재수집, false면 캐시 반환

Response 200:
{
  "ok": true,
  "product": { ...ProductDetail },
  "source": "cache" | "cdp",
  "collected_at": "2026-05-29T10:00:00+00:00"
}

Response 404:
{
  "ok": false,
  "error": "product_not_found",
  "hint": "products/collect 로 목록을 먼저 수집하세요"
}
```

### 5-2. 상품 상세 CDP 수집

```
POST /api/v1/smartstore/products/{product_id}/collect

Response 200:
{
  "ok": true,
  "product": { ...ProductDetail },
  "duration_ms": 3240,
  "collected_at": "..."
}
```

### 5-3. 상품 필드 편집 (approval_gated)

```
PUT /api/v1/smartstore/products/{product_id}

Body:
{
  "fields": { "price": 29800, "stock": 100 },
  "reason": "가격 조정",
  "dry_run": true
}

Response 200 (dry_run=true):
{
  "ok": true,
  "dry_run": true,
  "preview": { "price": { "before": 32000, "after": 29800 } },
  "message": "dry_run 모드 — 실제 변경 없음"
}

Response 200 (dry_run=false, approval 토큰 포함):
{
  "ok": true,
  "changed": ["price", "stock"],
  "duration_ms": 1820
}

Response 403 (approval 토큰 없음):
{
  "ok": false,
  "error": "approval_required",
  "hint": "PUT 요청은 SMARTSTORE_APPROVED_SUBMIT 토큰 필요"
}
```

### 5-4. 공통 응답 규칙

| 필드 | 타입 | 설명 |
|------|------|------|
| `ok` | bool | 항상 포함 |
| `error` | str | 실패 시 snake_case 에러 코드 |
| `hint` | str | 실패 시 복구 방법 안내 |
| `collected_at` | ISO str | CDP 수집 시각 |
| `duration_ms` | int | CDP 소요 시간 |
| `dry_run` | bool | 편집 요청 시 포함 |

---

## 6. 프론트엔드 UX 표준

### 6-1. 상품 목록 → 상세 진입 패턴

```
상품 목록 테이블 행 클릭
  → ProductDetailDrawer (우측 슬라이드 패널) 열림
  → 캐시 즉시 표시 (source: cache)
  → 백그라운드 refresh=true 수집 후 갱신
  → source: cdp 로 변경 시 "실시간 갱신됨" 토스트 표시
```

### 6-2. 드로어 레이아웃

```
┌─────────────────────────────────────┐
│ [상품명]                   [닫기 ×] │
│ 상품번호: 1234567890                │
│ 상태: [판매중 ●]                    │
├─────────────────────────────────────┤
│ [대표이미지]  가격: 29,800원        │
│               재고: 100개           │
│               카테고리: 생활/주방   │
├─────────────────────────────────────┤
│ 탭: [기본정보] [옵션] [통계] [이력] │
├─────────────────────────────────────┤
│ (탭 내용)                           │
├─────────────────────────────────────┤
│ [셀러센터 바로가기] [편집 요청]     │
└─────────────────────────────────────┘
```

### 6-3. 인라인 편집 규칙

- **즉시 편집 가능** (safe 필드): 가격, 재고 → 클릭 시 input 전환 → blur 시 dry_run 미리보기 → 확인 버튼으로 실제 적용
- **편집 불가** (gated 필드): 상품명, 카테고리, 설명 → 잠금 아이콘 + "셀러센터에서 직접 수정" 안내
- 모든 편집 전 `window.confirm()` 게이트 필수
- 편집 성공 후 해당 필드 하이라이트 2초 표시

### 6-4. 상태 배지 색상 표준

| 상태 | 라벨 | 색상 |
|------|------|------|
| SALE | 판매중 | green |
| OUTOFSTOCK | 품절 | yellow |
| SUSPENSION | 판매중지 | red |
| CLOSE | 숨김 | gray |

### 6-5. 데이터 없음 처리

```
캐시 없음 + CDP 수집 실패
  → "데이터를 불러올 수 없습니다"
  → [재시도] 버튼
  → [셀러센터 바로가기] 버튼
```

---

## 7. 보안·승인 게이트 기준

### 7-1. 위험 등급별 처리

| 위험 등급 | 해당 작업 | 처리 방식 |
|----------|----------|----------|
| read | 상세 조회, 캐시 조회 | 즉시 실행 |
| prepare | 편집 dry_run, 미리보기 | 즉시 실행 |
| submit | 실제 필드 편집 | `SMARTSTORE_APPROVED_SUBMIT` 토큰 필수 |
| critical | 상품 삭제, 카테고리 변경 | **구현 금지** (셀러센터 직접 접속) |

### 7-2. 감사 로그 필수 항목

```python
log_event(
    event_type="SMARTSTORE_PRODUCT_EDIT",
    task_id=task_id,
    product_id=product_id,
    fields_changed=list(fields.keys()),
    dry_run=dry_run,
    risk="submit",
    actor=current_user.username,
)
```

---

## 8. 구현 순서 (직렬 진행)

### Phase 1 — 상세 조회 (P0, read-only)

```
Step 1. scripts/naver/smartstore/product/page_selectors.py 작성
Step 2. scripts/naver/smartstore/product/detail_collector.py 작성
        └── collect_product_detail(page, product_id) → ProductDetail
Step 3. GET /smartstore/products/{product_id} 엔드포인트 추가
Step 4. POST /smartstore/products/{product_id}/collect 엔드포인트 추가
Step 5. admin-web: ProductDetailDrawer.tsx 컴포넌트 작성
Step 6. 목록 행 클릭 → 드로어 열기 연결
Step 7. 게이트 실행 + 테스트
```

### Phase 2 — 가격·재고 편집 (P1, approval_gated)

```
Step 1. scripts/naver/smartstore/product/field_editor.py 작성
        └── patch_field(page, product_id, field, value) → PatchResult
Step 2. PUT /smartstore/products/{product_id} 엔드포인트 추가
Step 3. admin-web: 인라인 편집 UX 추가 (가격, 재고)
Step 4. dry_run 미리보기 → 확인 → 실행 흐름 연결
Step 5. 감사 로그 검증
Step 6. 게이트 실행 + 테스트
```

### Phase 3 — 옵션·이미지·통계 연결 (P2)

```
Step 1. 옵션 테이블 수집 → ProductOption 목록
Step 2. 이미지 URL 목록 추출 → 드로어 갤러리 표시
Step 3. 상품별 통계(조회수/주문수/리뷰) 드로어 통계 탭 연결
Step 4. 편집 이력 JSONL → 이력 탭 표시
```

---

## 9. 품질 게이트 (작업 후 필수 실행)

```bash
python tools/repo_gates/codebase_layer_audit.py
pytest tests/test_codebase_layer_audit.py -q
python tools/quality/quality_gate.py --staged --enforce --allow-existing-code-change
```

**판정 기준:**

| 항목 | 기준 | 조치 |
|------|------|------|
| FORBIDDEN_IMPORT | 0 | 0 초과 → STOP |
| SECURITY_PATTERN | 0 | 0 초과 → STOP |
| CIRCULAR_IMPORT | 0 | 0 초과 → STOP |
| 상세 조회 테스트 | PASS | 실패 → STOP |
| approval_gated 우회 | 없음 | 발견 시 → STOP |

---

## 10. 참조 파일

| 파일 | 용도 |
|------|------|
| `ai_orchestrator/connectors/smartstore_router.py` | 기존 라우터 (확장 기준) |
| `scripts/naver/smartstore/__init__.py` | NaverSmartStore 클래스 (CDP 자동화) |
| `scripts/naver/smartstore/product/models.py` | 데이터 모델 (확장 대상) |
| `admin-web/src/app/naver/smartstore/SmartStoreClient.tsx` | 기존 UI (드로어 추가 위치) |
| `scripts/auth/auth_session.py` | 세션 복원 (`restore_session('naver.com', page)`) |
| `ai_orchestrator/connectors/naver_auth/session_router.py` | 세션 파이프라인 API |
| `data/sessions/naver.com.json` | 저장된 로그인 세션 |
