(() => {
  const res = [];
  const seen = new Set();
  const sels = [
    '.tag_area a', '.tag_list li a', '.tag_cloud a',
    '[class*="tag"] a', 'a[href*="?tag="]',
  ];
  for (const sel of sels) {
    const els = document.querySelectorAll(sel);
    if (!els.length) continue;
    for (const a of els) {
      const tag = a.innerText.trim();
      const href = a.href || '';
      if (!tag || tag.length < 2 || seen.has(tag)) continue;
      seen.add(tag);
      const countEl = a.parentElement?.querySelector('[class*="count"]');
      const count = countEl ? parseInt(countEl.innerText.replace(/\D/g,'')) || 0 : 0;
      res.push({ tag, count, href });
    }
    if (res.length) break;
  }
  return res;
})()
