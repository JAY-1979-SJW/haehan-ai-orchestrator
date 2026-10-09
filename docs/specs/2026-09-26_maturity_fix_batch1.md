# 완성도 개선 1차분 기준서·드라이런 (2026-09-26, 코드 미수정)

근거: docs/maturity-assessment.md, docs/defect_index.json. 조사는 읽기 전용(하위 에이전트 6 병렬), 코드·git 변경 없음. 파일:줄은 조사 시점(master 워킹트리) 기준.
사용자 승인 후 별도 지시로 구현. 브랜치 stage/maturity-b1, 건당 1커밋.

## 요약

| # | 건 | 결론 | 작업량 |
|---|---|---|---|
| 1 | EUM 일일점검 조용한 실패(#13) | 원인 확정(`daily_check.py:98-101`), 실패 기록+알림+비0 종료 | S (+근본원인 조사 M 별도) |
| 2a | test_authed_local_agent_dispatch_dry_run | **테스트(감사 스크립트)가 낡음.** 실제 보안 문제 아님 — 보안 보고 대상 아님 | S |
| 2b | test_naver_blog_assets | 테스트가 낡음(모듈 이동) | S |
| 2c | test_naver_cafe_list_collector | 테스트가 낡음(모듈 이동), 통과 중이던 8개 재확인 필요 | S |
| 2d | test_app_deployment_readonly_polish | 테스트 경로가 낡음((legacy) 라우트 그룹 이동) | S |
| 3 | 발행·발송 공용 실패 기록·알림 래퍼 | 기존 장치 재사용, 신규 1파일(`scripts/publish_guard.py`) + 4곳 적용 | S(래퍼)+M(적용) |
| 4 | 예외 삼킴 위험경로 | **전제 불성립: 대상 경로 약 34곳, 성공 오보고 확인 0건.** 범위 재정의 필요(결정 사항) | S(조사)/S~M(로그정리) |
| 5 | 하나팩스 하드코딩 | 환경변수 1개, 기본값 유지 | S |

> 앞선 성숙도 평가의 E 점수(local_agent bare-except 143, CDP 117)는 `except` 계열 전체를 센 값이었고, 이번 정밀 조사에서 "bare `except:` 7 + `except…: pass` 약 27, 합 약 34" 로 나왔다. #19 의 1,341곳은 저장소 전체 수치이며 이 경로 전용이 아니다. 성숙도 평가 문서의 해당 수치는 과대 — 정정 필요.

---
## 1. EUM 매일 점검의 조용한 실패 (결함 #13)

**현재 동작**
- 스케줄러(PC 수동 등록 `HaehanEumDailyCheck`, 저장소에는 configs/code_map/entrypoints_manual.json:5 에 이름만) → `python scripts/eum/daily_check.py` → `main()`(:131-140) → `run_daily_check()`.
- scripts/eum/daily_check.py:57-97 try 전체를 :98-101 `except Exception` 이 받아 `skipped=True, reason="cdp_unavailable: <예외명>"` 로 반환. CDP 접속(:59)뿐 아니라 goto·추출·파일쓰기 예외도 전부 삼켜 원인이 가려짐.
- :63-66 `no_eum_tab_or_login`, :104-107 `no_device_data_after_extract` 도 skipped.
- main 은 skipped 를 print 만 하고 return → **종료코드 항상 0**(sys.exit 없음). 실패 기록 없음(정상 완료 때만 `{eum_dir}/daily_checks/<날짜>.json`). `work_run`(scripts/eum/run_log.py:56-110)은 router.py 에서만 사용, daily_check 는 안 씀.
- 스케줄러 등록 스크립트는 저장소에 없음 → 실제 트리거·재시도·로그 리다이렉트는 PC 에서 `schtasks /query` 로 확인 필요.

**변경안**
1. 예외 분기 세분화: `playwright.Error`(접속 불가)만 `cdp_unavailable`, 나머지는 `extract_failed: <예외명>`.
2. 실패 시 `failed=True` 로 반환하고 `daily_checks/<날짜>.json` 에 `status=failed`+reason 기록(마지막 성공일 판별용), stderr 에 명확한 에러 출력.
3. 알림: `ai_orchestrator/clients/telegram_sender.py:35 send_message`(미설정 시 `{"ok":False,"skipped":True}` 반환, 예외 없음) 재사용. 알림 자체 실패는 stderr 기록(다시 조용한 실패가 되지 않게).
4. `main()` → `int` 반환, 실패 시 2, `__main__` 에서 `sys.exit(main())`. 스케줄러의 "마지막 실행 결과"가 실패로 보이게 됨.
5. (선택) 같은 원인 연속 실패면 알림을 하루 1회로 제한.
6. `scripts/op_log.py` `log_op`(:185)로 실패 기록도 남김(3번 래퍼와 일관).

**예상 diff**: daily_check.py +~30줄(예외 분기, `_record_failure`, main 반환), tests/test_eum_daily_check.py 신규(playwright 예외 monkeypatch→failed·비0 종료·알림 호출·알림 env 없어도 예외 없음).
**영향 테스트**: `query.py tests-for scripts/eum/daily_check.py` = 0건(직접 테스트 없음). 인접: tests/test_eum_run_log.py(work_run, 무관).
**라우트 영향**: 없음(router.py 가 import 하지 않음).
**위험**: 종료코드 비0 로 스케줄러 재시도가 있으면 반복 실행 / CDP(9223) 가 계속 죽어 있으면 알림이 매일 옴(피로) → 근본원인(9223 자동화 브라우저 기동, scripts/local_agent/install_cdp_chrome_task.ps1 이 9223 을 다루는지)을 별도 조사 / scripts/eum→ai_orchestrator.clients import 는 층 게이트 확인 필요.
**작업량**: S (근본 원인 조사는 M).

---
## 2. 원래부터 실패하던 테스트 4건 — 진단

| 테스트 | 판정 | 원인 | 수정안 | 작업량 |
|---|---|---|---|---|
| tests/test_authed_local_agent_dispatch_dry_run.py | **테스트(감사 스크립트)가 낡음. 실제 보안 문제 아님** | verdict 는 tools/audits/agent/audit_authed_local_agent_dispatch_dry_run.py:183 이 정적 검사 FAIL 시 반환. 10개 체크 중 2개 FAIL: `register_endpoint_auth`("admin/owner guard not found"), `registration_code_flow`. 감사가 `ai_orchestrator/agent_hub/router/root.py:128-144` 를 grep 하지만 핸들러가 라우터 분할(32fa1ae5, 7ecf1b52)로 `local_agent_router_registration.py` 로 이동함. 새 위치: :25-31 `@registration_router.post("/register")`+`Depends(require_role("admin","owner"))`, :69 `/registration-codes`, :175 `/register-with-code`(일회용 등록코드로 보호, 의도된 공개). 인증 가드 온전. AUTH_ENABLED 는 docker-compose.yml:27, config.py:50 | 감사 스크립트의 대상 파일을 `local_agent_router_registration.py` 로, 데코레이터 문자열을 `@registration_router.post(...)` 로 교체. **정규식은 느슨하게 하지 말 것**(가드 제거 시 여전히 FAIL 해야 함). 선택: `issue_registration_code` 핸들러의 require_role 도 단언 | S |
| tests/test_naver_blog_assets.py::test_pixel_analysis_adjusts_representative_score | 테스트 낡음 | :180 `0 == 1`. 실코드는 `scripts/naver/blog/seo/assets.py` 로 이동, `scripts/naver/blog/assets.py` 는 `import *` 스텁. 테스트가 스텁에 monkeypatch 해서 `seo/assets.py:471` 이 자기 모듈 전역(:365)을 부름 → 가짜 미적용 | 테스트 import 를 `from scripts.naver.blog.seo import assets` 로. 나머지 9개는 심볼 읽기만이라 유지될 것 | S |
| tests/test_naver_cafe_list_collector.py::test_create_isolated_cafe_target_creates_new_tab | 테스트 낡음 | :166 `'' != 'iso'`. 실모듈 `scripts/naver/cafe/background/list_background_runner.py:159`, 기존 경로는 스텁. 패치가 스텁에 걸림 | `from scripts.naver.cafe.background import list_background_runner as runner`. :142 `runner.cdp`, :199, :331 도 같은 전환 필요 가능. **통과 중이던 8개가 우연 통과였을 수 있어 파일 전체 재실행** | S |
| test_app_deployment_readonly_polish_20260518.py::TestFilesExist::test_page_exists | 경로 낡음 | :11 PAGE 가 `admin-web/src/app/assistant/deployment/page.tsx`. 2597a8bc 가 `(legacy)/deployment/page.tsx` 로 이동(URL 불변, 라우트 그룹) | PAGE 경로에 `(legacy)` 추가. `_src()` 가 빈 문자열을 돌려 다른 단언이 가려졌을 수 있어 수정 후 내용 드리프트 재확인 | S |

- 영향 테스트: 각 파일 단독 재실행. 스텁을 import 하는 다른 테스트 확인 — `grep -r "cafe import list_background_runner"`, `"blog import assets"`(tests/test_naver_mail_action_gate_policy.py, tests/test_naver_service_router.py 는 미커밋 변경 중이므로 이 브랜치에서 건드리지 말 것).
- 코드 변경 0(테스트·감사 스크립트만). 라우트 영향 0.
- **보안 보고 대상 없음**(2a 는 실제 가드가 온전함을 소스로 확인). 다만 "감사 스크립트가 리팩터 후 자동으로 낡는다"는 구조 문제 → 보안 2단계 백로그로 넘길 것.

---
## 3. 발행·발송 공용 실패 기록·알림 래퍼

**기존 장치 (재사용, 신규 채널 금지)**
- 전송: `ai_orchestrator/clients/telegram_sender.py:35 send_message(text, reply_markup=None, chat_id=None, parse_mode="HTML") -> dict` (L3, 환경변수 TELEGRAM_BOT_TOKEN/TELEGRAM_APPROVER_CHAT_ID, 미설정이면 skipped). **주의: ai_orchestrator/telegram_notifier.py 는 메시지 빌더뿐(:41, :210)이고 전송 함수 없음.** 지시서의 "telegram_notifier 재사용"은 실제로는 telegram_sender 재사용이 된다.
- 기록: `scripts/op_log.py`(L7) `log_op`:185(파일+DB, ok/message/metadata), `op_context`:255, `op_logged`:271(실패 시 ok=False 기록 후 raise), `query_recent`:314. `scripts/critical_logger.py` `log_critical`:172. → "실패 기록 래퍼"의 절반이 이미 있고 **텔레그램 연동만 없음**.
- 중복 전송기 이미 존재: scripts/community/notifier.py:71, scripts/naver/automation/integration/notification_hub.py:109, local_agent/user_attention_notifier.py:111 → 새로 만들지 말고 telegram_sender 하나만 씀(정리는 범위 밖).
- 레이어: op_log(L7)가 텔레그램(L3)을 부르면 L7→{1,7} 위반이므로 **op_log 에 텔레그램을 넣으면 안 됨**. 조합은 L5(허용 {1..5,7})에서.

**제안**: 신규 `scripts/publish_guard.py`(L5 공용). scripts→ai_orchestrator.clients(L3) import 가 기존 관행인지·FORBIDDEN_IMPORT 통과는 `codebase_layer_audit`·registry_sync 로 구현 시 검증(결정 사항 D3).
```python
@contextmanager
def guarded_publish(op_name, *, notify=True, **meta):
    try: yield
    except Exception as e:
        log_op(op_name, ok=False, message=f"{type(e).__name__}: {e}", **meta)   # 파일+DB
        print(f"[FAIL] {op_name}: {e}", file=sys.stderr)                         # 콘솔
        if notify: _notify(f"❌ {op_name} 실패: {str(e)[:300]}")                 # 텔레그램, 자체 실패는 삼키되 stderr
        raise
def guarded(op_name, ok_fn=lambda r: True): ...   # 데코레이터. {"ok":False} 반환형 기능도 실패로 취급(ok_fn)
```
알림 본문에 토큰·OAuth·이메일 원문 금지(길이 300자 절단, 메타는 변수 식별자만).

**적용 4곳(예외 전파형/반환형 구분)**
| 기능 | 진입점 | 현재 실패 처리 | 적용 |
|---|---|---|---|
| YouTube | scripts/youtube/uploader.py:182 `execute_upload_plan`(→:138 `_upload_with_official_api`) | 예외 없이 `{"ok":False,"reason"}`(:144,:148,:153) 반환, result JSON+`emit_event` 만. 콘솔·알림 없음. 반환이 tuple | `@guarded("youtube_upload", ok_fn=lambda r: r[0]["status"]!="failed")` — blocked(승인 대기)는 실패로 알리지 않도록 ok_fn 정의 |
| 인스타 | scripts/instagram/api_publish.py:104/:145/:177 `publish_reel/carousel/story` | RuntimeError/ValueError 전파, 기록 없음 | `@guarded("ig_publish")`(예외 전파 유지) |
| 메일 | scripts/hiworks/mail_batch.py:99 `execute_send_batch`(건별 try/except→failed 카운트, :152 파일 저장), 실제 전송 scripts/hiworks/mail.py:118 | 건별 error 를 결과 파일에만 | `@guarded(ok_fn=lambda r: r["failed"]==0)`, **건별 알림 폭주 방지 위해 요약 1회**. Gmail 은 초안만 작성(scripts/google/gmail_api.py:85)이라 제외, naver/mail 발송 진입점은 미발견 |
| 스마트스토어 문의 | **scripts/naver/smartstore/inquiry_reply.py**(지시서의 scripts/inquiry/ 는 없음) :81 `submit_reply` | except 없음, 실패를 문자열 반환 | 결과 문자열 판정 ok_fn |

**예상 diff**: publish_guard.py 신규 ~70줄, tests/test_publish_guard.py 신규(텔레그램 monkeypatch: 실패 기록·stderr·알림 호출·미설정 skipped·알림 실패가 본작업을 깨지 않음), 4곳 데코레이터 각 +1~3줄.
**영향 테스트**: tests/test_google_youtube_upload.py, tests/test_hiworks_mail_batch.py. instagram·inquiry_reply·op_log 직접 테스트는 못 찾음(`query.py tests-for` 는 저장소 루트 `tools/code_map/query.py` 이며 조사 에이전트 일부가 경로 오류로 실행 못 함 — 구현 시 실행).
**라우트 영향**: 없음(시그니처·반환·예외 불변).
**위험**: 알림 폭주(배치), ok_fn 오판(blocked=정상 대기), 텔레그램 미설정 시 skipped 처리(정상), 승인 대기 상태를 실패로 알림, L5→L3 import 게이트.
**작업량**: 래퍼 S, 적용 4곳+테스트 M.

---
## 4. 예외 삼킴 — local_agent·CDP 위험 경로

**조사 결과**: 요청 범위(ai_orchestrator/local_agent/ 포함 browser/, local_agent/, scripts/cdp_force_start.py)의 삼킴은 **약 34곳**(bare `except:` 7 — deep_sitemap_detector.py:106,128,162,276,321 / sitemap_detector.py:127,147; `except…: pass` 약 27, 대부분 local_agent/token_store.py ~8, web_reader.py:198, site_mapper.py:374). cdp_force_start.py 는 0. **약 390곳이라는 수치는 이 경로가 아니라 `except` 전체를 센 값**.
**성공 오보고 경로: 확인 0건.** 검토한 지점 — browser/agent.py click/type/click_link 는 `ActionResult(ok=False)` 반환, `click_text`(:190-200)는 폴백 체인 후 마지막에 ok=False, login_auto_flow.py:332 실패→RESUME_FAILED, user_present_status_sender.py:157 실패→ok False, user_approval_gate.py:213 파싱오류→만료 True(fail-closed), local_agent/actions.py:1293 타임아웃→success False. browser_foreground_adapter.py:156 은 항상 True 를 반환하는 스텁 자체.
**결론/제안**: "20곳 수정"은 근거가 없어 **범위 재정의를 권고**한다.
- 제안 A(권장, S~M): 로그 전용 정리 — token_store.py 의 keyring→평문 폴백에 warning 로그(:130 는 이미 있음), bare `except:` 7곳은 `logger.debug`(selector/URL 노출·로그 폭주 방지), 나머지 best-effort 는 그대로. 동작 불변.
- 제안 B: 이 경로는 보류하고 나머지 `scripts/`·`ai_orchestrator/connectors/` 에서 같은 방식으로 재측정해 진짜 위험 경로를 찾는다(#19 1,341곳 중). 3번 래퍼가 발행·발송 쪽 위험 경로를 덮으므로 우선순위 낮음.
- 영향 테스트(A): token_store·sitemap_detector 관련 tests-for 를 파일군 단위로 실행. 라우트 영향 없음. 위험 낮음(`logger.exception` 을 bare-except 에 쓰면 로그 폭주 → `debug` 사용).

---
## 5. 하나팩스 bulk_send.py 하드코딩

**현재**: scripts/hanafax/bulk_send.py:5,6(docstring), **:27 `G2B_BASE = Path("C:/work/05. g2b/exports/개별팩스")`** → :28 FAX_FILE, :29 BATCH_DIR, 사용 :48,:77,:78,:144,:145,:149. 05.g2b 는 **다른 저장소**의 경로.
**결함 #17**: docs/defect_index.json:234 "경로를 파일마다 직접 조립 — Path(__file__).parents 561곳, C:\work 하드코딩 39곳, 공용 data_paths 사용 25파일". 기존 공용 함수 `scripts/common/data_paths.py get_app_dir(app, sub="")`(AI_DATA_ROOT 하위 또는 <repo>/data/<app>, mkdir 자동)는 **저장소 내부 data 전용**이라 외부 저장소 경로에는 부적합. 저장소 밖 경로용 공용 해석 함수는 없음(resolve_path/get_repo_root 류 없음, grant_radar/report.py:22 의 HAEHAN_DATA_DIR 패턴만 유사).
**변경안(최소)**: 환경변수 `HAEHAN_G2B_FAX_DIR`(개별팩스 디렉터리 전체), 기본값 기존 경로 유지 → 동작 불변.
```diff
+import os
-G2B_BASE = Path("C:/work/05. g2b/exports/개별팩스")
+G2B_BASE = Path(os.environ.get("HAEHAN_G2B_FAX_DIR", "C:/work/05. g2b/exports/개별팩스"))
```
docstring :5,6 도 갱신. (선택: data_paths.py 에 `get_external_dir(env, default)` 신규 함수 — 기존 코드 보존, 다른 하드코딩 정리에 재사용. 이번엔 1줄안 권장.)
**영향 테스트**: `tests-for scripts/hanafax/bulk_send.py` = 0건. 신규 테스트 1(환경변수 설정 시 G2B_BASE 반영). **라우트 영향**: bulk_send 를 import 하는 곳 없음(CLI 스크립트).
**위험**: 낮음(미설정 시 무변화). **후속(범위 밖)**: send_kras_final_campaign.py:40, export_kras_fax_pdf.py:30,31 의 사용자 홈(Downloads) 절대경로, scripts/instagram/__init__.py:16 IMAGE_ROOT.
**작업량**: S.

---
## 브랜치 계획
- 브랜치 `stage/maturity-b1` (master 3eb93cad 이후 병합 상태 기준으로 생성, worktree 별도). 건당 1커밋:
  1. `fix(eum)`: 일일점검 실패 기록·알림·종료코드 + 테스트
  2. `test(audit)`: 2a 감사 스크립트 대상 파일 교체
  3. `test`: 2b blog assets import 정정
  4. `test`: 2c cafe collector import 정정(+전체 재실행 결과)
  5. `test`: 2d deployment 페이지 경로 정정
  6. `feat(ops)`: publish_guard 래퍼 + 테스트(적용 전)
  7. `feat`: 래퍼를 YouTube·인스타·메일·문의에 적용
  8. (제안 A 채택 시) `chore(local_agent)`: 삼킴 로그 정리
  9. `fix(hanafax)`: G2B_BASE 환경변수화 + 테스트
- 커밋마다: layer_count·codebase_layer_audit·`tests/test_codebase_layer_audit.py`·quality_gate·skeleton_gate(신규 파일은 registry_sync --fix)와 해당 영향 테스트. verify_change·병합·push 는 메인이 직렬로.

## 실행 순서
2a(가장 먼저: 보안 게이트가 초록이 되어야 이후 게이트 신뢰) → 2b·2c·2d → 1(EUM) → 5(하나팩스) → 3(래퍼→적용) → 4(범위 결정 후).
근거: 테스트 복구가 이후 모든 커밋의 회귀 판정 기준이 되고, 3번 래퍼는 1번 EUM 알림 방식과 통일(`telegram_sender` + `log_op`)하기 위해 1번 뒤가 자연스럽다. 단 1번에서 래퍼를 미리 쓰지 않고 같은 두 호출(log_op+send_message)로 구현해 나중에 래퍼로 치환.

## 사용자 결정이 필요한 항목
- D1. EUM `no_eum_tab_or_login`(재로그인 필요)도 실패·알림으로 볼지, 스킵 유지할지. 연속 실패 알림을 하루 1회로 제한할지.
- D2. EUM 근본원인(CDP 9223 가 왜 죽어 있는지) 조사를 이번 배치에 포함할지, 별도로 할지. 스케줄러 재시도 설정은 PC 에서 `schtasks /query`(읽기 전용) 확인이 필요.
- D3. 래퍼 위치 `scripts/publish_guard.py`(L5) 승인 및 scripts→ai_orchestrator.clients import 허용 여부(게이트 결과에 따라 대안: 래퍼가 telegram 전송 함수를 호출자에게서 주입받음).
- D4. 4번 범위: 제안 A(로그 정리만) / B(다른 경로 재측정) / 보류. 성숙도 평가 문서의 과대 수치를 정정할지.
- D5. 2a 감사 스크립트 수정 시 "낡는 감사"를 막는 구조 개선(라우터 분할 후에도 대상 파일을 자동 탐색)을 이번에 할지, 보안 2단계로 넘길지.
- D6. 하나팩스: 1줄안(권장) vs `get_external_dir` 공용 헬퍼 추가. Downloads 경로 후속 정리를 같은 배치에 넣을지.
- D7. 인스타·메일 알림 정책: 실패마다 개별 알림 vs 배치 요약 1회.
