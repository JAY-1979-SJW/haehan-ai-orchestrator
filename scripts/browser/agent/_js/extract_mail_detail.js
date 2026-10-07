// 네이버 mail 상세 추출 — auto_structure_builder 자동 생성
(function () {
  const result = {
    subject: '', from: '', to: '', date: '', body: '', attachments: []
  };

  try {
    // from
    for (const sel of [".button_sender"]) {
      const el = document.querySelector(sel);
      if (el?.innerText?.trim()) { result.from = el.innerText.trim(); break; }
    }

    // to
    for (const sel of ["[class*=\"to\"]"]) {
      const el = document.querySelector(sel);
      if (el?.innerText?.trim()) { result.to = el.innerText.trim(); break; }
    }

    // subject
    for (const sel of ["h1", ".mail_title", "[class*=\"title\"]"]) {
      const el = document.querySelector(sel);
      if (el?.innerText?.trim()) { result.subject = el.innerText.trim(); break; }
    }

    // date
    for (const sel of ["[class*=\"date\"]", "[class*=\"time\"]"]) {
      const el = document.querySelector(sel);
      if (el?.innerText?.trim()) { result.date = el.innerText.trim(); break; }
    }

    // body
    for (const sel of ["[class*=\"content\"]"]) {
      const el = document.querySelector(sel);
      if (el?.innerText?.trim()) { result.body = el.innerText.trim(); break; }
    }

    // name
    for (const sel of [".name", "[class*=\"name\"]", "[class*=\"title\"]"]) {
      const el = document.querySelector(sel);
      if (el?.innerText?.trim()) { result.name = el.innerText.trim(); break; }
    }

    // end
    for (const sel of ["[class*=\"end\"]"]) {
      const el = document.querySelector(sel);
      if (el?.innerText?.trim()) { result.end = el.innerText.trim(); break; }
    }

    // 첨부파일
    document.querySelectorAll('.attachment, [class*="attach"], a[download]').forEach(att => {
      const name = att.innerText?.trim() || att.getAttribute('download') || '';
      if (name) result.attachments.push({ name, size: att.dataset.size || '' });
    });
  } catch(e) {}

  return result;
})();
