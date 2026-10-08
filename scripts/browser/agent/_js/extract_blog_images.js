(() => {
  const res = [];
  const seen = new Set();
  const sels = [
    '.se-image-resource', '.se-module-image img',
    '#postViewArea img', '.post_ct img',
    '.se-component img', 'figure img',
  ];
  for (const sel of sels) {
    for (const img of document.querySelectorAll(sel)) {
      const src = img.dataset.src || img.src || '';
      if (!src || src.includes('data:') || seen.has(src)) continue;
      const orig = src.replace(/\?.*/, '');
      seen.add(src);
      res.push({
        src: orig,
        alt: img.alt || '',
        width: img.naturalWidth || img.width || 0,
        height: img.naturalHeight || img.height || 0,
      });
    }
  }
  if (!res.length) {
    const og = document.querySelector('meta[property="og:image"]');
    if (og && og.content) res.push({src: og.content, alt:'', width:0, height:0});
  }
  return res;
})()
