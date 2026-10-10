// 네이버 메일 폴더 목록 추출
(function () {
  const folders = [];

  // 사이드바 폴더 항목 탐지 — 여러 선택자 시도
  const selectors = [
    'li[class*="folder"]',
    'li[class*="Folder"]',
    'ul[class*="folder"] li',
    'ul[class*="list"] li',
    '[class*="sidebar"] li',
    '[class*="gnb"] li',
    'nav li',
  ];

  let elements = [];
  for (const sel of selectors) {
    const found = document.querySelectorAll(sel);
    if (found.length >= 2) { elements = Array.from(found); break; }
  }

  elements.forEach(li => {
    // 폴더 이름 — 첫 번째 텍스트 노드 또는 이름 전용 요소
    let name = '';
    const nameEl = li.querySelector('[class*="name"], [class*="title"], [class*="label"], span:first-child');
    if (nameEl) {
      name = nameEl.innerText.trim().split('\n')[0].trim();
    }
    if (!name) {
      const text = li.innerText.trim();
      name = text.split('\n')[0].trim();
    }
    if (!name || name.length > 30) return;

    // 안읽은 수 — 전용 뱃지/카운트 요소 우선
    let count = 0;
    const countEl = li.querySelector('[class*="count"], [class*="badge"], [class*="unread"], [class*="num"]');
    if (countEl) {
      const n = parseInt(countEl.innerText.trim().replace(/[^\d]/g, ''), 10);
      if (!isNaN(n)) count = n;
    }

    // 전용 요소 없으면 텍스트 전체에서 숫자 패턴 추출
    if (count === 0) {
      const fullText = li.innerText;
      // "안 읽은 메일\n54\n개" 또는 "(54)" 패턴
      const m = fullText.match(/안\s*읽[은은]\s*메일[^0-9]*(\d+)/)
             || fullText.match(/\((\d+)\)/)
             || fullText.match(/(\d+)\s*개/)
             || fullText.match(/새\s*메일[^0-9]*(\d+)/);
      if (m) count = parseInt(m[1], 10);
    }

    folders.push({ name, count });
  });

  // 중복 제거
  const seen = new Set();
  return folders.filter(f => {
    if (seen.has(f.name)) return false;
    seen.add(f.name);
    return true;
  });
})();
