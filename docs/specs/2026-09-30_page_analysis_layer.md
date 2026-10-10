# 페이지 구조 분석 계층 기준서 v4 (신규 화면 대응 — HTML 탐색·분석 보완)

작성: 2026-09-30 · v4 개정(범용 팝업 인지 추가) · 상태: **승인 대기 (코드 미작성)** · 범위: A~C 단계(§3)

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

### 2-1. 신규 화면 대응 빈틈 (스냅샷 JS `_EXTRACT_FRAME_JS` 실측, v2 추가)

| 빈틈 | 근거 | 신규 화면에서의 영향 |
|---|---|---|
| 입력칸의 `<label>` 텍스트 미수집 | inputs 는 name/id/placeholder/aria 만 | id 없는 칸은 용도를 알 수 없음 |
| `<select>` 옵션 미수집 | 태그만 수집 | 드롭다운 자동 선택 불가 |
| 텍스트·aria 없는 버튼 제외 | `.filter(b => b.text \|\| b.aria)` | 아이콘 버튼 누락 |
| 표·목록 구조 없음 | table / ul·li / 행 반복 미수집 | 주문·게시글 목록을 데이터로 못 읽음 |
| 섀도우 DOM 미통과 | `document.querySelectorAll` 은 shadow root 안을 못 봄 | 웹 컴포넌트 화면이 통째로 비어 보임 |
| 모달/다이얼로그 판별 없음 | `role=dialog`, `aria-modal` 미수집 | 팝업이 가려도 모름 |
| 위험 동작 표시 없음 | 버튼 위험도 분류 없음 | 결제·삭제·발행을 자동으로 누를 위험 |
| 동적 로딩 대응 없음 | 즉시 1회 추출 | 스피너 중 추출하면 빈 화면 |

### 2-2. 중복 확인 결과와 재사용 결정 (v3 추가 — `projects/CLAUDE.md` §1 준수)

`dup-checker` 서브에이전트 조사 후, 재사용 후보 3곳은 **직접 열어 사실 확인**했다.

| 기능 | 기존 구현 (확인) | 결정 |
|---|---|---|
| 셀렉터 안정성 점수 | 없음(`selector_health/core.py` 는 존재·가시성만) | **새로 작성** |
| 요소 역할 분류(버튼/링크) | 입력칸 전용 `scripts/form/discovery.py::_ROLE_KEYWORDS`(L1), 버튼 전용 없음 | **새로 작성**, 키워드 구조는 참고 |
| 위험 버튼 분류 | `local_agent/runtime/generic_selector_discovery.py::_RISK_BUTTON_KEYWORDS`(L4, 14개 항목: 결제·서명·입찰·송금·이체·계약 제출·최종 제출·삭제) | **재사용(import)**. 없는 범주(발행·전송·탈퇴)는 이 목록을 확장하지 않고 우리 쪽에서 **추가 키워드로 덧붙임**(기존 모듈 수정 없음) |
| 로그인/캡차 상태 판정 | `local_agent/login_state_detector.py::classify(url, title, body_sample, ...)` — 순수 함수, LOGIN_REQUIRED·CHALLENGE_REQUIRED·LOGGED_IN·SESSION_EXPIRED·POPUP_WAITING 등 판정 (**L10**) | 아래 레이어 문제로 **직접 import 불가** → 아래 결정 |
| 권한 없음(permission_denied) | 없음 | **새로 작성** |
| 팝업 판정 | `scripts/popup_detector.py`(페이지 필요), 우리는 스냅샷 기반 | 새로 작성(스냅샷 입력) |

**레이어 제약(실측):** `module_registry.json` 기준 L4 는 L1·L2·L3·L4·L7 만 import 할 수 있다. `login_state_detector.py` 는 **L10**(로컬 에이전트)이라
L4 인 `scripts/explorer/page_analysis.py` 가 직접 import 하면 역방향 import(`FORBIDDEN_IMPORT`)다.

**결정 (택1 — 사용자 승인 사항):**
- **(가) 권장:** 이번에는 상태 판정 중 로그인/캡차 부분을 **새로 쓰지 않고 판정 결과 어휘만 맞춘다**. `page_analysis` 는 `page_state` 를
  `login_required / captcha / permission_denied / popup_blocking / ok / unknown` 으로 내되, 로그인·캡차는 단순 규칙(URL 패턴·비밀번호 입력칸·문구)만 쓰고,
  **L10 의 정교한 판정은 호출하는 쪽(L10/L6)에서 `classify()` 결과와 합치도록** 남긴다. 중복은 규칙 범위 최소화로 억제한다.
- (나) `classify()` 의 URL·문구 패턴 상수(`LOGIN_HOST_HINTS`, `CHALLENGE_TEXT_PATTERNS` 등)를 L1(공용 계약)로 옮겨 양쪽이 import.
  중복은 없어지나 **기존 파일 수정**이며 파급이 커서(L10 모듈 변경, 관련 테스트 다수) 별도 기준서로 분리하는 것을 권장.

## 3. 변경 범위

레이어: **L4 Browser Engine (범용)**, 신규 파일 위치 `scripts/explorer/`. 기존 파일은 수정하지 않는다.

| 파일 | 변경 |
|---|---|
| `scripts/explorer/page_analysis.py` (신규) | 스냅샷 dict → 분석 dict. **순수 함수**(브라우저·네트워크·파일 쓰기 없음). import: `local_agent.runtime.generic_selector_discovery._RISK_BUTTON_KEYWORDS`(L4→L4, 허용) |
| `tests/test_page_analysis.py` (신규) | 합성 스냅샷과 실제 깨진 셀렉터 사례로 검증. 브라우저 불필요 |
| `configs/module_registry.json` | 신규 파일 등록(게이트 요구) |

**변경하지 않는 것:** `page_snapshot.py`, `selector_health/*`, `mcp_server.py`, API 응답 키, DB, 외부 호출.
`mcp_server.py`의 독자 CDP 연결 8곳 통일은 **별도 작업**이다(범위 밖 §6).

### 3-1. 단계 (수집과 분석을 분리, 각 단계 끝에서 승인·검증)

| 단계 | 내용 | 브라우저 | 산출 |
|---|---|---|---|
| **A. 분석 계층** (v1 그대로 + 역할 기반 후보) | 스냅샷 → 역할·셀렉터 후보·페이지 상태 | 불필요(순수 함수) | `page_analysis.py` + 테스트 |
| **B. 수집 강화** | 스냅샷에 라벨·select 옵션·표/목록·다이얼로그·섀도우 DOM 추가, 로딩 안정 대기 | 필요(읽기 전용) | `page_snapshot.py` 확장 필드(**기존 필드·저장 형식은 그대로 유지, 필드 추가만**) |
| **C. 위험·행동 계획** | 요소 위험도(결제·삭제·발행·전송·제출·탈퇴) 분류와 "다음에 볼 만한 요소" 제안. 실행은 하지 않음 | 불필요 | 분석 결과의 `risk`/`suggested_next` 필드 |

각 단계는 이전 단계의 산출물을 입력으로 쓰고, **A만 통과해도 독립적으로 유용**하다. B는 실제 페이지를 열어 검증해야 하므로
CDP 세션이 살아 있는 상태에서 읽기 전용으로만 시험한다(쓰기·클릭·입력 없음).

### 3-2. 범용 팝업 인지 (v4 추가 — 사용자 요구: "특정 사이트가 아닌 어떤 팝업이든, 3개가 떠도")

**현황 조사(2026-09-30):** `scripts/popup_detector.py`(범용·여러 개 감지·최대 10회 반복 닫기·별도 창), `popup_watcher.py`(알려진 문구 표),
`smartstore/product/modal_guard.py`(스마트스토어 한정·문구 보존). 빈틈: ①내용(문구·버튼)을 읽지 않고 닫음 ②닫는 버튼의 위험 판단 없음
③모르는 팝업의 종류를 구조로 판정 못 함 ④JS 네이티브 `alert/confirm/prompt` 범용 처리 없음(hanafax·blog writer 에 개별 코드) ⑤겹친 순서 모름 ⑥분석 계층에 연결 없음.

**신규 모듈 2개 (기존 25곳 호출부는 수정하지 않는다):**

| 모듈 | 하는 일 | 브라우저 |
|---|---|---|
| `scripts/explorer/popup_probe.py` | 화면의 **모든** 팝업 수집: `role=dialog/alertdialog`, `aria-modal`, 열린 `<dialog>`, 이름에 modal·popup·layer 가 있는 요소, 그리고 이름과 무관하게 **고정 위치 + 큰 z-index 로 화면 25% 이상을 덮는 요소**. 각각 z-index·덮음 비율·문구(200자)·버튼 목록·프레임 위치 기록. 맨 위부터 정렬. 읽기 전용. 네이티브 대화상자 기록기(`install_dialog_recorder`) 포함 | 필요 |
| `scripts/explorer/page_analysis.py` (확장) | 팝업 종류 분류(notice/consent/warning/confirm/ad/error), 버튼 역할·위험, **안전하게 닫을 수 있는 버튼**(위험하지 않은 close/cancel 우선, 없으면 확인) 지정, 위험 버튼뿐이면 `needs_review` | 불필요 |
| `scripts/explorer/popup_probe.py::dismiss_popups_safely` | 맨 위 팝업부터 안전 닫기 버튼만 눌러 반복 처리(최대 N회). **위험 버튼만 있는 팝업은 누르지 않고 문구와 함께 보고.** 닫은 팝업의 문구는 항상 결과에 보존 | 필요 |

**네이티브 대화상자 정책(결정적):** `alert` → 수락(확인만 있음). `confirm`·`prompt`·`beforeunload` → **취소(dismiss)**, 안전 기본값. 메시지(200자)를 기록해 반환.
**옵트인:** 기록기는 호출자가 명시적으로 설치해야 동작한다(자동으로 페이지 이벤트를 가로채지 않는다).

**시험:** 실제 사이트 대신 **로컬 HTML**로 헤드리스 Chrome 에서 시험한다 — 팝업 3개 겹침(z-index 순서), 역할 없는 오버레이, 쿠키 배너(하단 고정), 숨김 팝업 제외,
`<dialog open>`, 위험 버튼만 있는 팝업, 네이티브 alert/confirm. 순수 분석은 합성 데이터로 브라우저 없이 시험한다.

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

### 4.1-1 셀렉터 후보의 두 종류 (도구 선정 결과 반영)
Playwright 1.63 은 `get_by_role / get_by_label / get_by_test_id / get_by_text / get_by_placeholder / aria_snapshot` 을 제공한다
(옛 `page.accessibility` 는 제거됨). 새 패키지 없이 이를 활용한다.
- **역할 기반 후보** (1순위): `get_by_role("button", name="저장")`, `get_by_label("제목")` 형태의 **문자열로 표현**한다. 빌드 해시·`ng-model` 같은 내부 이름과 무관.
  같은 역할·이름이 화면에 여러 개면 "중복" 표시를 하고 CSS 후보를 함께 제시한다.
- **CSS 후보**: 아래 §4.2 점수 규칙.
- 분석 모듈은 여전히 **순수 함수**(후보 문자열만 만든다). 실제 로케이터 동작 검증은 B단계 실측에서 한다.

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

### 4.4-1 위험 동작 분류 (C단계)
버튼·링크·폼 제출 요소의 텍스트/aria/id/name 을 분류해 `risk` 를 붙인다. **기존 `_RISK_BUTTON_KEYWORDS`(결제·서명·입찰·송금·이체·계약 제출·삭제)를 import 해 그대로 쓰고**, 그 목록에 없는 `publish`·`send`·탈퇴 류만 이 모듈의 추가 사전으로 덧붙인다.

| 위험 | 키워드 예 | 이 프로젝트 정책과의 연결 |
|---|---|---|
| `payment` | 기존: 결제·pay·송금·이체 / 추가: 구매, 주문하기, purchase | 결제·과금은 항상 사용자 확인 |
| `destructive` | 기존: 삭제 / 추가: 탈퇴, 해지, 초기화, delete, remove | 데이터 삭제는 승인 후 |
| `publish` | 발행, 게시, 등록, 공개, publish, post | 외부 공개 발행은 매번 재확인 |
| `send` | 전송, 발송, 보내기, send, submit | 메일·메시지 전송은 매번 재확인 |
| `safe` | 그 외 | |

분석 결과는 위험 요소를 표시만 하며 **자동 클릭 판단에 쓰지 않는다**(승인 게이트는 기존 것을 그대로 사용). 사전은 모듈 상수로 두고 테스트로 고정한다.

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
- **후속 D단계:** 이전/현재 스냅샷 비교로 "이 셀렉터는 이 요소로 바뀐 것 같다" 대체 후보 제시, 헬스체크 보고서에 연결
- **후속 E단계:** 멈춤 진단(진입 직후 page_state 판정으로 대기 대신 즉시 원인 반환) — `mcp_server.py` 도구에 적용
- `mcp_server.py`의 독자 `connect_over_cdp` 8곳을 공유 연결(`run_on_browser_thread`)로 통일 — 별도 기준서
- 사이트별 탐색기 30개 통합, UI 표시(UI 보류)

## 7. 위험과 대응
| 위험 | 대응 |
|---|---|
| 키워드 사전 오탐(다른 사이트에서 역할 오분류) | `other` 기본, 사전은 테스트로 고정, 판정 근거를 출력에 남김 |
| 해시 판정이 정상 id를 깎음 | 규칙을 보수적으로(끝 5자 이상 난수 + `__` 구분자), 경계 사례 테스트 |
| 스냅샷에 개인정보/입력값 포함 | 분석은 라벨·속성 이름만 사용, 입력 `value`는 읽지 않음. 출력에 원문 텍스트 전체 미포함 |
| 순수 함수라 실제 페이지와 어긋남 | B단계 이후 실측 스냅샷으로 검증 |

롤백: 신규 파일 3개 삭제(다른 파일 미수정).

## 8. 승인 요청
**§2-2 의 (가)/(나) 중 선택**과 함께, A→B→C 순서로 진행한다. **A단계**(`page_analysis.py` + 테스트 + 레지스트리 등록, 순수 함수)부터 승인을 요청하고,
A 완료·검증 후 B(수집 강화, 실측)와 C(위험 분류)는 각각 결과를 보고 다시 승인받는다.
