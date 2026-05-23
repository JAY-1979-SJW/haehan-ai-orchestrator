"""Keep direct script execution from using workspace-local bytecode caches."""
from __future__ import annotations

import os
import sys
from pathlib import Path

if "PYTHONPYCACHEPREFIX" not in os.environ and "TEMP" in os.environ:
    pycache = Path(os.environ["TEMP"]) / "haehan_scripts_pycache"
    os.environ["PYTHONPYCACHEPREFIX"] = str(pycache)
    sys.pycache_prefix = str(pycache)
