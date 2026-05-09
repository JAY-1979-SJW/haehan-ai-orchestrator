(() => {
    const res = [];
    const seen = new Set();
    for (const a of document.querySelectorAll('a')) {
        const href = a.href || '';
        const txt = (a.innerText || '').trim().split('\n')[0].trim();
        if (!txt || !href) continue;
        const isBoard = href.includes('ArticleList') || href.includes('/menus/') ||
                        href.includes('search.boardtype');
        if (!isBoard || seen.has(href)) continue;
        // 게시글 수 추출
        const parent = a.parentElement;
        let count = '';
        if (parent) {
            const cnt = parent.querySelector('.count, .num, em');
            if (cnt) count = (cnt.innerText || '').trim();
            // 텍스트에서 숫자 추출
            const m = (parent.innerText || '').match(/[\d,]{3,}/);
            if (m && !count) count = m[0];
        }
        seen.add(href);
        res.push({ name: txt.substring(0, 60), href, count });
    }
    return res;
})()
