"""제품 이미지 원본화질 정리 — 서버 배포용.

- C:/work/전등 이미지/gonobi_images_v2 의 원본 이미지를 코드별 폴더로 재구성
- 압축은 웹 전송에 무리 없는 선에서만 (긴 변 1600px, quality 88) — base64 임베드 제약 없음
- data/mk_catalog/site/images/{code}/01.jpg ... 로 저장
- data/mk_catalog/site/products.json 에 상대경로 이미지 목록 포함한 최종 카탈로그 저장
"""

import json
import re
from pathlib import Path
from typing import Any

from PIL import Image

from scripts.common.app_paths import onedrive_root, resolve_external

ROOT = str(resolve_external("HAEHAN_LIGHTING_IMAGE_DIR", "전등 이미지", "gonobi_images_v2", base=onedrive_root()))
EXCLUDE_CATS = {"시공사례"}
FNAME_RE = re.compile(r"^(\d+)_(\d+)_(.+)\.(png|jpg|jpeg|gif|webp)$", re.I)

OUT_DIR = "data/mk_catalog/site"
IMG_DIR = Path(OUT_DIR) / "images"
MAX_SIDE = 1600
QUALITY = 88

IMG_DIR.mkdir(parents=True, exist_ok=True)

# 1) log_no -> 정렬된 원본 이미지 경로 목록
posts_files: dict[Any, Any] = {}
for catdir in Path(ROOT).iterdir():
    if catdir.name in EXCLUDE_CATS:
        continue
    if not catdir.is_dir():
        continue
    for f in catdir.iterdir():
        m = FNAME_RE.match(f.name)
        if not m:
            continue
        log_no, seq, name, ext = m.groups()
        posts_files.setdefault(log_no, []).append((seq, f))

for k in posts_files:
    posts_files[k].sort(key=lambda x: x[0])

catalog = json.load(Path("data/mk_catalog/products_web.json").open(encoding="utf-8"))


def save_full(src_path, dst_path):
    try:
        with Image.open(src_path) as im:
            im = im.convert("RGB")
            w, h = im.size
            longest = max(w, h)
            if longest > MAX_SIDE:
                scale = MAX_SIDE / longest
                im = im.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
            im.save(dst_path, format="JPEG", quality=QUALITY)
        return True
    except Exception as e:  # noqa: BLE001 - 카탈로그 이미지 리사이즈/저장 - 개별 이미지 처리 실패 시 False 반환하고 해당 이미지만 skip, 다른 이미지 처리에 영향 없음
        print("fail", src_path, e)
        return False


n_products_with_images = 0
n_images_total = 0
for c in catalog:
    log_no = c.get("blogLogNo")
    c.pop("img", None)
    c.pop("gallery", None)
    c.pop("imgBig", None)
    if not log_no:
        c["images"] = []
        continue
    files = posts_files.get(log_no)
    if not files:
        c["images"] = []
        continue
    code_dir = IMG_DIR / c["code"]
    code_dir.mkdir(parents=True, exist_ok=True)
    rel_paths = []
    for i, (seq, path) in enumerate(files, start=1):
        dst = code_dir / f"{i:02d}.jpg"
        if save_full(path, dst):
            rel_paths.append(f"images/{c['code']}/{i:02d}.jpg")
            n_images_total += 1
    c["images"] = rel_paths
    if rel_paths:
        n_products_with_images += 1

print("products with images:", n_products_with_images, "/", len(catalog))
print("total image files written:", n_images_total)

json.dump(catalog, (Path(OUT_DIR) / "products.json").open("w", encoding="utf-8"), ensure_ascii=False)
print("saved:", Path(OUT_DIR) / "products.json")
