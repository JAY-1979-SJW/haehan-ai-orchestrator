"""서버 시작 시 가장 먼저 import 하는 부트스트랩 — 저장 폴더 준비 + 예전 위치 데이터 1회 복사 이행.

어떤 저장소(DB)도 열리기 전에 실행돼야 한다(옛 users.db 가 먼저 이행돼야 '계정이 비어 있지 않은' 상태가 되어
첫 가입자 자동 승인이 일어나지 않는다). asgi.py 의 첫 프로젝트 import 로 둔다. 실패해도 시작은 막지 않는다.
"""

from __future__ import annotations

from .legacy_import import import_legacy_install
from .migrate import migrate_legacy_data
from .runtime import ensure_runtime_dirs

ensure_runtime_dirs()
MIGRATION_RESULT = migrate_legacy_data()
LEGACY_IMPORT_RESULT = import_legacy_install()  # 예전 설치 폴더(Haehan AI) 데이터 가져오기 — 첫 실행·복사만·실패해도 시작은 계속
