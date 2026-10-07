"""Naver Blog asset inventory tools.

The tools are intentionally rights-aware. They can inventory public blog posts
and image metadata for review, but any shopping-mall reuse manifest requires an
explicit rights confirmation from the operator.
"""

from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from scripts.naver.mail.read import cdp

ROOT = Path(__file__).resolve().parents[4]
LATEST_BLOG_ASSET_PLAN_PATH = ROOT / "data" / "naver_blog_asset_plan_latest.json"
LATEST_BLOG_ASSET_INVENTORY_PATH = ROOT / "data" / "naver_blog_asset_inventory_latest.json"
LATEST_BLOG_IMAGE_ANALYSIS_PATH = ROOT / "data" / "naver_blog_image_analysis_latest.json"
LATEST_BLOG_PIXEL_ANALYSIS_PATH = ROOT / "data" / "naver_blog_pixel_image_analysis_latest.json"
LATEST_BLOG_SHOPPING_MANIFEST_PATH = ROOT / "data" / "naver_blog_shopping_asset_manifest_latest.json"
DEFAULT_IMAGE_DOWNLOAD_DIR = ROOT / "tmp" / "naver_blog_downloaded_images"
RIGHTS_CONFIRM_TEXT = "I_HAVE_RIGHTS_TO_USE_NAVER_BLOG_ASSETS"


@dataclass
class BlogAssetPlan:
    ok: bool
    action: str
    blog_id: str
    target_pages: int
    source_url: str
    required_confirm_text: str = RIGHTS_CONFIRM_TEXT
    collection_rules: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def blog_prologue_url(blog_id: str) -> str:
    encoded = urllib.parse.quote(blog_id.strip())
    return (
        "https://blog.naver.com/prologue/PrologueList.naver"
        f"?blogId={encoded}&skinType=&skinId=&from=menu&userSelectMenu=true"
    )


def blog_post_list_url(blog_id: str, page: int) -> str:
    encoded = urllib.parse.quote(blog_id.strip())
    return (
        "https://blog.naver.com/PostList.naver"
        f"?blogId={encoded}&from=postList&categoryNo=0&currentPage={max(1, int(page))}"
    )


def mobile_post_url(url: str, *, blog_id: str = "") -> str:
    normalized = normalize_post_url(url, blog_id=blog_id)
    match = re.search(r"blog\.naver\.com/([^/?#]+)/(\d{6,})", normalized)
    if not match:
        return normalized
    return f"https://m.blog.naver.com/{match.group(1)}/{match.group(2)}"


def build_blog_asset_plan(blog_id: str, *, target_pages: int = 1000) -> BlogAssetPlan:
    return BlogAssetPlan(
        ok=True,
        action="naver_blog_asset_plan",
        blog_id=blog_id,
        target_pages=target_pages,
        source_url=blog_prologue_url(blog_id),
        collection_rules=[
            "Collect post URLs, titles, text samples, and image metadata first.",
            "Do not download or reuse images unless the operator owns the blog or has permission.",
            "Shopping-mall upload manifests require an explicit rights confirmation string.",
            "Keep source post URL and image URL for every asset for audit.",
            "Do not publish or upload automatically from this tool.",
        ],
    )


def save_blog_asset_plan(plan: BlogAssetPlan | dict[str, Any]) -> Path:
    payload = plan.to_dict() if isinstance(plan, BlogAssetPlan) else plan
    LATEST_BLOG_ASSET_PLAN_PATH.parent.mkdir(parents=True, exist_ok=True)
    LATEST_BLOG_ASSET_PLAN_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return LATEST_BLOG_ASSET_PLAN_PATH


def normalize_post_url(url: str, *, blog_id: str = "") -> str:
    text = str(url or "").strip()
    if not text:
        return ""
    parsed = urllib.parse.urlparse(text)
    query = urllib.parse.parse_qs(parsed.query)
    log_no = ""
    for key in ("logNo", "logno", "LogNo"):
        if query.get(key):
            log_no = query[key][0]
            break
    if not log_no:
        match = re.search(r"/(\d{6,})(?:\D|$)", parsed.path)
        if match:
            log_no = match.group(1)
    clean_blog_id = blog_id or query.get("blogId", [""])[0]
    if log_no and clean_blog_id:
        return f"https://blog.naver.com/{clean_blog_id}/{log_no}"
    return text.split("#", 1)[0]


def extract_post_links(snapshot: dict[str, Any], *, blog_id: str) -> list[dict[str, str]]:
    rows = []
    seen = set()
    for link in snapshot.get("links", []):
        if not isinstance(link, dict):
            continue
        href = str(link.get("href") or "")
        text = str(link.get("text") or "").strip()
        if "blog.naver.com" not in href:
            continue
        normalized = normalize_post_url(href, blog_id=blog_id)
        if not normalized or normalized in seen or normalized == blog_prologue_url(blog_id):
            continue
        if re.search(r"/\d{6,}$", normalized) or "PostView.naver" in href:
            seen.add(normalized)
            rows.append({"url": normalized, "title": text[:160]})
    return rows


def build_post_asset_record(snapshot: dict[str, Any], *, source_url: str, title: str = "") -> dict[str, Any]:
    images = []
    seen = set()
    for image in snapshot.get("images", []):
        if not isinstance(image, dict):
            continue
        src = str(image.get("src") or "")
        if not src or src in seen:
            continue
        if _is_ignored_image(src, str(image.get("alt") or "")):
            continue
        width = int(image.get("natural_width") or image.get("width") or 0)
        height = int(image.get("natural_height") or image.get("height") or 0)
        if width and height and max(width, height) < 300:
            continue
        seen.add(src)
        images.append(
            {
                "src": src,
                "alt": str(image.get("alt") or ""),
                "width": width,
                "height": height,
                "source_url": source_url,
                "rights_status": "unverified",
                "reuse_allowed": False,
            }
        )
    body_sample = str(snapshot.get("body_sample") or "")[:2000]
    return {
        "source_url": source_url,
        "title": title or str(snapshot.get("title") or ""),
        "body_sample": body_sample,
        "image_count": len(images),
        "images": images,
        "rights_status": "unverified",
        "shopping_reuse_allowed": False,
    }


def _is_ignored_image(src: str, alt: str) -> bool:
    lowered = f"{src} {alt}".lower()
    if lowered.startswith("data:image"):
        return True
    if "postfiles.pstatic.net" in lowered or "blogfiles.pstatic.net" in lowered:
        return False
    return any(token in lowered for token in ("favicon", "icon", "sp_common", "profile", "프로필"))


def validate_rights_confirm(confirm: str) -> bool:
    return str(confirm or "").strip() == RIGHTS_CONFIRM_TEXT


def create_shopping_upload_manifest(inventory: dict[str, Any], *, rights_confirm: str) -> dict[str, Any]:
    if not validate_rights_confirm(rights_confirm):
        return {
            "ok": False,
            "code": "rights_confirmation_required",
            "required_confirm_text": RIGHTS_CONFIRM_TEXT,
            "items": [],
            "messages": ["Shopping-mall reuse is blocked until asset rights are confirmed."],
        }
    items = []
    for post in inventory.get("posts", []):
        for image in post.get("images", []):
            items.append(
                {
                    "source_post_url": post.get("source_url", ""),
                    "source_title": post.get("title", ""),
                    "image_url": image.get("src", ""),
                    "alt": image.get("alt", ""),
                    "width": image.get("width", 0),
                    "height": image.get("height", 0),
                    "rights_status": "confirmed_by_operator",
                    "suggested_use": "shopping_detail_reference_or_owned_asset",
                }
            )
    return {
        "ok": True,
        "code": "ok",
        "action": "naver_blog_shopping_asset_manifest",
        "source_inventory": inventory.get("source_url", ""),
        "item_count": len(items),
        "items": items,
        "messages": ["Operator confirmed rights before shopping-mall reuse manifest creation."],
    }


def _classify_role(width: int, height: int, ratio: float, tags: list[str], recommendations: list[str]) -> str:
    """종횡비로 이미지 역할 분류(tags/recommendations 를 제자리 갱신)."""
    if ratio >= 2.0:
        role = "spec_table_or_long_detail"
        tags.extend(["detail", "spec"])
        recommendations.append("Use near the lower detail section; split or redraw if mobile text becomes small.")
    elif ratio <= 0.45:
        role = "wide_comparison_or_banner"
        tags.extend(["comparison", "detail"])
        recommendations.append("Use as a comparison row or feature strip, not as the main thumbnail.")
    elif abs(width - height) <= 80:
        role = "thumbnail_candidate"
        tags.extend(["thumbnail", "product"])
        recommendations.append("Candidate for representative image after contrast/background review.")
    elif ratio >= 1.15:
        role = "portrait_product_or_feature"
        tags.extend(["product", "feature"])
        recommendations.append("Use in the upper product story section.")
    else:
        role = "landscape_detail"
        tags.extend(["detail", "product"])
        recommendations.append("Use for installation/detail explanation blocks.")
    return role


def _representative_score(width: int, height: int, ratio: float, index: int, role: str) -> int:
    """대표 이미지 점수(0~100)."""
    representative_score = 0
    if width >= 750:
        representative_score += 20
    if abs(width - height) <= 100:
        representative_score += 35
    if 0.75 <= ratio <= 1.45:
        representative_score += 25
    if index <= 3:
        representative_score += 10
    if role == "spec_table_or_long_detail":
        representative_score -= 30
    if role == "wide_comparison_or_banner":
        representative_score -= 15
    representative_score = max(0, min(100, representative_score))
    return representative_score


def classify_blog_image(image: dict[str, Any], *, index: int, total: int) -> dict[str, Any]:
    width = int(image.get("width") or 0)
    height = int(image.get("height") or 0)
    ratio = round(height / width, 3) if width else 0.0
    src = str(image.get("src") or "")
    filename = src.split("?", 1)[0].rstrip("/").split("/")[-1]
    lower = urllib.parse.unquote(filename).lower()

    tags: list[str] = []
    warnings: list[str] = []
    recommendations: list[str] = []

    if width < 800:
        warnings.append("width_below_800")
    if width and height and max(width, height) < 600:
        warnings.append("low_resolution")

    role = _classify_role(width, height, ratio, tags, recommendations)

    if index == 1:
        tags.append("opening")
        recommendations.append("Good first detail section if it clearly states the main value proposition.")
    if index == total:
        tags.append("ending_or_thumbnail")
    if any(token in lower for token in ("spec", "스펙", "상세", "table")) or ratio >= 2.0:
        tags.append("spec_readability_check")
    if any(token in lower for token in ("thumb", "썸", "thumbnail")):
        tags.append("source_thumbnail")

    representative_score = _representative_score(width, height, ratio, index, role)

    if representative_score >= 70:
        recommendations.append("Review as a SmartStore representative image candidate.")
    elif representative_score < 35:
        recommendations.append("Keep as detail-page support material rather than representative image.")

    return {
        "index": index,
        "src": src,
        "filename": filename,
        "width": width,
        "height": height,
        "aspect_ratio_h_over_w": ratio,
        "role": role,
        "tags": sorted(set(tags)),
        "representative_score": representative_score,
        "warnings": warnings,
        "recommendations": recommendations,
        "rights_status": image.get("rights_status", "unverified"),
        "reuse_allowed": bool(image.get("reuse_allowed")),
    }


def analyze_blog_asset_images(inventory: dict[str, Any]) -> dict[str, Any]:
    posts_out = []
    all_items = []
    for post in inventory.get("posts", []):
        images = post.get("images", [])
        analyzed = [
            classify_blog_image(image, index=index, total=len(images)) for index, image in enumerate(images, start=1)
        ]
        all_items.extend(analyzed)
        posts_out.append(
            {
                "source_url": post.get("source_url", ""),
                "title": post.get("title", ""),
                "image_count": len(images),
                "analyzed_images": analyzed,
            }
        )

    role_counts: dict[str, int] = {}
    warning_counts: dict[str, int] = {}
    for item in all_items:
        role_counts[item["role"]] = role_counts.get(item["role"], 0) + 1
        for warning in item.get("warnings", []):
            warning_counts[warning] = warning_counts.get(warning, 0) + 1

    representative_candidates = sorted(
        all_items,
        key=lambda item: (-int(item.get("representative_score", 0)), int(item.get("index", 0))),
    )[:5]
    detail_sequence = [item for item in all_items if item["role"] != "thumbnail_candidate"]

    return {
        "ok": True,
        "code": "ok",
        "action": "naver_blog_image_analysis",
        "source_inventory": inventory.get("source_url", ""),
        "post_count": len(posts_out),
        "image_count": len(all_items),
        "role_counts": role_counts,
        "warning_counts": warning_counts,
        "representative_candidates": representative_candidates,
        "detail_sequence_recommendation": [
            {
                "index": item["index"],
                "role": item["role"],
                "filename": item["filename"],
                "recommendation": item["recommendations"][0] if item.get("recommendations") else "",
            }
            for item in detail_sequence[:20]
        ],
        "posts": posts_out,
        "shopping_reuse_allowed": False,
        "required_confirm_text": RIGHTS_CONFIRM_TEXT,
        "messages": [
            "Automated metadata analysis only. Pixel-level visual judgment still requires screenshot/vision review.",
            "Shopping-mall reuse remains blocked until asset rights are confirmed.",
        ],
    }


def download_blog_asset_images(
    inventory: dict[str, Any],
    *,
    output_dir: str | Path = DEFAULT_IMAGE_DOWNLOAD_DIR,
    limit: int = 100,
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    items = []
    errors = []
    count = 0
    for post_index, post in enumerate(inventory.get("posts", []), start=1):
        for image_index, image in enumerate(post.get("images", []), start=1):
            if count >= limit:
                break
            src = str(image.get("src") or "")
            if not src:
                continue
            ext = ".png"
            lower = src.split("?", 1)[0].lower()
            if lower.endswith((".jpg", ".jpeg")):
                ext = ".jpg"
            elif lower.endswith(".webp"):
                ext = ".webp"
            name = f"post_{post_index:03d}_image_{image_index:03d}{ext}"
            path = output / name
            try:
                request = urllib.request.Request(src, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(request, timeout=20) as response:
                    path.write_bytes(response.read())
                items.append(
                    {
                        "post_index": post_index,
                        "image_index": image_index,
                        "src": src,
                        "path": str(path),
                        "bytes": path.stat().st_size,
                    }
                )
                count += 1
            except Exception as exc:  # noqa: BLE001 - 이미지 처리/픽셀 분석 실패를 오류 레코드에 담아 계속 진행 — 읽기전용 분석, 쓰기 없음
                errors.append(
                    {"post_index": post_index, "image_index": image_index, "src": src, "error": str(exc)[:200]}
                )
        if count >= limit:
            break
    return {
        "ok": bool(items),
        "code": "ok" if items else "no_images_downloaded",
        "output_dir": str(output),
        "downloaded_count": len(items),
        "items": items,
        "errors": errors,
    }


def analyze_image_pixels(path: str | Path) -> dict[str, Any]:
    from PIL import Image, ImageStat

    image = Image.open(path).convert("RGB")
    width, height = image.size
    sample = image.copy()
    sample.thumbnail((160, 160))
    stat = ImageStat.Stat(sample)
    mean_rgb = tuple(round(v, 2) for v in stat.mean)
    luminance_values = []
    white_pixels = 0
    near_white_pixels = 0
    dark_pixels = 0
    saturated_pixels = 0
    pixels = list(sample.get_flattened_data() if hasattr(sample, "get_flattened_data") else sample.getdata())
    for red, green, blue in pixels:
        lum = 0.2126 * red + 0.7152 * green + 0.0722 * blue
        luminance_values.append(lum)
        if red >= 245 and green >= 245 and blue >= 245:
            white_pixels += 1
        if red >= 230 and green >= 230 and blue >= 230:
            near_white_pixels += 1
        if lum <= 70:
            dark_pixels += 1
        if max(red, green, blue) - min(red, green, blue) >= 80:
            saturated_pixels += 1
    total = max(1, len(pixels))
    mean_luminance = sum(luminance_values) / total
    variance = sum((value - mean_luminance) ** 2 for value in luminance_values) / total
    contrast_stddev = variance**0.5
    white_ratio = white_pixels / total
    near_white_ratio = near_white_pixels / total
    dark_ratio = dark_pixels / total
    saturated_ratio = saturated_pixels / total
    white_on_white_risk = near_white_ratio >= 0.68 and contrast_stddev <= 48
    text_or_spec_like = dark_ratio >= 0.045 and near_white_ratio >= 0.45 and contrast_stddev >= 35
    return {
        "path": str(path),
        "pixel_width": width,
        "pixel_height": height,
        "mean_rgb": mean_rgb,
        "mean_luminance": round(mean_luminance, 2),
        "contrast_stddev": round(contrast_stddev, 2),
        "white_ratio": round(white_ratio, 4),
        "near_white_ratio": round(near_white_ratio, 4),
        "dark_ratio": round(dark_ratio, 4),
        "saturated_ratio": round(saturated_ratio, 4),
        "white_on_white_risk": white_on_white_risk,
        "text_or_spec_like": text_or_spec_like,
    }


def analyze_blog_asset_images_with_pixels(
    inventory: dict[str, Any],
    *,
    output_dir: str | Path = DEFAULT_IMAGE_DOWNLOAD_DIR,
    limit: int = 100,
) -> dict[str, Any]:
    base = analyze_blog_asset_images(inventory)
    downloads = download_blog_asset_images(inventory, output_dir=output_dir, limit=limit)
    by_key: dict[tuple[int, int], dict[str, Any]] = {}
    for item in downloads.get("items", []):
        try:
            metrics = analyze_image_pixels(item["path"])
        except Exception as exc:  # noqa: BLE001 - 이미지 처리/픽셀 분석 실패를 오류 레코드에 담아 계속 진행 — 읽기전용 분석, 쓰기 없음
            metrics = {"path": item.get("path", ""), "error": str(exc)[:200]}
        by_key[(int(item["post_index"]), int(item["image_index"]))] = {**item, "pixel_metrics": metrics}

    white_on_white_count = 0
    text_like_count = 0
    for post_index, post in enumerate(base.get("posts", []), start=1):
        for image in post.get("analyzed_images", []):
            key = (post_index, int(image.get("index", 0)))
            downloaded = by_key.get(key)
            if not downloaded:
                continue
            metrics = downloaded.get("pixel_metrics", {})
            image["download_path"] = downloaded.get("path", "")
            image["pixel_metrics"] = metrics
            if metrics.get("white_on_white_risk"):
                white_on_white_count += 1
                image.setdefault("warnings", []).append("white_on_white_risk")
                image.setdefault("recommendations", []).append(
                    "Increase contrast or use a subtle background before using as a representative image."
                )
                image["representative_score"] = max(0, int(image.get("representative_score", 0)) - 20)
            if metrics.get("text_or_spec_like"):
                text_like_count += 1
                image.setdefault("tags", []).append("text_or_spec_like")
                if image.get("role") == "thumbnail_candidate":
                    image["representative_score"] = max(0, int(image.get("representative_score", 0)) - 15)

    all_images = [image for post in base.get("posts", []) for image in post.get("analyzed_images", [])]
    base["representative_candidates"] = sorted(
        all_images,
        key=lambda item: (-int(item.get("representative_score", 0)), int(item.get("index", 0))),
    )[:5]
    base["action"] = "naver_blog_pixel_image_analysis"
    base["download"] = downloads
    base["pixel_summary"] = {
        "downloaded_count": downloads.get("downloaded_count", 0),
        "white_on_white_risk_count": white_on_white_count,
        "text_or_spec_like_count": text_like_count,
    }
    base["messages"] = [
        "Downloaded images into the workspace tmp directory for analysis only.",
        "Pixel metrics are heuristic; final representative image choice still benefits from visual review.",
        "Shopping-mall reuse remains blocked until asset rights are confirmed.",
    ]
    return base


def save_blog_asset_inventory(payload: dict[str, Any]) -> Path:
    LATEST_BLOG_ASSET_INVENTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    LATEST_BLOG_ASSET_INVENTORY_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return LATEST_BLOG_ASSET_INVENTORY_PATH


def save_blog_image_analysis(payload: dict[str, Any]) -> Path:
    LATEST_BLOG_IMAGE_ANALYSIS_PATH.parent.mkdir(parents=True, exist_ok=True)
    LATEST_BLOG_IMAGE_ANALYSIS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return LATEST_BLOG_IMAGE_ANALYSIS_PATH


def save_blog_pixel_analysis(payload: dict[str, Any]) -> Path:
    LATEST_BLOG_PIXEL_ANALYSIS_PATH.parent.mkdir(parents=True, exist_ok=True)
    LATEST_BLOG_PIXEL_ANALYSIS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return LATEST_BLOG_PIXEL_ANALYSIS_PATH


def save_shopping_upload_manifest(payload: dict[str, Any]) -> Path:
    LATEST_BLOG_SHOPPING_MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    LATEST_BLOG_SHOPPING_MANIFEST_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return LATEST_BLOG_SHOPPING_MANIFEST_PATH


def _collect_new_links(snapshot: dict[str, Any], blog_id: str, seen: set, post_links: list, target_pages: int) -> None:
    """스냅샷의 새 포스트 링크를 post_links 에 추가(중복 제외, target_pages 도달 시 중단)."""
    for row in extract_post_links(snapshot, blog_id=blog_id):
        if row["url"] in seen:
            continue
        seen.add(row["url"])
        post_links.append(row)
        if len(post_links) >= target_pages:
            break


def collect_blog_asset_inventory(
    *,
    blog_id: str,
    target_pages: int = 1000,
    port: int = 9232,
    wait_seconds: float = 2.5,
    max_index_pages: int = 50,
    scroll_steps: int = 10,
) -> dict[str, Any]:
    target_id = cdp.create_target(blog_prologue_url(blog_id), port=port)
    if not target_id:
        return {"ok": False, "code": "target_create_failed", "blog_id": blog_id}
    time.sleep(wait_seconds)
    post_links: list[Any] = []
    seen: set[Any] = set()
    snapshot = _read_blog_index_snapshot(target_id, port=port)
    _collect_new_links(snapshot, blog_id, seen, post_links, target_pages)

    for index in range(1, max_index_pages + 1):
        if len(post_links) >= target_pages:
            break
        cdp.navigate(target_id, blog_post_list_url(blog_id, index), port=port)
        time.sleep(wait_seconds)
        snapshot = _read_blog_index_snapshot(target_id, port=port)
        _collect_new_links(snapshot, blog_id, seen, post_links, target_pages)

    posts = []
    for row in post_links[:target_pages]:
        cdp.navigate(target_id, mobile_post_url(row["url"], blog_id=blog_id), port=port)
        time.sleep(wait_seconds)
        _scroll_blog_post(target_id, port=port, steps=scroll_steps)
        snapshot = _read_blog_post_snapshot(target_id, port=port)
        posts.append(build_post_asset_record(snapshot, source_url=row["url"], title=row.get("title", "")))

    image_count = sum(post.get("image_count", 0) for post in posts)
    ok = len(posts) > 0
    payload = {
        "ok": ok,
        "code": "ok" if ok else "no_posts_collected",
        "action": "naver_blog_asset_inventory",
        "blog_id": blog_id,
        "source_url": blog_prologue_url(blog_id),
        "target_pages": target_pages,
        "collected_pages": len(posts),
        "image_count": image_count,
        "posts": posts,
        "rights_status": "unverified",
        "shopping_reuse_allowed": False,
        "required_confirm_text": RIGHTS_CONFIRM_TEXT,
        "messages": [
            "Inventory only. Images are not authorized for shopping-mall reuse until rights are confirmed.",
        ],
    }
    if not ok:
        payload["messages"].append(
            "No post links were collected from the blog index; retry with higher wait/max-index-pages or inspect the blog layout."
        )
    save_blog_asset_inventory(payload)
    return payload


def _read_blog_index_snapshot(target_id: str, *, port: int) -> dict[str, Any]:
    payload = cdp.evaluate(
        target_id,
        r"""JSON.stringify((() => {
          const clean = (value) => String(value || '').replace(/\s+/g, ' ').trim();
          return {
            href: location.href,
            title: document.title || '',
            links: Array.from(document.querySelectorAll('a')).map((a) => ({
              text: clean(a.innerText || a.textContent || a.getAttribute('title')),
              href: a.href || ''
            })).filter((row) => row.href).slice(0, 500)
          };
        })())""",
        timeout=8.0,
        port=port,
    )
    return payload if isinstance(payload, dict) else {"links": []}


def _read_blog_post_snapshot(target_id: str, *, port: int) -> dict[str, Any]:
    payload = cdp.evaluate(
        target_id,
        r"""JSON.stringify((() => {
          const clean = (value) => String(value || '').replace(/\s+/g, ' ').trim();
          const root = document.querySelector('.se-main-container')
            || document.querySelector('#postViewArea')
            || document.querySelector('.post_ct')
            || document.querySelector('.se_component_wrap')
            || document.body;
          const body = clean(root ? root.innerText : '');
          return {
            href: location.href,
            title: document.title || '',
            body_sample: body.slice(0, 3000),
            images: Array.from(root ? root.querySelectorAll('img') : document.images).map((img) => ({
              src: img.currentSrc || img.src || '',
              alt: img.alt || '',
              natural_width: img.naturalWidth || 0,
              natural_height: img.naturalHeight || 0,
              width: img.width || 0,
              height: img.height || 0
            })).filter((img) => img.src).slice(0, 200)
          };
        })())""",
        timeout=10.0,
        port=port,
    )
    return payload if isinstance(payload, dict) else {"images": []}


def _scroll_blog_post(target_id: str, *, port: int, steps: int) -> None:
    for _ in range(max(0, steps)):
        cdp.evaluate(
            target_id,
            "window.scrollBy(0, Math.max(700, Math.floor(window.innerHeight * 0.85))); true",
            timeout=3.0,
            port=port,
        )
        time.sleep(0.25)


