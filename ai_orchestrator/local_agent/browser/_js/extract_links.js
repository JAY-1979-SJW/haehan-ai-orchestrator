(() => {
    const seen = new Set();
    const res = [];
    for (const a of document.querySelectorAll('a')) {
        const text = (a.innerText || '').trim().split('\n')[0].trim();
        const href = a.href || '';
        if (!href || href.startsWith('javascript') || seen.has(href)) continue;
        if (!text || text.length < 2) continue;
        seen.add(href);
        res.push({text: text.substring(0, 60), href});
    }
    return res;
})()
