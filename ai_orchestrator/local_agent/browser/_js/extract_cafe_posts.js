(() => {
    const res = [];
    const seen = new Set();

    for (const tr of document.querySelectorAll('tr')) {
        const tds = tr.querySelectorAll('td');
        if (tds.length < 2) continue;

        // td 5개 구조: [공지타입, 제목, 작성자, 날짜, 조회수]
        // td 4개 구조: [제목, 작성자, 날짜, 조회수]
        let titleTdIdx = tds.length >= 5 ? 1 : 0;
        const titleTd = tds[titleTdIdx];

        // 첫 번째 게시글 링크 찾기 (댓글수 링크 제외)
        let link = null;
        for (const a of titleTd.querySelectorAll('a')) {
            const href = a.href || '';
            const txt = (a.innerText || '').trim();
            if ((href.includes('ArticleRead') || href.includes('/articles/')) &&
                !txt.includes('댓글수') && txt.length > 2) {
                link = a;
                break;
            }
        }
        if (!link) continue;

        const href = link.href;
        // 중복 제거 (articleid 기준)
        const artM = href.match(/articles\/(\d+)|articleid=(\d+)/);
        const artKey = artM ? (artM[1] || artM[2]) : href;
        if (seen.has(artKey)) continue;
        seen.add(artKey);

        // 제목 정리: 댓글수 [ N ] 제거
        let title = (link.innerText || '').trim().split('\n')[0].trim();
        title = title.replace(/\s*\[\s*\d+\s*\]\s*$/, '').replace(/\s+/g, ' ').trim();

        // 댓글수: [ N ] 패턴
        const titleFull = (titleTd.innerText || '').trim();
        const cmtM = titleFull.match(/\[\s*(\d+)\s*\]/);
        const comments = cmtM ? cmtM[1] : '';

        // 작성자
        const authorTd = tds[titleTdIdx + 1];
        const nickEl = authorTd ? authorTd.querySelector('.nick, .nickname') : null;
        const author = nickEl
            ? nickEl.innerText.trim()
            : (authorTd ? (authorTd.innerText || '').split('\n')[0].trim() : '');

        // 날짜
        const dateTd = tds[titleTdIdx + 2];
        const date = dateTd ? (dateTd.innerText || '').trim() : '';

        // 조회수
        const viewsTd = tds[titleTdIdx + 3];
        const views = viewsTd ? (viewsTd.innerText || '').trim() : '';

        if (title) {
            res.push({ title: title.substring(0, 100), href, author, date, views, comments });
        }
    }

    // fallback: tr 구조 없는 경우 a 태그 직접 수집
    if (res.length === 0) {
        for (const a of document.querySelectorAll('a')) {
            const txt = (a.innerText || a.textContent || '').trim().split('\n')[0].trim();
            const href = a.href || '';
            if (!txt || txt.length < 4 || txt.includes('댓글수')) continue;
            if (href.includes('ArticleRead') || href.includes('/articles/')) {
                const artM = href.match(/articles\/(\d+)|articleid=(\d+)/);
                const artKey = artM ? (artM[1] || artM[2]) : href;
                if (seen.has(artKey)) continue;
                seen.add(artKey);
                let title = txt.replace(/\s*\[\s*\d+\s*\]\s*$/, '').trim();
                res.push({ title: title.substring(0, 100), href, author: '', date: '', views: '', comments: '' });
            }
        }
    }

    return res;
})()
