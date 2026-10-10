// 네이버 MyBox 파일 목록 추출 — API 직접 호출
// args: { path: "/" }
(async function (args) {
  const path = (args && args.path) || '/';

  try {
    // MyBox 파일 목록 API 탐지
    const endpoints = [
      `/api/getFileList?path=${encodeURIComponent(path)}&_=${Date.now()}`,
      `/api/explorer/list?path=${encodeURIComponent(path)}&_=${Date.now()}`,
      `/api/v1/explorer/list?folderPath=${encodeURIComponent(path)}&_=${Date.now()}`,
    ];

    for (const url of endpoints) {
      try {
        const res = await fetch(url, { credentials: 'include' });
        if (!res.ok) continue;
        const data = await res.json();

        // 응답 구조 탐지
        const list = data?.result?.fileList || data?.fileList || data?.result || data?.items || [];
        if (!Array.isArray(list) || list.length === 0) continue;

        return list.map(f => ({
          name:  f.name || f.fileName || f.title || '',
          type:  f.type || f.fileType || (f.isDir ? 'folder' : 'file'),
          size:  f.size || f.fileSize || 0,
          mtime: f.modifiedDate || f.lastModified || f.mtime || '',
          path:  f.path || f.filePath || '',
        }));
      } catch (e) { continue; }
    }

    return [];
  } catch (e) {
    return [];
  }
})(args);
