# 사이트 업무 지도 M6 — 은행·세무 등 업무 사이트 대응 (기준서)

작성 2026-10-04 · 상태: 기준서(승인 대기) · 선행: 2026-10-03_site_task_map.md, 2026-10-04_site_task_map_m5_runner.md

## 1. 배경과 결정
- 목표: AI 직원이 은행 업무(잔액·거래내역·이체 준비), 국세청 홈택스(세금계산서 조회·발행 준비) 같은 **업무 사이트**를 사람처럼 다루는 것.
- **사용자 결정(2026-10-04): 해당 분야의 공식 API(오픈뱅킹, 전자세금계산서 ASP 등)는 유료이므로 쓰지 않는다. 화면의 버튼을 눌러 처리한다.**
  → 벤더 목록(`configs/vendor_apis.json`)에 이 결정을 기록해 AI가 "API 신청하세요"라고 되풀이하지 않게 한다(새 상태 `paid_declined`).
- 금지선 유지(CLAUDE.md): 송금·결제·전자서명·신고 제출의 **최종 실행은 사람**. 공동인증서·OTP·로그인도 사람.

## 2. 현재 한계(2026-10-04 블로그 탐색 실측)
- 6쪽 방문, 양식 4쪽, **업무 0건**. 원인: 스냅샷이 `input/textarea/select`만 입력창으로 보고, 편집 영역(contenteditable)·버튼만 있는 화면(발행/조회/이체 버튼)을 업무로 못 잡는다.
- 위험 키워드에 업무 사이트 용어(이체·송금·발행·전자서명·인증서·신고)가 부족할 수 있다.
- 탐색이 무엇을 놓쳤는지 알 수 없다(점검표 없음).

## 3. 변경 범위 (이번 단계 M6-a: 읽기·기록만, 실행 정책은 건드리지 않음)
| # | 변경 | 위치(레이어) | 비고 |
|---|---|---|---|
| 1 | 스냅샷에 편집 영역(contenteditable, role=textbox)을 `inputs`에 포함(type=`editable`) | `scripts/explorer/page_snapshot.py` (L5 어댑터) | 기존 키 유지, 항목만 추가 |
| 2 | 입력창이 없고 버튼만 있는 화면을 **버튼 업무**(category=`navigate`/`submit`)로 기록, 위험도는 버튼 글자로 판정 | `ai_orchestrator/domain/site_task_map.py` (L1) | 위험도는 올리기만, 낮추지 않음(기존 원칙) |
| 3 | 위험 키워드 확장: 이체·송금·출금·결제·발행·전자서명·인증서·신고·제출 → submit, 저장·등록·수정 → write | 같은 파일 | 읽기 업무가 submit으로 오분류되는 쪽(안전한 쪽)으로만 치우침 |
| 4 | 탐색 **점검표**: `explored.coverage = {pages, form_pages, tasks, editable, buttons_only, unrecognized}` 저장, 양식은 있는데 업무 0건이면 `warning` 기록 | `site_task_map.note_exploration` + `task_mapper.explore_to_map` | 스키마 버전 유지(선택 키 추가) |
| 5 | 벤더 상태 `paid_declined` 추가 + KISCON 외 항목 등록: 홈택스/전자세금계산서 ASP, 오픈뱅킹·은행 API | `vendor_directory.py`, `configs/vendor_apis.json` (L1/설정) | STATUS_GUIDE: "유료라 사용하지 않기로 함 — 사이트 지도의 화면 조작으로 처리" |
| 6 | 조회 응답(`lookup`)에 점검표 경고 노출 → AI가 "탐색이 불완전"을 알고 보고 | `site_task_map_service.lookup` | 응답 키 추가만 |

API 응답 key 삭제·변경, DB 스키마 변경, 새 라우트 없음 → 라우트 기준선(416) 변경 없음.

## 4. 다음 단계 (이번에 구현하지 않음, 별도 기준서)
- **M6-b 준비 실행(prepare)**: write/submit 업무를 **최종 버튼 직전까지** 입력하고 멈춰 "확정 카드"를 만든다. 사람이 누르면 그때 실행. 현재 서버는 read만 허용 — 이 정책 변경은 승인 필요.
- 공동인증서 로그인 상태 감지, 세션 만료 처리, 거래 금액·상대 계좌 화면 대조 확인.

## 5. 검증
- 단위: 편집 영역·버튼 전용 화면 픽스처(실제 헤드리스 Chrome), 위험 키워드 표(이체→submit, 조회→read), 점검표 경고, 벤더 `paid_declined`.
- 실측: 이미 저장된 `blog.naver.com` 재탐색(읽기 전용, 8쪽)으로 업무 > 0 확인.
- 게이트: ruff·mypy 새 오류 0, layer audit, 영향 테스트, `verify_change` PASS.

## 6. 위험
- 오분류로 쓰기 화면이 read로 잡히면 AI가 자동 실행할 수 있다 → 위험도는 **불확실하면 높게**, 서버가 read만 실행(이중 방어).
- 키워드 확장으로 거짓 양성(read→submit)이 늘면 AI가 할 수 있는 일이 줄지만 안전 쪽이다.
