from __future__ import annotations

from scripts.naver.blog import assets
from scripts.naver.blog.seo import assets as seo_assets


def test_blog_asset_plan_is_rights_aware():
    plan = assets.build_blog_asset_plan("gonobi", target_pages=1000).to_dict()

    assert plan["ok"] is True
    assert plan["blog_id"] == "gonobi"
    assert plan["target_pages"] == 1000
    assert plan["required_confirm_text"] == assets.RIGHTS_CONFIRM_TEXT
    assert any("Do not download or reuse images" in rule for rule in plan["collection_rules"])


def test_normalize_post_url_from_postview():
    url = "https://blog.naver.com/PostView.naver?blogId=gonobi&logNo=223456789012&from=menu"

    assert assets.normalize_post_url(url) == "https://blog.naver.com/gonobi/223456789012"


def test_mobile_post_url_uses_mobile_blog_reader():
    assert (
        assets.mobile_post_url("https://blog.naver.com/gonobi/223456789012?from=menu")
        == "https://m.blog.naver.com/gonobi/223456789012"
    )


def test_extract_post_links_dedupes_and_filters_blog_posts():
    snapshot = {
        "links": [
            {"href": "https://blog.naver.com/PostView.naver?blogId=gonobi&logNo=223456789012", "text": "First"},
            {"href": "https://blog.naver.com/gonobi/223456789012?x=1", "text": "Duplicate"},
            {"href": "https://blog.naver.com/gonobi/223456789013", "text": "Second"},
            {"href": "https://example.com/not-blog", "text": "External"},
        ]
    }

    rows = assets.extract_post_links(snapshot, blog_id="gonobi")

    assert rows == [
        {"url": "https://blog.naver.com/gonobi/223456789012", "title": "First"},
        {"url": "https://blog.naver.com/gonobi/223456789013", "title": "Second"},
    ]


def test_build_post_asset_record_marks_images_unverified():
    snapshot = {
        "title": "Lighting post",
        "body_sample": "body" * 1000,
        "images": [
            {
                "src": "https://postfiles.pstatic.net/MjAy/image.jpg",
                "alt": "pendant light",
                "natural_width": 1200,
                "natural_height": 900,
            },
            {"src": "https://ssl.pstatic.net/static/icon.png", "alt": "icon"},
        ],
    }

    record = assets.build_post_asset_record(
        snapshot,
        source_url="https://blog.naver.com/gonobi/223456789012",
    )

    assert record["image_count"] == 1
    assert record["shopping_reuse_allowed"] is False
    assert record["images"][0]["rights_status"] == "unverified"
    assert record["images"][0]["reuse_allowed"] is False
    assert len(record["body_sample"]) == 2000


def test_shopping_manifest_blocks_without_rights_confirmation():
    inventory = {"posts": [{"images": [{"src": "https://postfiles.pstatic.net/a.jpg"}]}]}

    manifest = assets.create_shopping_upload_manifest(inventory, rights_confirm="")

    assert manifest["ok"] is False
    assert manifest["code"] == "rights_confirmation_required"
    assert manifest["items"] == []


def test_classify_blog_image_assigns_detail_roles():
    spec = assets.classify_blog_image(
        {"src": "https://x/spec.png", "width": 800, "height": 2462},
        index=17,
        total=18,
    )
    square = assets.classify_blog_image(
        {"src": "https://x/thumb.png", "width": 750, "height": 748},
        index=18,
        total=18,
    )
    wide = assets.classify_blog_image(
        {"src": "https://x/compare.png", "width": 800, "height": 261},
        index=6,
        total=18,
    )

    assert spec["role"] == "spec_table_or_long_detail"
    assert "spec" in spec["tags"]
    assert square["role"] == "thumbnail_candidate"
    assert square["representative_score"] >= 70
    assert wide["role"] == "wide_comparison_or_banner"


def test_analyze_blog_asset_images_builds_representative_candidates():
    inventory = {
        "source_url": "https://blog.naver.com/prologue/PrologueList.naver?blogId=gonobi",
        "posts": [
            {
                "source_url": "https://blog.naver.com/gonobi/223456789012",
                "title": "Lighting post",
                "images": [
                    {"src": "https://x/opening.png", "width": 800, "height": 1031},
                    {"src": "https://x/strip.png", "width": 800, "height": 261},
                    {"src": "https://x/spec.png", "width": 800, "height": 2462},
                    {"src": "https://x/square.png", "width": 750, "height": 748},
                ],
            }
        ],
    }

    report = assets.analyze_blog_asset_images(inventory)

    assert report["ok"] is True
    assert report["image_count"] == 4
    assert report["role_counts"]["spec_table_or_long_detail"] == 1
    assert report["representative_candidates"][0]["role"] == "thumbnail_candidate"
    assert report["shopping_reuse_allowed"] is False


def test_analyze_image_pixels_detects_white_on_white_risk(tmp_path):
    from PIL import Image, ImageDraw

    path = tmp_path / "white_product.png"
    image = Image.new("RGB", (400, 400), (250, 250, 250))
    draw = ImageDraw.Draw(image)
    draw.rectangle((80, 170, 320, 230), fill=(226, 230, 235))
    image.save(path)

    metrics = assets.analyze_image_pixels(path)

    assert metrics["white_on_white_risk"] is True
    assert metrics["near_white_ratio"] > 0.68


def test_pixel_analysis_adjusts_representative_score(monkeypatch, tmp_path):
    from PIL import Image

    local = tmp_path / "img.png"
    Image.new("RGB", (400, 400), (250, 250, 250)).save(local)
    inventory = {
        "source_url": "https://blog.naver.com/prologue/PrologueList.naver?blogId=gonobi",
        "posts": [
            {
                "source_url": "https://blog.naver.com/gonobi/223456789012",
                "title": "Lighting post",
                "images": [{"src": "https://x/square.png", "width": 800, "height": 800}],
            }
        ],
    }

    # blog/assets.py 는 import * 스텁이라 실제 구현 모듈(seo.assets)의 이름을 패치해야 한다.
    monkeypatch.setattr(
        seo_assets,
        "download_blog_asset_images",
        lambda inventory, output_dir, limit: {
            "ok": True,
            "code": "ok",
            "downloaded_count": 1,
            "items": [{"post_index": 1, "image_index": 1, "src": "https://x/square.png", "path": str(local), "bytes": 10}],
            "errors": [],
        },
    )

    report = assets.analyze_blog_asset_images_with_pixels(inventory, output_dir=tmp_path)
    analyzed = report["posts"][0]["analyzed_images"][0]

    assert report["pixel_summary"]["downloaded_count"] == 1
    assert analyzed["pixel_metrics"]["white_on_white_risk"] is True
    assert "white_on_white_risk" in analyzed["warnings"]
    assert analyzed["representative_score"] < 80


def test_shopping_manifest_allows_after_explicit_rights_confirmation():
    inventory = {
        "source_url": "https://blog.naver.com/prologue/PrologueList.naver?blogId=gonobi",
        "posts": [
            {
                "source_url": "https://blog.naver.com/gonobi/223456789012",
                "title": "Lighting post",
                "images": [
                    {
                        "src": "https://postfiles.pstatic.net/a.jpg",
                        "alt": "light",
                        "width": 1200,
                        "height": 900,
                    }
                ],
            }
        ],
    }

    manifest = assets.create_shopping_upload_manifest(
        inventory,
        rights_confirm=assets.RIGHTS_CONFIRM_TEXT,
    )

    assert manifest["ok"] is True
    assert manifest["item_count"] == 1
    assert manifest["items"][0]["rights_status"] == "confirmed_by_operator"
