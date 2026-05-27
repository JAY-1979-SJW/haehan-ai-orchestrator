"""Modular SmartStore product registration pipeline.

The package separates product registration into read, prepare, and approval
stages. Existing SmartStore helpers remain available; these modules provide
stable boundaries for gates and future implementation work.
"""
from __future__ import annotations

from scripts.smartstore.product_register.pipeline import build_product_register_pipeline

__all__ = ["build_product_register_pipeline"]
