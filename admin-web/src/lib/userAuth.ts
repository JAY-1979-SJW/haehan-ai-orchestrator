// same-origin 프록시(/api/proxy → 서버사이드 포워딩). 데스크톱 webview(127.0.0.1:3000)에서
// localhost:8401 직접 호출 시 cross-origin CORS 차단되어 getMe 실패 → 랜딩으로 튕기던 문제 해결.
// assistant/api.ts 와 동일한 same-origin 규약.
const API_BASE = "/api/proxy";
const TOKEN_KEY = "haehan_ai_token";
const COOKIE_MAX_AGE = 60 * 60 * 24 * 30; // 30일 (JWT_EXPIRE_DAYS와 일치)

export interface UserInfo {
  id: string;
  email: string;
  name: string;
  role: string;
  plan: string;
  created_at: string;
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
  // 미들웨어(서버사이드)가 읽을 수 있도록 쿠키에도 저장
  document.cookie = [
    `${TOKEN_KEY}=${encodeURIComponent(token)}`,
    `path=/`,
    `max-age=${COOKIE_MAX_AGE}`,
    `samesite=lax`,
    ...(location.protocol === "https:" ? ["secure"] : []),
  ].join("; ");
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
  document.cookie = `${TOKEN_KEY}=; path=/; max-age=0; samesite=lax`;
}

async function post(path: string, body: object): Promise<Response> {
  return fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export interface SignupResult {
  status: string; // "pending_approval"
  message: string;
  user: UserInfo;
}

export async function signup(email: string, name: string, password: string): Promise<SignupResult> {
  const res = await post("/api/v1/users/signup", { email, name, password });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail ?? "회원가입 실패");
  return data; // { status, message, user } — 토큰 미발급(승인 후 로그인)
}

export async function login(email: string, password: string): Promise<{ token: string; user: UserInfo }> {
  const res = await post("/api/v1/users/login", { email, password });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail ?? "로그인 실패");
  return data;
}

export async function getMe(): Promise<UserInfo | null> {
  const token = getToken();
  // 토큰이 없어도 /me 를 호출한다: 자기완결 데스크톱(AUTH off)은 서버가 owner 를 자동 반환 → 자동 로그인.
  // 운영 웹(AUTH on)은 토큰 없으면 401 → null → 정상 로그인 흐름 유지.
  const res = await fetch(`${API_BASE}/api/v1/users/me`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) return null;
  return res.json();
}

export async function changePassword(currentPassword: string, newPassword: string): Promise<void> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/v1/users/me/password`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail ?? "비밀번호 변경 실패");
  }
}
