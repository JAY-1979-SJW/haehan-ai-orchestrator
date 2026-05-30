// 상품 목록 헤더에서 product_id 컬럼 인덱스 탐색
export function findProductIdIndex(headers: string[]): number {
  const keys = ["상품번호", "productNo", "상품 번호", "번호"];
  return headers.findIndex(h => keys.some(k => h.includes(k)));
}

// 행 데이터에서 product_id 추출 (링크 href 또는 텍스트)
export function extractProductId(row: string[], pidIdx: number): string | null {
  const cell = pidIdx >= 0 ? row[pidIdx] : row[0];
  if (!cell) return null;
  const m = cell.match(/\d{8,}/);
  return m ? m[0] : null;
}
