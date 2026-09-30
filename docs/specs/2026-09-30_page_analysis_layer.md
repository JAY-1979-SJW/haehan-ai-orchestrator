# 페이지 구조 분석 계층 기준서 (HTML 탐색·분석 보완 1단계)

작성: 2026-09-30 · 상태: **승인 대기 (코드 미작성)** · 범위: 1단계(분석 계층)만

## 1. 배경과 목적

사이트 자동화(카페 글쓰기, 스마트스토어 등록, 블로그 발행)는 코드에 박힌 셀렉터에 의존한다. 사이트가 화면을
바꾸면 조용히 깨진다. 지금은 깨졌다는 사실은 알 수 있지만(헬스체크), **왜 깨졌는지, 무엇으로 바꾸면 되는지,
애초에 어떤 셀렉터가 깨지기 쉬운 것이었는지**는 알 수 없다.

이번 단계는 이미 수집되는 페이지 스냅샷 위에 **읽기 전용 분석 계층**을 얹어, 요소의 역할과 셀렉터 안정성,
페이지의 차단 상태(로그인 요구·권한 없음·캡차)를 판정한다.

## 2. 현황 (실측, 2026-09-30)

| 항목 | 내용 |
|---|---|
| 스냅샷 | `scripts/explorer/page_snapshot.py::snapshot(page)` — 프레임별 links/inputs/buttons/forms/headings(id·name·aria·placeholder·visible·text)를 추출해 `data/sitemap/*.json` 저장. 읽기 전용, 분석 없음 |
| 헬스체크 | `scripts/ops/selector_health/` — `SiteSpec`/`SelectorCheck`로 코드 셀렉터의 존재·가시성 측정(OK/HIDDEN/MISSING/SKIPPED/ERROR). 등록 사이트 2개(naver_blog, naver_smartstore) |
| 최근 보고서 | 2026-09-19: 28개 중 **MISSING 10, SKIPPED 4, OK 14** |
| 깨진 셀렉터의 성격 | `button.publish_btn__m9KHH`(빌드 해시 클래스), `input[ng-model="vm.product…"]`(프레임워크 내부명), `.se-section-documentTitle`(에디터 내부 클래스), `button:has-text("저장")`(문구 의존) |
| 탐색 코드 | 사이트별 탐색기 약 30개(카페·블로그·EUM·하이웍스·구글 등), 대부분 개별 복사본 |
| 멈춤 사례 | 2026-09-30 카페 게시판 목록 조회가 300초 멈췄을 때 원인(권한 없음 vs 연결 정지) 구분 불가 |

## 3. 변경 범위

레이어: **L4 Browser Engine (범용)**, 신규 파일 위치 `scripts/explorer/`. 기존 파일은 수정하지 않는다.

| 파일 | 변경 |
|---|---|
| `scripts/explorer/page_analysis.py` (신규) | 스냅샷 dict → 분석 dict. **순수 함수**(브라우저·네트워크·파일 쓰기 없음) |
| `tests/test_page_analysis.py` (신규) | 합성 스냅샷과 실제 깨진 셀렉터 사례로 검증. 브라우저 불필요 |
| `configs/module_registry.json` | 신규 파일 등록(게이트 요구) |

**변경하지 않는 것:** `page_snapshot.py`, `selector_health/*`, `mcp_server.py`, API 응답 키, DB, 외부 호출.
`mcp_server.py`의 독자 CDP 연결 8곳 통일은 **별도 작업**이다(범위 밖 §6).

## 4. 설계

### 4.1 입력/출력
- 입력: `page_snapshot.snapshot()`이 반환/저장하는 dict(`url`, `title`, `frames[].links/inputs/buttons/forms/headings`).
- 출력 `analyze_snapshot(snapshot) -> dict`:
  ```
  {
    "url", "title",
    "page_state": {"state": "ok|login_required|permission_denied|captcha|popup_blocking|unknown",
                   "evidence": ["url 패턴 …", "문구 …"]},          # 값(비밀번호 등)은 절대 담지 않음
    "elements": [ {"frame": 0, "kind": "button|input|link|select", "role": "login|search|write|save|publish|next|close|other",
                   "label": "…", "visible": true,
                   "selectors": [ {"css": "…", "stability": 0~100, "reason": "id 안정|aria-label|해시 클래스 감점 …"} ] } ],
    "summary": {"elements": N, "fragile_only": M}
  }
  ```

### 4.2 셀렉터 안정성 점수 (결정적 규칙)
높을수록 안정. 후보 셀렉터를 요소별로 여러 개 만들고 점수순 정렬한다.

| 근거 | 점수 | 비고 |
|---|---|---|
| 안정적인 `id` (해시/난수/숫자열 아님) | 90 | |
| `name` 속성 | 80 | |
| `aria-label` / `role`+텍스트 | 75 | 접근성 속성은 화면 개편에도 잘 유지 |
| `data-*` 테스트/식별 속성 | 70 | |
| 고정 문구 텍스트(`:has-text`) | 50 | 문구 변경·다국어에 취약 |
| 프레임워크 내부 속성(`ng-model`, `data-v-*`) | 35 | |
| 해시가 붙은 클래스(`btn__m9KHH`, 끝이 5자 이상 영숫자 난수) | 15 | **빌드마다 바뀜** |
| 위치 기반(`nth-child`) | 20 | |

해시 판정: 클래스/ID가 `__[A-Za-z0-9]{5,}`로 끝나거나, 숫자·대소문자 혼합 6자 이상 무의미 토큰을 포함하면 "빌드 해시"로 본다.

### 4.3 역할 분류
한국어/영어 키워드 사전(로그인·검색·글쓰기·저장·임시저장·발행/등록·다음·닫기·확인·취소)을 요소의 텍스트,
`aria-label`, `id`, `name`, `placeholder`에 적용. 모호하면 `other`. 사전은 모듈 상수로 두고 테스트로 고정.

### 4.4 페이지 상태 판정
- `login_required`: URL이 알려진 로그인 경로(`nid.naver.com/nidlogin`, `accounts.commerce.naver.com/login`, `accounts.google.com`) 이거나 비밀번호 입력칸 + 로그인 버튼 존재
- `captcha`: 문구(보안문자, 자동입력 방지, captcha) 또는 캡차 이미지 요소
- `permission_denied`: 문구(권한이 없습니다, 접근할 수 없습니다, 관리자만)
- `popup_blocking`: 보이는 모달/다이얼로그 역할 요소가 전체를 덮는 경우(role=dialog visible)
- 근거(`evidence`)는 어떤 규칙으로 판정했는지만 기록하고, **입력값·텍스트 원문 전체를 저장하지 않는다**(문구 키워드만).

### 4.5 CLI
`python scripts/explorer/page_analysis.py <snapshot.json> [--json]` — 파일을 읽어 사람이 읽기 좋은 요약을 출력(기본), `--json`은 전체 분석. 저장하지 않는다.

## 5. 이 단계의 효과 검증 계획 (드라이런 포함)
1. 단위: 안정성 점수 표의 각 행, 해시 판정(실제 `publish_btn__m9KHH`가 15점), 역할 사전, 상태 판정 4종
2. **회귀 사례:** 9월 19일 보고서에서 MISSING이던 셀렉터 10개를 "취약 유형"으로 분류하는 시험
   (해시 클래스 1, ng-model 계열 다수, 에디터 내부 클래스 등 → 모두 stability ≤ 50 판정)
3. 위 §5-1 수치(MISSING 10건 중 9건 ≤50점, 특히 `publish_btn__m9KHH` 15점)를 테스트로 고정
4. 게이트: layer audit 3종, quality gate, ruff 신규 위반 0

## 5-1. 드라이런 결과 (코드 작성 전, 2026-09-19 헬스체크 실측 28개에 §4.2 규칙을 계산만 해 본 것)

| 헬스체크 상태 | 건수 | 점수 ≤ 50(취약) 판정 |
|---|---|---|
| MISSING(깨짐) | 10 | **9건 (90%)** — 해시 클래스 1(15점), ng-model 4(35점), 에디터 내부 클래스 3(40점), 문구 의존 1(50점) |
| SKIPPED | 4 | 4건 |
| OK(정상) | 14 | **11건 (79%)** |

**해석과 설계 반영**
- 규칙은 깨진 셀렉터의 대부분을 취약으로 알아본다(재현율 90%). 하지만 **정상 셀렉터의 79%도 취약으로 판정**해서, 점수 하나만으로는 "곧 깨질 것"과 "현재 잘 쓰이는 것"을 구분하지 못한다.
- 그래서 이 단계의 산출물은 **"깨질 셀렉터 예측"이 아니라 "더 안정적인 대체 후보 제시"** 로 정의한다. 요소마다 후보를 여러 개 만들고
  현재 쓰는 셀렉터보다 점수가 높은 후보가 있으면 "교체 권장"으로 표시한다(점수가 같거나 낮으면 표시 안 함).
- 점수 자체를 합격/불합격 기준으로 쓰지 않는다. 2단계(스냅샷 비교)에서 "현재 MISSING이고 대체 후보가 있는 것"에만 강한 신호를 준다.
- 위 표는 작성 전 계산이며, 구현 후 같은 28건으로 테스트해 이 수치와 일치하는지 확인한다.

## 6. 범위 밖 (후속 단계)
- **2단계:** 이전/현재 스냅샷 비교로 "이 셀렉터는 이 요소로 바뀐 것 같다" 대체 후보 제시, 헬스체크 보고서에 연결
- **3단계:** 멈춤 진단(진입 직후 page_state 판정으로 대기 대신 즉시 원인 반환) — `mcp_server.py` 도구에 적용
- `mcp_server.py`의 독자 `connect_over_cdp` 8곳을 공유 연결(`run_on_browser_thread`)로 통일 — 별도 기준서
- 사이트별 탐색기 30개 통합, UI 표시(UI 보류)

## 7. 위험과 대응
| 위험 | 대응 |
|---|---|
| 키워드 사전 오탐(다른 사이트에서 역할 오분류) | `other` 기본, 사전은 테스트로 고정, 판정 근거를 출력에 남김 |
| 해시 판정이 정상 id를 깎음 | 규칙을 보수적으로(끝 5자 이상 난수 + `__` 구분자), 경계 사례 테스트 |
| 스냅샷에 개인정보/입력값 포함 | 분석은 라벨·속성 이름만 사용, 입력 `value`는 읽지 않음. 출력에 원문 텍스트 전체 미포함 |
| 순수 함수라 실제 페이지와 어긋남 | 2·3단계에서 실측 스냅샷으로 검증 |

롤백: 신규 파일 3개 삭제(다른 파일 미수정).

## 8. 승인 요청
1단계(분석 계층: `page_analysis.py` + 테스트 + 레지스트리 등록)로 코드 작성 진행 여부.
