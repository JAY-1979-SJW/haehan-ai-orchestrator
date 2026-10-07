# 네이버 자동 로그인 정리 — 진행 기록 (2026-10-01)

브랜치 `feat/login-state-by-element`. 푸시 안 함(로컬 커밋만).

## 끝난 것
| 커밋 | 내용 |
|---|---|
| `cbc52a4a` | 죽은 코드 5건 삭제(`cafe.py`, `secure_login.py`, `_human_type`, `wait_for_logout`, `list_naver_accounts`) — 복원법은 `docs/deleted_code_index.md` |
| `6ab874f8` | `select_naver_session` 중복 제거 → `scripts/browser/session/browser_cdp_selection_gate.py` 한 곳 |
| `0a1ba412` | `naver/auth.py::_safe_human_input` 사본 삭제 → 공용 `scripts/browser/page/human_input.py`(`click_timeout_ms`, 네이버는 8000) |

검증: 새 테스트 17개 통과, 변이 6개 전부 검출, 영향 테스트 새 실패 0(나머지는 기준선 백로그).

## 다음에 이어서 할 것 (우선순위 순)
1. **8401 FastAPI 재시작 승인 → 일렉트론 `/naver/session` 화면 종단 검증.** 그 전에는 "화면에서 확인됨"이라고 보고하지 않는다.
2. **로그인 칸 못 찾을 때 대체 탐색**(승인됨, 미착수): `login_naver` 실패 경로에서 `#id`/`#pw` 없으면 `page_analysis` 역할·위치 기반으로 찾기. 스크린샷 증거는 시도/unknown/unverified/failed/captcha 때만, `data/` 아래 7일 보관, 커밋 안 함. 비전 판독은 나중.
3. `unknown + 세션 쿠키` 모순 처리(`ensure_naver_login`=로그인 OK, 파이프라인=중단, `login_naver`=계정 불명) — 별도 기준서 필요.
4. `verify_login` / `connect_and_ensure_login`의 alias 읽기를 `account_probe.read_alias`로 위임(하이픈 유지, `connect_and_ensure_login`의 로그아웃 URL 위험 제거) — 별도 기준서.
5. `scripts/naver/browser_gate.py`의 세 번째 세션 선택 변형 검토, NID_AUT/NID_SES 쿠키명 정의 통일(`apps/marketing-standalone` 사본은 유지).

## 사용자 결정 대기
- `scripts/ops/make_inspection_video.py`: 없는 `_ID_SELECTORS` import로 실행 불가 — 고칠지 지울지.
- 오타 자격증명 `naver:skyjswin` 삭제(데이터 삭제라 승인 필요).
- 블로그 자동화 C단계(스케줄러 + `/naver/blog` "자동 작성" 탭 + 임시저장), 신규 사이트 온보딩 구현 승인.

## 건드리지 않은 미커밋 파일(다른 작업 것)
`.githooks/pre-commit.orig`, `ai_orchestrator/connectors/community_router.py`, `data/.cred.key.migrated`, `data/_backup_cred_*`, `data/content_rag/`, `tmpnzbjosab.py`, `admin-web/electron/.htmlvalidate.json`
