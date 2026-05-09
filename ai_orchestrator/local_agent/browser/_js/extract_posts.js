(() => {
    const res = [];
    for (const a of document.querySelectorAll('a')) {
        const txt = (a.innerText || a.textContent || '').trim().split('\n')[0].trim();
        const href = a.href || '';
        if (!txt || txt.length < 4) continue;
        if (href.includes('ArticleRead') || href.includes('/articles/')) {
            res.push({title: txt.substring(0, 80), href});
        }
    }
    const seen = new Set();
    return res.filter(r => { if (seen.has(r.href)) return false; seen.add(r.href); return true; });
})()
