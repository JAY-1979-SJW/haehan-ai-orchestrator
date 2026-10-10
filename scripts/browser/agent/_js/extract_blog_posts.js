(() => {
  const res = [];
  const seen = new Set();
  const sels = [
    '.post-item', '.item_inner', '[class*="post_item"]',
    '.blog_post_list li', 'ul.list_post li', '.post_wrap',
  ];
  for (const sel of sels) {
    const els = document.querySelectorAll(sel);
    if (!els.length) continue;
    for (const el of els) {
      const a = el.querySelector('a[href*="/"]');
      if (!a) continue;
      const href = a.href;
      const m = href.match(/\/(\d{10,})/) || href.match(/logNo=(\d+)/);
      const logNo = m ? m[1] : '';
      if (!logNo || seen.has(logNo)) continue;
      seen.add(logNo);
      const titleEl = el.querySelector('.title,.post_title,[class*="title"]');
      const title = (titleEl || a).innerText.trim().split('\n')[0].trim();
      const dateEl = el.querySelector('.date,.post_date,[class*="date"]');
      const date = dateEl ? dateEl.innerText.trim() : '';
      const summaryEl = el.querySelector('.desc,.summary,[class*="desc"]');
      const summary = summaryEl ? summaryEl.innerText.trim().substring(0,200) : '';
      const imgEl = el.querySelector('img');
      const thumb_url = imgEl ? (imgEl.src || imgEl.dataset.src || '') : '';
      const cmtEl = el.querySelector('[class*="comment"],[class*="cmt"]');
      const comment_count = cmtEl ? parseInt(cmtEl.innerText.replace(/\D/g,'')) || 0 : 0;
      if (title && title.length > 1)
        res.push({ log_no:logNo, title, date, summary, thumb_url, href, comment_count });
    }
    if (res.length) break;
  }
  // fallback: a 태그 직접
  if (!res.length) {
    for (const a of document.querySelectorAll('a[href]')) {
      const href = a.href || '';
      const m = href.match(/blog\.naver\.com\/\w+\/(\d{10,})/);
      if (!m || seen.has(m[1])) continue;
      seen.add(m[1]);
      const title = a.innerText.trim().split('\n')[0].trim();
      if (title && title.length > 2)
        res.push({ log_no:m[1], title, date:'', summary:'', thumb_url:'', href, comment_count:0 });
    }
  }
  return res;
})()
