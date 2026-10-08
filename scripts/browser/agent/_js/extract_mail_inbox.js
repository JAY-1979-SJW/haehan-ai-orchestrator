// 네이버 mail 목록 추출 — auto_structure_builder 자동 생성
(function () {
  const items = [];
  const itemSelectors = ["li.mail_item", "[class*=\"mail_item\"]", "li[class*=\"mail\"]"];

  let elements = [];
  for (const sel of itemSelectors) {
    const found = document.querySelectorAll(sel);
    if (found.length > 0) { elements = Array.from(found); break; }
  }

  elements.forEach((item) => {
    try {
      // from
      let from = '';
      for (const sel of [".button_sender"]) {
        const el = item.querySelector(sel);
        if (el?.innerText?.trim()) { from = el.innerText.trim(); break; }
      }

      // to
      let to = '';
      for (const sel of ["[class*=\"to\"]"]) {
        const el = item.querySelector(sel);
        if (el?.innerText?.trim()) { to = el.innerText.trim(); break; }
      }

      // subject
      let subject = '';
      for (const sel of ["h1", ".mail_title", "[class*=\"title\"]"]) {
        const el = item.querySelector(sel);
        if (el?.innerText?.trim()) { subject = el.innerText.trim(); break; }
      }

      // date
      let date = '';
      for (const sel of ["[class*=\"date\"]", "[class*=\"time\"]"]) {
        const el = item.querySelector(sel);
        if (el?.innerText?.trim()) { date = el.innerText.trim(); break; }
      }

      // body
      let body = '';
      for (const sel of ["[class*=\"content\"]"]) {
        const el = item.querySelector(sel);
        if (el?.innerText?.trim()) { body = el.innerText.trim(); break; }
      }

      // name
      let name = '';
      for (const sel of [".name", "[class*=\"name\"]", "[class*=\"title\"]"]) {
        const el = item.querySelector(sel);
        if (el?.innerText?.trim()) { name = el.innerText.trim(); break; }
      }

      // end
      let end = '';
      for (const sel of ["[class*=\"end\"]"]) {
        const el = item.querySelector(sel);
        if (el?.innerText?.trim()) { end = el.innerText.trim(); break; }
      }

      // ID 추출
      let id = item.className.match(/(?:mail|event|item)-(\d+)/)?.[1] || '';
      if (!id) {
        const link = item.querySelector('a[href*="/read/"], a[href*="/view/"]');
        id = link?.href?.match(/\/(\d+)/)?.[1] || '';
      }

      if (id || from || subject) {
        items.push({ id, from, subject, date, unread: Boolean(item.classList.contains('unread')) });
      }
    } catch(e) {}
  });

  return items;
})();
