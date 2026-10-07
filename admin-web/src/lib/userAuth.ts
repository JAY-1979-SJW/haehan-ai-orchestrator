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
  const res = await fetch(`${API_BASE}/api/v1/users/me`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (res.ok) return res.json();

  // 자기완결 데스크톱(AUTH_ENABLED=false) fallback: /auth/me 시도.
  // 번들 exe의 /users/me 가 구버전이어도 /auth/me 는 AUTH off 시 owner 반환.
  if (res.status === 401) {
    try {
      const r2 = await fetch(`${API_BASE}/api/v1/auth/me`);
      if (r2.ok) {
        const d = await r2.json();
        if (d.role === "owner" || d.actor === "system") {
          return { id: "owner", email: "owner@local", name: "Owner", role: "owner", plan: "owner", created_at: "" };
        }
      }
    } catch { /* 무시 */ }
  }
  return null;
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

export interface BuildInfo {
  git_sha: string; // 7~40자 hex 또는 "unknown"
  build_time: string; // ISO8601 또는 "unknown"
}

/** 서버(health)가 알려 주는 빌드 정보 — 데스크톱은 build-info.json 값을 서버에 env 로 넘겨 준다. 실패하면 null. */
export async function getBuildInfo(): Promise<BuildInfo | null> {
  try {
    const res = await fetch(`${API_BASE}/api/v1/health`, { cache: "no-store" });
    if (!res.ok) return null;
    const data = await res.json();
    return {
      git_sha: typeof data.git_sha === "string" ? data.git_sha : "unknown",
      build_time: typeof data.build_time === "string" ? data.build_time : "unknown",
    };
  } catch {
    return null;
  }
}

// ── 데스크톱 로컬 모드: 첫 실행 등록(이름·이메일)·자동 세션 ────────────────────────────
// 백엔드가 데스크톱 모드에서만 응답한다(그 외 404). 비밀번호는 쓰지 않는다.
const DESKTOP_HEADERS = { "Content-Type": "application/json", "X-Haehan-Desktop": "1" };

export async function getDesktopSetupStatus(): Promise<{ needs_setup: boolean } | null> {
  try {
    const res = await fetch(`${API_BASE}/api/v1/auth/desktop-setup-status`, { cache: "no-store" });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

export async function desktopSetup(name: string, email: string): Promise<{ token: string; user: UserInfo }> {
  const res = await fetch(`${API_BASE}/api/v1/auth/desktop-setup`, {
    method: "POST",
    headers: DESKTOP_HEADERS,
    body: JSON.stringify({ name, email }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = Array.isArray(data.detail) ? data.detail.map((d: { msg?: string }) => d.msg).join(", ") : data.detail;
    throw new Error(detail ?? "등록 실패");
  }
  return data;
}

/** 등록된 owner 로 새 토큰을 받는다. 첫 실행(등록 필요)이면 "needs_setup", 실패하면 null. */
export async function desktopSession(): Promise<{ token: string; user: UserInfo } | "needs_setup" | null> {
  try {
    const res = await fetch(`${API_BASE}/api/v1/auth/desktop-session`, { method: "POST", headers: DESKTOP_HEADERS, body: "{}" });
    if (res.status === 409) {
      const data = await res.json().catch(() => ({}));
      return data.detail === "needs_setup" ? "needs_setup" : null;
    }
    return res.ok ? await res.json() : null;
  } catch {
    return null;
  }
}
