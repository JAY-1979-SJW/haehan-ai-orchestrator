const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8401";
const TOKEN_KEY = "haehan_ai_token";

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
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

async function post(path: string, body: object): Promise<Response> {
  return fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function signup(email: string, name: string, password: string): Promise<{ token: string; user: UserInfo }> {
  const res = await post("/api/v1/users/signup", { email, name, password });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail ?? "회원가입 실패");
  return data;
}

export async function login(email: string, password: string): Promise<{ token: string; user: UserInfo }> {
  const res = await post("/api/v1/users/login", { email, password });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail ?? "로그인 실패");
  return data;
}

export async function getMe(): Promise<UserInfo | null> {
  const token = getToken();
  if (!token) return null;
  const res = await fetch(`${API_BASE}/api/v1/users/me`, {
    headers: { Authorization: `Bearer ${token}` },
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
