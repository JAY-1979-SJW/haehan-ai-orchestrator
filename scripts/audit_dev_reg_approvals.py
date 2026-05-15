"""Compatibility wrapper for the archived developer registration audit."""
from __future__ import annotations

import sys

from scripts.archive.debug import audit_dev_reg_approvals as _impl

if __name__ == "__main__":
    raise SystemExit(_impl.main())

sys.modules[__name__] = _impl
