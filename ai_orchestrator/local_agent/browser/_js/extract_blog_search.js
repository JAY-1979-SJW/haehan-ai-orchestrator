(() => {
  const res = [];
  const seen = new Set();

  // Naver blog search: collect all blog.naver.com links with logNo
  const anchors = document.querySelectorAll('a[href*="blog.naver.com"]');
  for (const a of anchors) {
    const href = a.href || '';
    const m1 = href.match(/blog\.naver\.com\/(\w+)\/(\d{8,})/);
    if (!m1) continue;
    const blogId = m1[1];
    const logNo = m1[2];
    if (seen.has(logNo)) continue;

    // Skip short/numeric-only text (comment count badges etc.)
    const rawText = (a.innerText || a.textContent || '').trim();
    if (!rawText || rawText.length < 3 || /^\d+$/.test(rawText)) continue;
    // Skip very long text (body previews — we want titles)
    if (rawText.length > 150) continue;

    seen.add(logNo);
    const title = rawText.split('\n')[0].trim();

    // Walk up to find summary, date, author siblings
    let summary = '', date = '', author = blogId;
    const container = a.closest('li') || a.closest('div[class]') || a.parentElement;
    if (container) {
      // Summary: longer sibling text
      const allTxt = [...container.querySelectorAll('span, p, div')];
      for (const el of allTxt) {
        const t = el.innerText.trim();
        if (t.length > 30 && t.length < 300 && !t.includes(title.slice(0,10))) {
          summary = t.slice(0, 200);
          break;
        }
      }
      // Date: YYYY.MM.DD or YYYY.M.D pattern
      const cTxt = container.innerText || '';
      const dm = cTxt.match(/(\d{4}\.\d{1,2}\.\d{1,2}\.?)/);
      if (dm) date = dm[1];
    }

    res.push({ title, blog_id: blogId, log_no: logNo, href, summary, date, author });
  }
  return res;
})()
