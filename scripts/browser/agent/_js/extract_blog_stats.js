(() => {
  const stats = {
    visitor_today: 0,
    visitor_week: 0,
    visitor_month: 0,
    visitor_total: 0,
    post_count: 0,
    comment_count: 0,
    neighbor_count: 0,
    top_posts: [],
  };

  // 방문자 수 추출
  const statSels = [
    '.stat_area', '.blog_info_stat', '[class*="stat"]',
  ];
  for (const sel of statSels) {
    const el = document.querySelector(sel);
    if (!el) continue;
    const text = el.innerText;
    const m1 = text.match(/오늘\s*([\d,]+)/);
    const m2 = text.match(/주간\s*([\d,]+)/);
    const m3 = text.match(/월간\s*([\d,]+)/);
    const m4 = text.match(/전체\s*([\d,]+)/);
    if (m1) stats.visitor_today = parseInt(m1[1].replace(/,/g,''));
    if (m2) stats.visitor_week = parseInt(m2[1].replace(/,/g,''));
    if (m3) stats.visitor_month = parseInt(m3[1].replace(/,/g,''));
    if (m4) stats.visitor_total = parseInt(m4[1].replace(/,/g,''));
  }

  // 포스트 수
  const postSels = [
    '.post_count', '[class*="post_count"]',
  ];
  for (const sel of postSels) {
    const el = document.querySelector(sel);
    if (el) {
      const m = el.innerText.match(/(\d+)/);
      if (m) stats.post_count = parseInt(m[1]);
    }
  }

  // 이웃 수
  const neighborSels = [
    '.neighbor_count', '[class*="neighbor_count"]', '.buddy_count',
  ];
  for (const sel of neighborSels) {
    const el = document.querySelector(sel);
    if (el) {
      const m = el.innerText.match(/(\d+)/);
      if (m) stats.neighbor_count = parseInt(m[1]);
    }
  }

  // 인기 포스트 목록 (있으면)
  const topSels = [
    '.best_list li', '.popular_list li', '[class*="top_post"] li',
  ];
  for (const sel of topSels) {
    const els = document.querySelectorAll(sel);
    if (els.length) {
      for (const li of els) {
        const a = li.querySelector('a');
        if (!a) continue;
        const title = a.innerText.trim().split('\n')[0];
        const m = a.href.match(/\/(\d{10,})/);
        const logNo = m ? m[1] : '';
        const viewsEl = li.querySelector('.views, [class*="views"]');
        const views = viewsEl ? parseInt(viewsEl.innerText.replace(/\D/g,'')) || 0 : 0;
        if (title && logNo) stats.top_posts.push({ title, log_no: logNo, views });
      }
      break;
    }
  }

  return stats;
})()
