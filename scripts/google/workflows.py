"""Google workflows 공개 API — 책임별 leaf 모듈 aggregator.

actions/catalog/execute/report 기능이 각 leaf 에 구현돼 있다.
[docs/module_separation_standard.md]
"""
from __future__ import annotations

from .workflows_common import (  # noqa: F401
    GoogleWorkAction, GoogleExecutionAdapter,
    LATEST_ACTION_CATALOG, ACTION_CATALOG_DIR,
    LATEST_PREPARE, PREPARE_DIR, EXECUTION_DIR,
    LATEST_ADAPTER_CATALOG, ADAPTER_CATALOG_DIR,
    LATEST_UNDEVELOPED_REPORT, UNDEVELOPED_REPORT_DIR,
    VERIFICATION_DIR, APPROVAL_PHRASE,
)
from .workflows_actions import (  # noqa: F401
    _read_actions, get_action, parse_kv_args,
    WRITE_ACTIONS, GOOGLE_WORK_ACTIONS,
)
from .workflows_catalog import (  # noqa: F401
    build_adapter_profiles, build_action_catalog, save_action_catalog,
    build_adapter_catalog, save_adapter_catalog,
    build_undeveloped_report, save_undeveloped_report,
)
from .workflows_execute import (  # noqa: F401
    prepare_action, execute_prepared_action, verify_execution_result,
)
from .workflows_report import (  # noqa: F401
    print_action_summary, print_adapter_summary, print_undeveloped_summary,
)
