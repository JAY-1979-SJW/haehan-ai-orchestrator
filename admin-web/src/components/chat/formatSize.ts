/** 첨부 크기 표시 — 메일함 화면과 메일 초안 카드가 함께 쓴다(공용 위치: 의존은 화면 → 공용 한 방향). */
export function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(bytes < 10240 ? 1 : 0)}KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)}MB`;
}
