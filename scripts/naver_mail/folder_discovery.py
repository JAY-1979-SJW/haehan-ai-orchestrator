"""Naver Mail LNB 폴더 발견 + folder_id 매핑.

발견 절차:
  1. LNB 의 .mailbox_label 항목들에서 폴더명/unread 텍스트 추출
  2. 폴더가 smart/inbox/user/system 인지 분류 (svg_depth / svg_inbox / svg_folder 등)
  3. folder_id 는 클릭 후 URL `/v2/folders/{id}` 로부터 학습 — 단,
     클릭 없이 한 번에 알아내기 위해 click → url 학습 → 캐싱 패턴 사용

폴더 식별자(folder_id) URL 매핑은 사용자별로 다르므로 하드코딩 금지.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Protocol


@dataclass
class FolderInfo:
    name: str
    kind: str  # "inbox" / "smart" / "user" / "system" / "other"
    cls: str
    title: str
    unread_text: str
    unread_count: int  # -1 if unknown
    folder_id: str = ""  # 클릭 학습 후
    folder_url: str = ""
    href_attr: str = ""


# LNB 폴더 raw 목록 추출 (selector evidence 포함)
LNB_FOLDERS_EXPR = r"""
JSON.stringify((function(){
  var items = Array.from(document.querySelectorAll('.lnb .mailbox_item'));
  var out = [];
  for (var i = 0; i < items.length; i++) {
    var it = items[i];
    var label = it.querySelector('.mailbox_label');
    if (!label) continue;
    var nameText = (label.innerText||'').trim().replace(/\s+/g,' ').slice(0,40);
    var nameClean = nameText.replace(/\s*선택됨\s*$/,'').trim();
    var title = label.getAttribute('title')||'';
    var href = label.getAttribute('href')||'';
    var cls = (label.className||'').toString();
    var unread_el = it.querySelector('.unread_mail');
    var unread_text = unread_el ? (unread_el.innerText||'').trim().replace(/\s+/g,' ').slice(0,60) : '';
    var unread_count = -1;
    var m = unread_text.match(/(\d+)/);
    if (m) unread_count = parseInt(m[1], 10);
    var kind = 'other';
    if (/svg_inbox/.test(cls)) kind = 'inbox';
    else if (/svg_depth/.test(cls)) kind = 'smart';
    else if (/svg_folder/.test(cls)) kind = 'user';
    else if (/svg_sent_mail|svg_temporary|svg_spam|svg_trash|svg_receipt|svg_write_to_me|svg_all|svg_my|svg_vipmail|svg_smartmail/.test(cls)) kind = 'system';
    out.push({
      name: nameClean, kind, cls: cls.slice(0,120),
      title, href_attr: href || '',
      unread_text, unread_count,
    });
  }
  return out;
})())
"""


class _ActionsP(Protocol):
    def evaluate(self, expr: str) -> Any: ...
    def navigate(self, url: str) -> None: ...
    def wait_dom(self, expr_truthy: str, timeout_s: float = 8.0) -> bool: ...


def _click_folder_expr(name: str) -> str:
    # name 의 따옴표는 그대로 — Naver lnb 텍스트에는 따옴표 거의 없음
    safe = name.replace("'", "\\'")
    return (
        "(function(){"
        "var lbls=Array.from(document.querySelectorAll('.lnb .mailbox_label'));"
        f"for(var i=0;i<lbls.length;i++){{var t=(lbls[i].innerText||'').trim().replace(/\\s+/g,' ').replace(/\\s*선택됨\\s*$/,'').trim();"
        f"if(t==='{safe}'){{lbls[i].click();return true;}}}}return false;}})()"
    )


_FOLDER_URL_RE = re.compile(r"/v2/folders/([^/?#]+)")


def parse_folder_id_from_url(url: str) -> str:
    m = _FOLDER_URL_RE.search(url or "")
    return m.group(1) if m else ""


CURRENT_URL_EXPR = "JSON.stringify({url: location.href, title: document.title})"


def discover_folders(actions: _ActionsP,
                     *, learn_ids: bool = True,
                     click_delay_s: float = 2.0) -> list[FolderInfo]:
    """LNB 폴더 목록 발견. learn_ids=True 면 unread>0 폴더를 순회하며 folder_id 학습.

    부작용: 폴더 클릭으로 메일함 페이지 이동이 발생 (목록만, 본문 X). 마지막에 받은편지함으로 복귀.
    """
    raw = actions.evaluate(LNB_FOLDERS_EXPR) or []
    folders: list[FolderInfo] = []
    seen_names: set[str] = set()
    for r in raw:
        nm = (r.get("name") or "").strip()
        if not nm or nm in seen_names:
            continue
        seen_names.add(nm)
        folders.append(FolderInfo(
            name=nm,
            kind=r.get("kind", "other"),
            cls=r.get("cls", ""),
            title=r.get("title", ""),
            unread_text=r.get("unread_text", ""),
            unread_count=int(r.get("unread_count", -1)),
            href_attr=r.get("href_attr", ""),
        ))

    if learn_ids:
        # 받은편지함은 url_pattern /v2/folders/0/ 으로 잘 알려져 있음 — id="0"
        for f in folders:
            if f.kind == "inbox":
                f.folder_id = "0"
                f.folder_url = "https://mail.naver.com/v2/folders/0"
                break
        # unread>0 smart/user 폴더 학습
        for f in folders:
            if f.folder_id:
                continue
            if f.unread_count > 0 and f.kind in ("smart", "user"):
                clicked = actions.evaluate(_click_folder_expr(f.name))
                if clicked:
                    time.sleep(click_delay_s)
                    actions.wait_dom(
                        "document.querySelector('li.mail_item, .mail_list_wrap')",
                        timeout_s=8.0,
                    )
                    cur = actions.evaluate(CURRENT_URL_EXPR) or {}
                    url = (cur or {}).get("url", "") if isinstance(cur, dict) else ""
                    fid = parse_folder_id_from_url(url)
                    if fid:
                        f.folder_id = fid
                        f.folder_url = f"https://mail.naver.com/v2/folders/{fid}"
        # 학습 종료 — 받은편지함으로 복귀 (다음 단계 위해)
        actions.navigate("https://mail.naver.com/v2/folders/0/all")
        time.sleep(2.0)

    return folders


def filter_collectable(folders: list[FolderInfo]) -> list[FolderInfo]:
    """수집 대상 = inbox + smart 폴더 (user 폴더는 별도 정책으로 미수집)."""
    return [f for f in folders if f.kind in ("inbox", "smart") and f.unread_count > 0
            and f.folder_id]


def folders_to_dicts(folders: list[FolderInfo]) -> list[dict]:
    return [asdict(f) for f in folders]
