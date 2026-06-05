/** 유튜브 — 공유 타입·라벨 */

export interface OAuthStatus {
  ok: boolean;
  status: string;
  scopes: string[];
  has_upload_scope: boolean;
  channel?: { title: string; id: string };
  error?: string;
}

export const SCOPE_LABELS: Record<string, string> = {
  "https://www.googleapis.com/auth/youtube.force-ssl": "YouTube 읽기/기본",
  "https://www.googleapis.com/auth/youtube.upload":    "YouTube 업로드 ✅",
  "https://www.googleapis.com/auth/youtube.readonly":  "YouTube 읽기 전용",
  "https://www.googleapis.com/auth/userinfo.email":    "이메일 확인",
  "https://www.googleapis.com/auth/userinfo.profile":  "프로필 확인",
  "openid":                                            "OpenID",
};

