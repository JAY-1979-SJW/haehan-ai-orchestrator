// 모바일 블로그 페이지(m.blog.naver.com)에서 포스트 목록 추출
// blog.stat.naver.com/m/blog/article/{logNo}/cv 패턴 활용
(function () {
  const items = [];
  const seen = new Set();
  const blogId = window.location.pathname.split('/')[1] || '';

  for (const a of document.querySelectorAll('a[href*="blog.stat.naver.com"]')) {
    const m = a.href.match(/article\/([0-9]{10,})\/cv/);
    if (!m || seen.has(m[1])) continue;
    seen.add(m[1]);

    const logNo = m[1];
    const container = a.closest('li') || a.closest('article') || a.closest('.item') || a.parentElement;
    let title = '';
    let date = '';
    let thumb_url = '';

    if (container) {
      // 제목: strong, h2, h3, .title, .tit, .subject 순으로 탐색
      for (const sel of ['strong', 'h2', 'h3', '.title', '.tit', '.subject', 'b']) {
        const el = container.querySelector(sel);
        if (el) {
          title = el.innerText.trim();
          if (title.length > 2) break;
        }
      }
      // 제목 폴백: 첫 의미있는 텍스트 줄
      if (!title) {
        const lines = container.innerText.trim().split('\n').map(l => l.trim()).filter(Boolean);
        title = lines.find(l => l.length > 3 && !l.match(/^\d+ 읽음/) && !l.match(/^\d{4}\./)) || '';
      }
      // 날짜
      const dateM = container.innerText.match(/(\d{4}\. \d{1,2}\. \d{1,2}\.)/);
      if (dateM) date = dateM[1];
      // 썸네일
      const img = container.querySelector('img');
      if (img) thumb_url = img.src || '';
    }

    items.push({
      log_no: logNo,
      title: title.substring(0, 100),
      date: date,
      summary: '',
      thumb_url: thumb_url,
      href: 'https://m.blog.naver.com/' + blogId + '/' + logNo,
      comment_count: 0,
    });
  }

  return items;
})();
