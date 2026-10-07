"""네이버 블로그 자산 명령 핸들러"""
from __future__ import annotations

import json

from scripts.common.gate import check as gate_check
from scripts.naver.common.router_common import _int_option, _option_value


def _blog_assets_plan(blog_id, target_pages, build_blog_asset_plan, save_blog_asset_plan) -> None:
    """blog-assets plan/prepare."""
    plan = build_blog_asset_plan(blog_id, target_pages=target_pages)
    path = save_blog_asset_plan(plan)
    print(json.dumps(plan.to_dict(), ensure_ascii=False, indent=2))
    print(f"saved: {path}")


def _blog_assets_inventory(args, blog_id, target_pages, collect_blog_asset_inventory) -> None:
    """blog-assets inventory/collect/scan."""
    gate_check("scan_page")
    port = _int_option(args, "--port=", 9232)
    max_index_pages = _int_option(args, "--max-index-pages=", 50)
    scroll_steps = _int_option(args, "--scroll-steps=", 10)
    wait_raw = _option_value(args, "--wait=") or "2.5"
    try:
        wait_seconds = float(wait_raw)
    except ValueError as exc:
        raise SystemExit("--wait=<seconds> required") from exc
    payload = collect_blog_asset_inventory(
        blog_id=blog_id,
        target_pages=target_pages,
        port=port,
        wait_seconds=wait_seconds,
        max_index_pages=max_index_pages,
        scroll_steps=scroll_steps,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if not payload.get("ok"):
        raise SystemExit(1)


def _blog_assets_analyze(args, analyze_blog_asset_images, save_blog_image_analysis) -> None:
    """blog-assets analyze."""
    from pathlib import Path

    inventory_path = Path(_option_value(args, "--data=") or "data/naver_blog_asset_inventory_latest.json")
    if not inventory_path.exists():
        raise SystemExit(f"inventory file not found: {inventory_path}")
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    payload = analyze_blog_asset_images(inventory)
    path = save_blog_image_analysis(payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"saved: {path}")


def _blog_assets_pixel_analyze(args, analyze_blog_asset_images_with_pixels, save_blog_pixel_analysis) -> None:
    """blog-assets pixel-analyze."""
    from pathlib import Path

    inventory_path = Path(_option_value(args, "--data=") or "data/naver_blog_asset_inventory_latest.json")
    if not inventory_path.exists():
        raise SystemExit(f"inventory file not found: {inventory_path}")
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    limit = _int_option(args, "--limit=", 100)
    output_dir = _option_value(args, "--output-dir=") or "tmp/naver_blog_downloaded_images"
    payload = analyze_blog_asset_images_with_pixels(inventory, output_dir=output_dir, limit=limit)
    path = save_blog_pixel_analysis(payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"saved: {path}")


def _blog_assets_manifest(args, create_shopping_upload_manifest, save_shopping_upload_manifest) -> None:
    """blog-assets manifest."""
    from pathlib import Path

    inventory_path = Path(_option_value(args, "--data=") or "data/naver_blog_asset_inventory_latest.json")
    if not inventory_path.exists():
        raise SystemExit(f"inventory file not found: {inventory_path}")
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    confirm = _option_value(args, "--rights-confirm=") or ""
    payload = create_shopping_upload_manifest(inventory, rights_confirm=confirm)
    path = save_shopping_upload_manifest(payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"saved: {path}")
    if not payload.get("ok"):
        raise SystemExit(1)


def _cmd_blog_assets(sub: str, args: list[str]) -> None:
    from scripts.naver.blog.assets import (
        analyze_blog_asset_images,
        analyze_blog_asset_images_with_pixels,
        collect_blog_asset_inventory,
        create_shopping_upload_manifest,
        build_blog_asset_plan,
        save_blog_image_analysis,
        save_blog_asset_plan,
        save_blog_pixel_analysis,
        save_shopping_upload_manifest,
    )

    blog_id = _option_value(args, "--blog-id=") or _option_value(args, "--blog=") or "gonobi"
    target_pages = _int_option(args, "--target=", 1000)

    if sub in ("plan", "prepare"):
        _blog_assets_plan(blog_id, target_pages, build_blog_asset_plan, save_blog_asset_plan)
        return

    if sub in ("inventory", "collect", "scan"):
        _blog_assets_inventory(args, blog_id, target_pages, collect_blog_asset_inventory)
        return

    if sub in ("analyze", "analysis", "image-analysis", "images"):
        _blog_assets_analyze(args, analyze_blog_asset_images, save_blog_image_analysis)
        return

    if sub in ("pixel-analyze", "pixel-analysis", "visual-analyze", "download-analyze"):
        _blog_assets_pixel_analyze(args, analyze_blog_asset_images_with_pixels, save_blog_pixel_analysis)
        return

    if sub in ("manifest", "shopping-manifest", "reuse-manifest"):
        _blog_assets_manifest(args, create_shopping_upload_manifest, save_shopping_upload_manifest)
        return

    print("usage: python scripts/entry/cdp_cli.py naver blog-assets [plan|inventory|analyze|pixel-analyze|manifest] --blog-id=gonobi [--target=1000]")
