"""Product data loading gate for SmartStore registration."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ProductDataSource:
    path: str
    data: dict[str, Any]
    encoding: str = "utf-8"
    inline_blocked: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "data": self.data,
            "encoding": self.encoding,
            "inline_blocked": self.inline_blocked,
        }


def read_utf8_json_file(path: str | Path) -> ProductDataSource:
    source = Path(path)
    if source.suffix.lower() != ".json":
        raise ValueError("product data must be a .json file encoded as UTF-8")
    try:
        raw = source.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("product data JSON must be UTF-8 encoded") from exc
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("product data JSON must be an object")
    return ProductDataSource(path=str(source), data=data)


def require_product_data_arg(args: list[str], *, sample_path: str = "data/sample_product_data.json") -> ProductDataSource:
    path = ""
    for arg in args:
        text = str(arg)
        if text.startswith("--data=") or text.startswith("--file="):
            path = text.split("=", 1)[1]
            break
    if not path:
        raise ValueError(
            f"product data required: --data=<utf8-json-file>; sample={sample_path}. "
            "Inline/stdin Korean product data is blocked to prevent mojibake."
        )
    return read_utf8_json_file(path)
