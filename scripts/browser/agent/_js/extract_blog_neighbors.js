(() => {
  const res = [];
  const seen = new Set();

  // 이웃 수 추출
  const totalEl = document.querySelector('a[href*="widgetSeq"]');
  const totalTxt = totalEl ? totalEl.closest('div, p, span')?.innerText || '' : document.body.innerText;
  const totalM = totalTxt.match(/(\d+)\s*명/);
  const total = totalM ? parseInt(totalM[1]) : 0;

  // 이웃 링크: blog.naver.com/{blogId} 형태 (widgetSeq 링크 제외, 닉네임 있는 것)
  const anchors = [...document.querySelectorAll('a')].filter(a => {
    const href = a.href || '';
    return href.includes('blog.naver.com') && !href.includes('widgetSeq') && !href.includes('WidgetView') && !href.includes('connect/');
  });

  for (const a of anchors) {
    const href = a.href;
    const m = href.match(/blog\.naver\.com\/(\w+)\/?$/);
    if (!m) continue;
    const blogId = m[1];
    if (seen.has(blogId)) continue;

    const nickname = (a.innerText || '').trim();
    if (!nickname || nickname.length < 1) continue;

    seen.add(blogId);

    // 블로그 소개: 부모의 다음 형제 텍스트
    const container = a.closest('li') || a.closest('div') || a.parentElement;
    const allLines = container ? (container.innerText || '').trim().split('\n').map(l => l.trim()).filter(Boolean) : [];
    const siblingText = allLines.find(l => l !== nickname && l.length > 2 && !l.startsWith('http')) || '';

    res.push({
      blog_id: blogId,
      nickname,
      blog_url: `https://blog.naver.com/${blogId}`,
      description: siblingText.slice(0, 100),
      is_mutual: false,
    });
  }

  return { total, neighbors: res };
})()
