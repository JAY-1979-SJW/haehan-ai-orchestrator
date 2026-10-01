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
    kind: str  # folder_policy.KIND_* 중 하나
    cls: str
    title: str
    unread_text: str
    unread_count: int  # -1 if unknown
    folder_id: str = ""  # 클릭 학습 후
    folder_url: str = ""
    href_attr: str = ""
    # 신규 (DYNAMIC_FOLDER_DISCOVERY_01):
    folder_key: str = ""        # name + folder_id 조합 식별자
    total_count: int = -1       # 전체 메일 수 (가능 시)
    parent_group: str = ""      # 'lnb_top' / 'smart_group' / 'user_group'
    depth: int = 0
    selector_evidence: dict = field(default_factory=dict)
    is_system_folder: bool = False
    is_smart_folder: bool = False
    is_user_folder: bool = False
    is_spam: bool = False
    is_trash: bool = False
    is_collectable: bool = False
    default_policy_state: str = ""   # folder_policy.evaluate 결과
    adapter_selected: str = ""
    adapter_reason: str = ""
    # CLOSEOUT_01 추가:
    is_nav_action: bool = False
    is_smart_group_header: bool = False
    raw_kind: str = ""
    is_support_menu: bool = False
    folder_evidence_count: int = 0
    unread_count_evidence: str = ""
    unread_count_unknown: bool = False
    requires_click_probe: bool = False
    count_included_in_sum: bool = True
    duplicate_count_group: str = ""


# LNB 폴더 raw 목록 추출 (selector evidence 포함)
LNB_FOLDERS_EXPR = r"""
JSON.stringify((function(){
  var items = Array.from(document.querySelectorAll('.lnb .mailbox_item'));
  var out = [];
  function depthOf(el) {
    var d = 0;
    var p = el.parentElement;
    while (p) {
      if (p.classList && p.classList.contains('depth_list')) d++;
      if (p.classList && p.classList.contains('mailbox_group')) break;
      p = p.parentElement;
    }
    return d;
  }
  function detectKind(cls) {
    if (/svg_inbox/.test(cls)) return 'inbox';
    if (/svg_sent_mail/.test(cls)) return 'sent';
    if (/svg_temporary/.test(cls)) return 'draft';
    if (/svg_spam/.test(cls)) return 'spam';
    if (/svg_trash/.test(cls)) return 'trash';
    if (/svg_receipt/.test(cls)) return 'receipt';
    if (/svg_write_to_me/.test(cls)) return 'self_mail';
    if (/svg_all\b/.test(cls)) return 'all';
    if (/svg_vipmail/.test(cls)) return 'vip';
    if (/svg_archive/.test(cls)) return 'archive';
    if (/svg_depth/.test(cls)) return 'smart';
    if (/svg_folder/.test(cls)) return 'user';
    if (/svg_smartmail/.test(cls)) return 'smart_group_header';
    if (/svg_my/.test(cls)) return 'other';
    return 'unknown';
  }
  function parentGroup(el) {
    var p = el.closest('.mailbox_group, .smartmail_group, .lnb_top');
    if (!p) return 'lnb_top';
    if (p.classList.contains('smartmail_group')) return 'smart_group';
    return p.className.split(/\s+/)[0] || 'lnb_top';
  }
  for (var i = 0; i < items.length; i++) {
    var it = items[i];
    var label = it.querySelector('.mailbox_label');
    if (!label) continue;
    var nameText = (label.innerText||'').trim().replace(/\s+/g,' ').slice(0,80);
    var nameClean = nameText.replace(/\s*선택됨\s*$/,'').trim();
    if (!nameClean) continue;
    var title = label.getAttribute('title')||'';
    var href = label.getAttribute('href')||'';
    var cls = (label.className||'').toString();
    var unread_el = it.querySelector('.unread_mail');
    var unread_text = unread_el ? (unread_el.innerText||'').trim().replace(/\s+/g,' ').slice(0,60) : '';
    var unread_count = -1;
    var m = unread_text.match(/(\d+)/);
    if (m) unread_count = parseInt(m[1], 10);
    var unread_count_evidence;
    if (unread_el && unread_count >= 0) unread_count_evidence = 'explicit_badge';
    else if (unread_el) unread_count_evidence = 'badge_but_no_number';
    else unread_count_evidence = 'no_badge_assumed_zero';

    // LNB 메뉴/푸터 분리 — li.mailbox_item.support
    var itCls = (it.className||'').toString();
    var isSupport = /\bsupport\b/.test(itCls);
    var raw_kind = detectKind(cls);
    var kind = raw_kind;
    if (isSupport) kind = 'nav_action';

    // 폴더 evidence 다중 평가
    var ev = {
      svg_kind_class: raw_kind !== 'unknown',
      has_unread_badge: !!unread_el,
      has_href: !!href,
      in_mailbox_item: /\bmailbox_item\b/.test(itCls),
      not_support_menu: !isSupport,
    };
    var ev_count = 0;
    for (var k in ev) if (ev[k]) ev_count++;

    out.push({
      name: nameClean,
      kind: kind,
      raw_kind: raw_kind,
      cls: cls.slice(0,120),
      title, href_attr: href || '',
      unread_text, unread_count,
      unread_count_evidence: unread_count_evidence,
      parent_group: parentGroup(it),
      depth: depthOf(it),
      is_support_menu: isSupport,
      folder_evidence_count: ev_count,
      selector_evidence: {
        item_cls: itCls.slice(0,80),
        label_cls: cls.slice(0,80),
        has_unread_el: !!unread_el,
        has_href: !!href,
        is_support: isSupport,
        evidence_flags: ev,
      },
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


def _classify_flags(f: FolderInfo) -> None:
    """kind → 분류 boolean flag 동기화 (in-place)."""
    from . import folder_policy as fp
    f.is_smart_folder = (f.kind == fp.KIND_SMART)
    f.is_user_folder = (f.kind == fp.KIND_USER)
    f.is_spam = (f.kind == fp.KIND_SPAM)
    f.is_trash = (f.kind == fp.KIND_TRASH)
    f.is_nav_action = (f.kind == fp.KIND_NAV_ACTION)
    f.is_smart_group_header = (f.kind == fp.KIND_SMART_GROUP_HEADER)
    f.is_system_folder = f.kind in (
        fp.KIND_INBOX, fp.KIND_SENT, fp.KIND_DRAFT, fp.KIND_SPAM,
        fp.KIND_TRASH, fp.KIND_ARCHIVE, fp.KIND_ALL,
        fp.KIND_RECEIPT, fp.KIND_WRITE_TO_ME, fp.KIND_VIP,
    )
    # 검산 합산 제외 대상
    if f.kind in fp.NON_FOLDER_KIND:
        f.count_included_in_sum = False
        if f.is_smart_group_header:
            f.duplicate_count_group = "smart_group_header"
    # unread DOM 미존재 — 0 으로 보정
    if f.unread_count_evidence == "no_badge_assumed_zero" and f.unread_count == -1:
        f.unread_count = 0
        f.unread_count_unknown = False
    elif f.unread_count_evidence == "badge_but_no_number":
        f.unread_count_unknown = True
        f.requires_click_probe = True


def _folder_from_raw(nm: str, r: dict) -> FolderInfo:
    """LNB 원시 dict 한 건 -> FolderInfo."""
    f = FolderInfo(
        name=nm,
        kind=r.get("kind", "unknown"),
        cls=r.get("cls", ""),
        title=r.get("title", ""),
        unread_text=r.get("unread_text", ""),
        unread_count=int(r.get("unread_count", -1)),
        href_attr=r.get("href_attr", ""),
        parent_group=r.get("parent_group", ""),
        depth=int(r.get("depth", 0)),
        selector_evidence=r.get("selector_evidence") or {},
        raw_kind=r.get("raw_kind", ""),
        is_support_menu=bool(r.get("is_support_menu", False)),
        folder_evidence_count=int(r.get("folder_evidence_count", 0)),
        unread_count_evidence=r.get("unread_count_evidence", ""),
    )
    return f


def _learn_folder_ids(
    actions: _ActionsP, folders: list[FolderInfo], click_delay_s: float, learn_kinds: tuple[str, ...]
) -> None:
    """folder_id 학습 (받은편지함 id=0 설정 + unread>0 폴더 클릭 학습 + 받은편지함 복귀)."""
    # 받은편지함 id=0 은 잘 알려진 라우트 — 클릭 없이 설정
    for f in folders:
        if f.kind == "inbox":
            f.folder_id = "0"
            f.folder_url = "https://mail.naver.com/v2/folders/0"
            f.folder_key = f"{f.name}::{f.kind}::0"
            break
    # unread>0 + learn_kinds 인 폴더만 클릭 학습 (스팸/휴지통은 기본 학습 안 함)
    for f in folders:
        if f.folder_id:
            continue
        if f.unread_count > 0 and f.kind in learn_kinds:
            clicked = actions.evaluate(_click_folder_expr(f.name))
            if clicked:
                time.sleep(min(click_delay_s, 0.2))
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
                    f.folder_key = f"{f.name}::{f.kind}::{fid}"
    # 받은편지함으로 복귀
    actions.navigate("https://mail.naver.com/v2/folders/0/all")
    time.sleep(0.2)


def discover_folders(actions: _ActionsP,
                     *, learn_ids: bool = True,
                     click_delay_s: float = 2.0,
                     learn_kinds: tuple[str, ...] = ("smart", "user")
                     ) -> list[FolderInfo]:
    """LNB 폴더 목록 발견 + folder_id 학습 (unread>0 + learn_kinds 대상).

    하드코딩 없음. learn_kinds 로 학습 대상 kind 만 클릭 학습.
    """
    raw = actions.evaluate(LNB_FOLDERS_EXPR) or []
    folders: list[FolderInfo] = []
    seen_names: set[str] = set()
    for r in raw:
        nm = (r.get("name") or "").strip()
        if not nm or nm in seen_names:
            continue
        seen_names.add(nm)
        f = _folder_from_raw(nm, r)
        _classify_flags(f)
        f.folder_key = f"{f.name}::{f.kind}"
        folders.append(f)

    if learn_ids:
        _learn_folder_ids(actions, folders, click_delay_s, learn_kinds)

    # adapter 자동 선택
    from . import folder_policy as fp
    for f in folders:
        has_link = bool(f.href_attr and f.href_attr not in ("#", ""))
        adapter, reason = fp.select_adapter(
            kind=f.kind, folder_id=f.folder_id,
            href_attr=f.href_attr, has_direct_link=has_link,
        )
        f.adapter_selected = adapter
        f.adapter_reason = reason

    return folders


def filter_collectable(folders: list[FolderInfo],
                       policy: "object | None" = None) -> list[FolderInfo]:
    """policy(FolderPolicy) 기반 수집 대상 필터. policy=None 이면 기본 정책 적용.

    각 folder.default_policy_state 와 is_collectable 도 in-place 기록.
    """
    from . import folder_policy as fp
    if policy is None:
        policy = fp.FolderPolicy()
    out = []
    for f in folders:
        # adapter 미설정 또는 unsupported 인데 folder_id 가 있으면 재평가
        if (f.adapter_selected in ("", fp.ADAPTER_UNSUPPORTED)) and f.folder_id:
            adapter, reason = fp.select_adapter(
                kind=f.kind, folder_id=f.folder_id,
                href_attr=f.href_attr,
                has_direct_link=bool(f.href_attr and f.href_attr != "#"),
            )
            f.adapter_selected = adapter
            f.adapter_reason = reason
        state = fp.evaluate(
            policy,
            name=f.name, kind=f.kind, unread_count=f.unread_count,
            folder_id=f.folder_id, adapter=f.adapter_selected,
        )
        f.default_policy_state = state
        f.is_collectable = state in (fp.INCLUDED, fp.INCLUDED_OVERRIDE)
        if f.is_collectable:
            out.append(f)
    return out


def folders_to_dicts(folders: list[FolderInfo]) -> list[dict]:
    return [asdict(f) for f in folders]
