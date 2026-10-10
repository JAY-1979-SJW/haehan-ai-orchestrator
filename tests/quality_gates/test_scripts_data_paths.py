"""scripts/ 쪽 런타임 데이터 경로 — 환경변수가 없으면 값 불변(저장소의 data/), HAEHAN_DATA_ROOT 가 있으면 전부 그 아래.

배경: 포터블 앱은 실행마다 TEMP 에 풀려 번들 안(`<번들>/data`)에 쓴 상태 파일은 앱 종료 때 사라진다(SCRIPTS_DATA_PATHS_1.md).
읽는 쪽(ai_orchestrator, 이미 data_dir() 사용)과 쓰는 쪽(scripts)이 같은 위치를 보는지도 함께 고정한다.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

# (모듈, 표현식, data 루트 아래 상대 경로) — 표현식은 모듈을 import 한 뒤 평가한다.
ITEMS: list[tuple[str, str, tuple[str, ...]]] = [
    # 배치 1 — ai_orchestrator 가 이미 data_dir() 를 쓰는 짝(읽는 곳과 쓰는 곳 일치)
    ("tools.runtime.session_probe", "OUTPUT_PATH", ("login_session_monitor_latest.json",)),
    ("scripts.naver.cafe.analysis.organizer", "_DATA_DIR", ("cafe",)),
    ("scripts.naver.cafe.collection.explorer", "_DATA_DIR", ("cafe",)),
    ("scripts.naver.blog.core.writer_pro", "DRAFT_DIR", ("blog_drafts",)),
    ("scripts.naver.blog.unsplash_images", "UPLOADS_DIR", ("blog_uploads",)),
    ("scripts.naver.blog.unsplash_images", "_UNSPLASH_CACHE", ("unsplash_images.json",)),
    ("scripts.naver.blog.marketing.topics", "RESEARCH_FILE", ("blog_topic_research_latest.json",)),
    ("scripts.naver.blog.marketing.images", "_DEFAULT_DATA_DIR", ()),
    ("scripts.naver.smartstore.product.category_cache", "CACHE_PATH", ("smartstore", "categories.json")),
    ("scripts.naver.smartstore.product.detail_collector", "PRODUCTS_DIR", ("smartstore", "products")),
    ("scripts.hanafax.batch", "DATA_DIR", ()),
    ("scripts.naver.shopping.crawl", "DB_PATH", ("shopping_competitor_v2.db",)),
    ("scripts.naver.blog.accounts", 'get_account("skyjwsin")["cache_file"]', ("blog_topic_cache_skyjwsin.json",)),
    ("scripts.naver.blog.accounts", 'get_account("skyjwshin")["cache_file"]', ("blog_topic_cache_skyjwshin.json",)),
    # 배치 2a — 계정·토큰·기록·상태
    ("scripts.auth.credentials", "CRED_FILE", ("credentials.json",)),
    ("scripts.auth.credentials", "KEY_FILE", (".cred.key",)),
    ("scripts.auth.auth_session", "SESSIONS_DIR", ("sessions",)),
    ("scripts.youtube.oauth", "TOKEN_DIR", ("secrets",)),
    ("scripts.youtube.uploader", "PLAN_DIR", ("youtube_upload_plans",)),
    ("scripts.youtube.uploader", "RESULT_DIR", ("youtube_upload_results",)),
    ("scripts.inquiry.store", "_FILE", ("inquiries", "inquiries.jsonl")),
    ("scripts.community.scheduler", "_DIR", ("community",)),
    ("scripts.community.registry", "_SITES_FILE", ("community", "sites.json")),
    ("scripts.community.notifier", "_CFG", ("community", "notify_config.json")),
    ("scripts.naver.blog.automation.store", "DEFAULT_BASE", ("blog_automation",)),
    ("scripts.form.personal_profile", "PROFILE_FILE", ("profile.json",)),
    # 배치 2b — 공용 cdp.db 와 로그·세션·일정 DB
    ("scripts.browser.cdp.cdp_db", "DB_PATH", ("cdp.db",)),
    ("scripts.common.critical_logger", "LOG_DIR", ("logs",)),
    ("scripts.common.critical_logger", "DB_PATH", ("cdp.db",)),
    ("scripts.common.op_log", "LOG_DIR", ("logs",)),
    ("scripts.common.op_log", "DB_PATH", ("cdp.db",)),
    ("scripts.common.logger", "LOG_DIR", ("logs",)),
    ("scripts.common.realtime_audit", "LOG_DIR", ("logs",)),
    ("scripts.browser.cdp.connection", "_DAEMON_STATE", ("cdp_daemon_state.json",)),
    ("scripts.browser.page.web_connector", "SESSION_BASE_DIR", ("browser_sessions",)),
    ("scripts.browser.cdp.cdp_force_start", "PID_FILE", ("cdp_force_pid.json",)),
    ("scripts.naver.automation.scheduler", "DB_PATH", ("cdp.db",)),
    ("scripts.naver.automation.error_recovery", "DB_PATH", ("cdp.db",)),
    ("scripts.naver.blog.management.schedule", "DB_PATH", ("cdp.db",)),
    ("scripts.naver.blog.management.analytics", "DB_PATH", ("cdp.db",)),
    ("scripts.naver.smartstore.automation.analytics_dashboard", "DB_PATH", ("cdp.db",)),
    ("scripts.naver.smartstore.automation.competitor_analysis", "DB_PATH", ("cdp.db",)),
    ("scripts.naver.smartstore.product.bulk", "DB_PATH", ("cdp.db",)),
    ("scripts.naver.blog.gonobi.db", "_DEFAULT_DB", ("gonobi.db",)),
    ("scripts.common.youtube_search_cache", "SEARCH_CACHE_DB", ("youtube_search_cache.db",)),
]

_CLEAN = ("HAEHAN_DATA_ROOT", "HAEHAN_DATA_DIR", "HAEHAN_STORAGE_DIR", "LOG_DIR")


def _resolve(extra: dict[str, str]) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in _CLEAN and k.upper() != "PYTHONPATH"}
    env["PYTHONUTF8"] = "1"
    env.update(extra)
    spec = json.dumps([(m, e) for m, e, _ in ITEMS])
    code = (
        "import importlib, json\n"
        f"items = json.loads({spec!r})\n"
        "out = {}\n"
        "for m, e in items:\n"
        "    try:\n"
        "        mod = importlib.import_module(m)\n"
        "        out[m + ':' + e] = str(eval(e, vars(mod)))\n"
        "    except Exception as exc:\n"
        "        out[m + ':' + e] = 'ERR ' + type(exc).__name__ + ': ' + str(exc)[:120]\n"
        "print(json.dumps(out))\n"
    )
    r = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=300,
    )
    assert r.returncode == 0, r.stderr[-800:]
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_unchanged_without_env():
    assert ITEMS, "비교 대상 0건이면 아래 검사가 공허해진다"
    got = _resolve({})
    assert len(got) == len(ITEMS)
    bad = [
        (m, e, got[f"{m}:{e}"], str(REPO.joinpath("data", *tail)))
        for m, e, tail in ITEMS
        if got[f"{m}:{e}"] != str(REPO.joinpath("data", *tail))
    ]
    assert not bad, bad


def test_follow_data_root(tmp_path):
    assert ITEMS
    root = tmp_path / "userdata"
    got = _resolve({"HAEHAN_DATA_ROOT": str(root)})
    assert len(got) == len(ITEMS)
    bad = [
        (m, e, got[f"{m}:{e}"], str((root / "data").joinpath(*tail)))
        for m, e, tail in ITEMS
        if got[f"{m}:{e}"] != str((root / "data").joinpath(*tail))
    ]
    assert not bad, bad


@pytest.mark.parametrize(
    ("scripts_mod", "scripts_attr", "orch_mod", "orch_attr"),
    [
        ("tools.runtime.session_probe", "OUTPUT_PATH", "ai_orchestrator.connectors.session_status_router", "DATA_PATH"),
        (
            "scripts.naver.cafe.collection.explorer",
            "_DATA_DIR",
            "ai_orchestrator.connectors.naver_cafe.naver_cafe_router",
            "_CAFE_DIR",
        ),
        (
            "scripts.naver.blog.core.writer_pro",
            "DRAFT_DIR",
            "ai_orchestrator.connectors.naver_blog.naver_blog_router",
            "DRAFTS_DIR",
        ),
        (
            "scripts.naver.blog.unsplash_images",
            "UPLOADS_DIR",
            "ai_orchestrator.connectors.naver_blog.naver_blog_router",
            None,
        ),
        (
            "scripts.naver.blog.marketing.topics",
            "RESEARCH_FILE",
            "ai_orchestrator.marketing.marketing_ops_router",
            "_RESEARCH_FILE",
        ),
    ],
)
def test_writer_and_reader_agree_on_the_desktop_location(tmp_path, scripts_mod, scripts_attr, orch_mod, orch_attr):
    """데스크톱(HAEHAN_DATA_ROOT)에서 scripts(쓰기)와 ai_orchestrator(읽기)가 같은 파일을 본다."""
    if orch_attr is None:
        pytest.skip("읽는 쪽이 상수가 아니라 함수 안에서 계산 — 위 위치 시험으로 갈음")
    env = {k: v for k, v in os.environ.items() if k not in _CLEAN and k.upper() != "PYTHONPATH"}
    env["PYTHONUTF8"] = "1"
    env["HAEHAN_DATA_ROOT"] = str(tmp_path / "ud")
    code = (
        "import importlib\n"
        f"a = getattr(importlib.import_module({scripts_mod!r}), {scripts_attr!r})\n"
        f"b = getattr(importlib.import_module({orch_mod!r}), {orch_attr!r})\n"
        "print(str(a) == str(b), a, b)\n"
    )
    r = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=300,
    )
    assert r.stdout.startswith("True"), r.stdout + r.stderr[-500:]


def _youtube_token_file(extra: dict[str, str]) -> str:
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in (*_CLEAN, "YOUTUBE_OAUTH_TOKEN_FILE") and k.upper() != "PYTHONPATH"
    }
    env["PYTHONUTF8"] = "1"
    env.update(extra)
    code = "from ai_orchestrator.connectors.youtube import upload; print(upload._TOKEN_FILE)"
    r = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=300,
    )
    assert r.returncode == 0, r.stderr[-500:]
    return r.stdout.strip().splitlines()[-1]


def test_youtube_upload_token_file_is_absolute_and_follows_storage(tmp_path):
    """예전 기본값은 cwd 상대 문자열이었다 — 환경변수 없으면 같은 위치(절대 경로), DATA_ROOT 가 있으면 userData/storage 아래."""
    name = "youtube_oauth_authorized_user.json"
    assert _youtube_token_file({}) == str(REPO / "ai_orchestrator" / "storage" / "secrets" / name)
    root = tmp_path / "ud"
    assert _youtube_token_file({"HAEHAN_DATA_ROOT": str(root)}) == str(root / "storage" / "secrets" / name)
    # scripts.youtube.oauth 가 data/secrets 에 이미 토큰을 썼다면 그쪽을 쓴다
    (root / "data" / "secrets").mkdir(parents=True)
    (root / "data" / "secrets" / name).write_text("{}", encoding="utf-8")
    assert _youtube_token_file({"HAEHAN_DATA_ROOT": str(root)}) == str(root / "data" / "secrets" / name)
    assert _youtube_token_file({"HAEHAN_DATA_ROOT": str(root), "YOUTUBE_OAUTH_TOKEN_FILE": "x.json"}) == "x.json"
