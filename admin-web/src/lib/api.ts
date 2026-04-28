export const API_BASE_PATH = "/api/v1";

export function buildApiUrl(path: string): string {
  return `${API_BASE_PATH}${path.startsWith("/") ? path : `/${path}`}`;
}
