"""Google workflows 공개 API — 책임별 leaf 모듈 aggregator.

actions/catalog/execute/report 기능이 각 leaf 에 구현돼 있다.
[docs/module_separation_standard.md]
"""

from __future__ import annotations

from scripts.google.common.workflows_actions import (  # noqa: F401
    GOOGLE_WORK_ACTIONS,
    WRITE_ACTIONS,
    _read_actions,
    get_action,
    parse_kv_args,
)
from scripts.google.common.workflows_catalog import (  # noqa: F401
    build_action_catalog,
    build_adapter_catalog,
    build_adapter_profiles,
    build_undeveloped_report,
    save_action_catalog,
    save_adapter_catalog,
    save_undeveloped_report,
)
from scripts.google.common.workflows_common import (  # noqa: F401
    ACTION_CATALOG_DIR,
    ADAPTER_CATALOG_DIR,
    APPROVAL_PHRASE,
    EXECUTION_DIR,
    LATEST_ACTION_CATALOG,
    LATEST_ADAPTER_CATALOG,
    LATEST_PREPARE,
    LATEST_UNDEVELOPED_REPORT,
    PREPARE_DIR,
    UNDEVELOPED_REPORT_DIR,
    VERIFICATION_DIR,
    GoogleExecutionAdapter,
    GoogleWorkAction,
)
from scripts.google.common.workflows_execute import (  # noqa: F401
    execute_prepared_action,
    prepare_action,
    verify_execution_result,
)
from scripts.google.common.workflows_report import (  # noqa: F401
    print_action_summary,
    print_adapter_summary,
    print_undeveloped_summary,
)
