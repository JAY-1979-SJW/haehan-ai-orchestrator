(() => {
  const res = [];
  const sels = [
    '.u_cbox_list li', '.comment_box', '.reply_list li',
    '.comment_list li', '[class*="comment"] li',
  ];
  for (const sel of sels) {
    const els = document.querySelectorAll(sel);
    if (!els.length) continue;
    for (const el of els) {
      const author = (el.querySelector('.nick,.u_cbox_nick,[class*="nick"]')||{}).innerText||'';
      const body   = (el.querySelector('.text,.u_cbox_text,[class*="text"]')||{}).innerText||'';
      const date   = (el.querySelector('.date,.u_cbox_date,[class*="date"]')||{}).innerText||'';
      if (author||body) res.push({author:author.trim(),body:body.trim(),written_at:date.trim()});
    }
    if (res.length) break;
  }
  return res;
})()
