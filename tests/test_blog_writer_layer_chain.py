"""C4: blog_mixin_write(L4) -> writer 체인이 레지스트리 허용방향(L4->L4) 안에 머문다."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHAIN = [
    "ai_orchestrator/local_agent/browser/mixins/blog_mixin_write.py",
    "scripts/naver/blog/core/writer.py",
    "scripts/naver/blog/tag_suggester.py",
    "scripts/naver/blog/seo/tag_suggester.py",
    "scripts/naver/auth.py",
]


def test_blog_writer_chain_declared_l4_or_below():
    reg = json.loads((ROOT / "configs" / "module_registry.json").read_text(encoding="utf-8"))
    allowed = reg["allowed_deps"]
    for f in CHAIN:
        assert reg["files"][f]["layer"] == "L4", f
    assert "L4" in allowed["L4"]


def test_writer_importable_from_mixin():
    from ai_orchestrator.local_agent.browser.mixins.blog_mixin_write import BlogWriteMixin
    from scripts.naver.blog.core.writer import BlogWriter, write_post

    assert BlogWriteMixin and BlogWriter and write_post
