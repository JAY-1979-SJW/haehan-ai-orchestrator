"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { getMe, changePassword, clearToken, getToken, type UserInfo } from "@/lib/userAuth";

// 이미 등록된 네이버 개발자센터 앱("해한AI검색") — 신규 발급이 아니라 기존 키 재사용
const NAVER_OPENAPI_APP_ID = "cSW_L1d1Gic9ElCbzA_k";

const ROLE_LABEL: Record<string, string> = {
  user: "일반 사용자",
  admin: "관리자",
  owner: "최고 관리자",
  operator: "운영자",
};

const PLAN_LABEL: Record<string, string> = {
  free: "Free",
  pro: "Pro",
  enterprise: "Enterprise",
};

export default function SettingsPage() {
  const router = useRouter();
  const [user, setUser] = useState<UserInfo | null>(null);
  const [loading, setLoading] = useState(true);

  const [curPw, setCurPw] = useState("");
  const [newPw, setNewPw] = useState("");
  const [newPwConfirm, setNewPwConfirm] = useState("");
  const [pwLoading, setPwLoading] = useState(false);
  const [pwError, setPwError] = useState<string | null>(null);
  const [pwSuccess, setPwSuccess] = useState(false);

  // AI 모델 전역 설정 (localStorage) — 상세설명·AI 생성이 이 값을 사용
  const [aiModel, setAiModelState] = useState("fast");
  useEffect(() => {
    try { setAiModelState(localStorage.getItem("haehan_ai_model") || "fast"); } catch { /* ignore */ }
  }, []);
  const changeAiModel = (v: string) => {
    setAiModelState(v);
    try { localStorage.setItem("haehan_ai_model", v); } catch { /* ignore */ }
  };

  // Claude Desktop MCP 연동 (haehanLocal 존재 시에만 노출 — Electron 데스크톱 앱 전용)
  const [claudeLoading, setClaudeLoading] = useState(false);
  const [claudeResult, setClaudeResult] = useState<{ ok: boolean; error?: string; hint?: string } | null>(null);
  const handleConnectClaudeDesktop = async () => {
    setClaudeLoading(true);
    setClaudeResult(null);
    try {
      const api = (window as unknown as { haehanLocal?: { connectClaudeDesktop?: () => Promise<{ ok: boolean; error?: string; hint?: string }> } }).haehanLocal;
      if (!api?.connectClaudeDesktop) { setClaudeResult({ ok: false, error: "unsupported" }); return; }
      const r = await api.connectClaudeDesktop();
      setClaudeResult(r);
    } finally {
      setClaudeLoading(false);
    }
  };

  // 외부 API 키 (userData/.env, Electron 데스크톱 앱에서만 노출)
  const ENV_KEY_LABEL: Record<string, string> = {
    NAVER_OPENAPI_CLIENT_ID: "네이버 오픈API Client ID",
    NAVER_OPENAPI_CLIENT_SECRET: "네이버 오픈API Client Secret",
    YOUTUBE_DATA_API_KEY: "YouTube Data API 키",
    OPENAI_API_KEY: "OpenAI API 키",
    UNSPLASH_ACCESS_KEY: "Unsplash Access Key",
  };
  const [envAvailable, setEnvAvailable] = useState(false);
  const [envKeys, setEnvKeys] = useState<string[]>([]);
  const [envMasked, setEnvMasked] = useState<Record<string, string>>({});
  const [envInput, setEnvInput] = useState<Record<string, string>>({});
  const [envSaving, setEnvSaving] = useState(false);
  const [envSaved, setEnvSaved] = useState(false);

  useEffect(() => {
    const api = (window as unknown as { haehanLocal?: { getEnvKeys?: () => Promise<{ keys: string[]; values: Record<string, string> }> } }).haehanLocal;
    if (!api?.getEnvKeys) return; // 웹 브라우저 환경(데스크톱 앱 아님) — 섹션 숨김
    setEnvAvailable(true);
    api.getEnvKeys().then(({ keys, values }) => {
      setEnvKeys(keys);
      setEnvMasked(values);
    }).catch(() => {});
  }, []);

  const [naverLookupLoading, setNaverLookupLoading] = useState(false);
  const [naverLookupError, setNaverLookupError] = useState<string | null>(null);

  // 네이버 개발자센터에 이미 등록된 앱의 Client ID/Secret을 CDP로 조회해 입력란에 채운다.
  // Client Secret은 "보기" 클릭이 필요한 민감값이라 여기서 한 번 더 확인받은 뒤에만 조회한다.
  const handleNaverLookup = async () => {
    if (!window.confirm("네이버 개발자센터에서 이 앱의 Client Secret을 조회합니다. 계속할까요?")) return;
    setNaverLookupLoading(true);
    setNaverLookupError(null);
    try {
      const token = getToken();
      const res = await fetch("/api/proxy/api/v1/naver/openapi-setup/lookup-keys", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ app_id: NAVER_OPENAPI_APP_ID, confirm_secret_reveal: true }),
      });
      const data = await res.json();
      if (!data.ok) { setNaverLookupError(data.error || "조회 실패"); return; }
      setEnvInput((prev) => ({
        ...prev,
        NAVER_OPENAPI_CLIENT_ID: data.client_id ?? prev.NAVER_OPENAPI_CLIENT_ID,
        NAVER_OPENAPI_CLIENT_SECRET: data.client_secret ?? prev.NAVER_OPENAPI_CLIENT_SECRET,
      }));
    } catch {
      setNaverLookupError("조회 실패 — 개발자센터 로그인 상태를 확인하세요");
    } finally {
      setNaverLookupLoading(false);
    }
  };

  const handleEnvSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setEnvSaving(true);
    setEnvSaved(false);
    try {
      const api = (window as unknown as { haehanLocal: { setEnvKeys: (p: Record<string, string>) => Promise<{ ok: boolean; values: Record<string, string> }> } }).haehanLocal;
      const { values } = await api.setEnvKeys(envInput);
      setEnvMasked(values);
      setEnvInput({});
      setEnvSaved(true);
    } finally {
      setEnvSaving(false);
    }
  };

  useEffect(() => {
    getMe().then((u) => {
      if (!u) { router.push("/login"); return; }
      setUser(u);
      setLoading(false);
    });
  }, [router]);

  const handleLogout = () => {
    clearToken();
    router.push("/login");
  };

  const handlePasswordChange = async (e: React.FormEvent) => {
    e.preventDefault();
    setPwError(null);
    setPwSuccess(false);
    if (newPw !== newPwConfirm) { setPwError("새 비밀번호가 일치하지 않습니다"); return; }
    if (newPw.length < 8) { setPwError("비밀번호는 최소 8자입니다"); return; }
    setPwLoading(true);
    try {
      await changePassword(curPw, newPw);
      setPwSuccess(true);
      setCurPw(""); setNewPw(""); setNewPwConfirm("");
    } catch (err) {
      setPwError(err instanceof Error ? err.message : "변경 실패");
    } finally {
      setPwLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-[#F9FAFB] flex items-center justify-center">
        <p className="text-sm text-[#6B7280]">로딩 중...</p>
      </div>
    );
  }
  if (!user) return null;

  const isOwner = user.role === "owner" || user.role === "admin";
  const joinedAt = new Date(user.created_at).toLocaleDateString("ko-KR", {
    year: "numeric", month: "long", day: "numeric",
  });

  return (
    <div className="min-h-screen bg-[#F9FAFB] px-4 py-8">
      <div className="max-w-lg mx-auto space-y-4">
        {/* 헤더 */}
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-[#F97316] flex items-center justify-center text-white font-bold text-xs">AI</div>
            <Link href="/" className="text-sm font-semibold text-[#111827] hover:text-[#F97316]">Haehan AI</Link>
            <span className="text-sm text-[#9CA3AF]">설정</span>
          </div>
          <button onClick={handleLogout}
            className="text-sm text-[#6B7280] hover:text-[#111827] transition-colors">
            로그아웃
          </button>
        </div>

        {/* 프로필 카드 */}
        <div className="bg-white border border-[#E5E7EB] rounded-2xl p-6">
          <div className="flex items-center gap-4 mb-5">
            <div className="w-14 h-14 rounded-full bg-[#FFF7ED] border-2 border-[#F97316] flex items-center justify-center text-[#F97316] font-bold text-xl">
              {user.name.charAt(0)}
            </div>
            <div>
              <p className="text-base font-bold text-[#111827]">{user.name}</p>
              <p className="text-sm text-[#6B7280]">{user.email}</p>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="rounded-xl bg-[#F9FAFB] border border-[#E5E7EB] px-4 py-3">
              <p className="text-xs text-[#9CA3AF] mb-1">역할</p>
              <p className="text-sm font-semibold text-[#111827]">{ROLE_LABEL[user.role] ?? user.role}</p>
            </div>
            <div className="rounded-xl bg-[#F9FAFB] border border-[#E5E7EB] px-4 py-3">
              <p className="text-xs text-[#9CA3AF] mb-1">플랜</p>
              <p className="text-sm font-semibold text-[#F97316]">{PLAN_LABEL[user.plan] ?? user.plan}</p>
            </div>
            <div className="col-span-2 rounded-xl bg-[#F9FAFB] border border-[#E5E7EB] px-4 py-3">
              <p className="text-xs text-[#9CA3AF] mb-1">가입일</p>
              <p className="text-sm font-semibold text-[#111827]">{joinedAt}</p>
            </div>
          </div>
        </div>

        {/* 최고 관리자 바로가기 (owner/admin 전용) */}
        {isOwner && (
          <Link href="/admin"
            className="block bg-[#111827] text-white border border-[#111827] rounded-2xl p-5 hover:bg-[#1F2937] transition-colors">
            <p className="text-sm font-bold">최고 관리자 페이지</p>
            <p className="text-xs text-[#9CA3AF] mt-1">사용자 승인·관리, 라이선스, 운영센터</p>
          </Link>
        )}

        {/* AI 모델 (전역) */}
        <div className="bg-white border border-[#E5E7EB] rounded-2xl p-6">
          <h2 className="text-sm font-bold text-[#111827] mb-1">AI 모델</h2>
          <p className="text-xs text-[#6B7280] mb-3">상품 상세설명·AI 생성에 쓸 모델입니다. 스마트스토어 등 모든 화면에 적용됩니다.</p>
          <select value={aiModel} onChange={(e) => changeAiModel(e.target.value)}
            className="w-full border border-[#E5E7EB] rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#F97316]">
            <option value="fast">빠름 — GPT-4o mini (저렴·빠름, 권장)</option>
            <option value="quality">고품질 — GPT-4o (이미지 분석 강함)</option>
            <option value="claude">Claude (고품질, 자연스러운 문장)</option>
          </select>
        </div>

        {/* 외부 API 키 (owner/admin 전용, 데스크톱 앱에서만 노출) */}
        {isOwner && envAvailable && (
          <div className="bg-white border border-[#E5E7EB] rounded-2xl p-6">
            <h2 className="text-sm font-bold text-[#111827] mb-1">외부 API 키</h2>
            <p className="text-xs text-[#6B7280] mb-3">이 PC의 앱에서만 사용되는 키입니다. 저장 후 앱 재시작 시 적용됩니다.</p>
            <button type="button" onClick={handleNaverLookup} disabled={naverLookupLoading}
              className="w-full mb-3 py-2 rounded-xl border border-[#E5E7EB] text-sm font-semibold text-[#111827] hover:bg-[#F9FAFB] disabled:opacity-50 transition-colors">
              {naverLookupLoading ? "조회 중..." : "네이버 API 키 자동 조회 (기존 등록 앱)"}
            </button>
            {naverLookupError && <div className="mb-3 rounded-xl bg-[#FEF2F2] border border-[#FECACA] px-4 py-2.5 text-sm text-[#DC2626]">{naverLookupError}</div>}
            <form onSubmit={handleEnvSave} className="space-y-3">
              {envKeys.map((k) => (
                <div key={k}>
                  <label className="block text-xs font-medium text-[#374151] mb-1">
                    {ENV_KEY_LABEL[k] ?? k}
                    {envMasked[k] ? <span className="ml-2 text-[#9CA3AF]">현재: {envMasked[k]}</span> : null}
                  </label>
                  <input
                    type="password"
                    value={envInput[k] ?? ""}
                    onChange={(e) => setEnvInput((prev) => ({ ...prev, [k]: e.target.value }))}
                    placeholder={envMasked[k] ? "변경하려면 새 값 입력" : "값 입력"}
                    className="w-full border border-[#E5E7EB] rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#F97316] focus:border-transparent"
                  />
                </div>
              ))}
              {envSaved && <div className="rounded-xl bg-[#F0FDF4] border border-[#BBF7D0] px-4 py-2.5 text-sm text-[#16A34A]">저장되었습니다</div>}
              <button type="submit" disabled={envSaving}
                className="w-full py-2.5 rounded-xl bg-[#111827] text-white text-sm font-semibold hover:bg-[#374151] disabled:opacity-50 transition-colors">
                {envSaving ? "저장 중..." : "저장"}
              </button>
            </form>
          </div>
        )}

        {/* Claude Desktop MCP 연동 (owner/admin 전용, 데스크톱 앱에서만 노출) */}
        {isOwner && envAvailable && (
          <div className="bg-white border border-[#E5E7EB] rounded-2xl p-6">
            <h2 className="text-sm font-bold text-[#111827] mb-1">Claude Desktop 연동</h2>
            <p className="text-xs text-[#6B7280] mb-3">
              이 PC의 Claude Desktop에 스마트스토어 등 도구를 MCP로 연결합니다. Claude Desktop이 설치되어 있어야 합니다.
            </p>
            <button type="button" onClick={handleConnectClaudeDesktop} disabled={claudeLoading}
              className="w-full py-2 rounded-xl border border-[#E5E7EB] text-sm font-semibold text-[#111827] hover:bg-[#F9FAFB] disabled:opacity-50 transition-colors">
              {claudeLoading ? "연결 중..." : "Claude Desktop에 연결"}
            </button>
            {claudeResult && (
              claudeResult.ok ? (
                <div className="mt-3 rounded-xl bg-[#F0FDF4] border border-[#BBF7D0] px-4 py-2.5 text-sm text-[#16A34A]">
                  연결되었습니다 — {claudeResult.hint}
                </div>
              ) : (
                <div className="mt-3 rounded-xl bg-[#FEF2F2] border border-[#FECACA] px-4 py-2.5 text-sm text-[#DC2626]">
                  {claudeResult.hint || claudeResult.error}
                </div>
              )
            )}
          </div>
        )}

        {/* 비밀번호 변경 */}
        <div className="bg-white border border-[#E5E7EB] rounded-2xl p-6">
          <h2 className="text-sm font-bold text-[#111827] mb-4">비밀번호 변경</h2>
          <form onSubmit={handlePasswordChange} className="space-y-3">
            <div>
              <label className="block text-xs font-medium text-[#374151] mb-1">현재 비밀번호</label>
              <input type="password" value={curPw} onChange={(e) => setCurPw(e.target.value)} required
                className="w-full border border-[#E5E7EB] rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#F97316] focus:border-transparent" />
            </div>
            <div>
              <label className="block text-xs font-medium text-[#374151] mb-1">새 비밀번호</label>
              <input type="password" value={newPw} onChange={(e) => setNewPw(e.target.value)} required placeholder="최소 8자"
                className="w-full border border-[#E5E7EB] rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#F97316] focus:border-transparent" />
            </div>
            <div>
              <label className="block text-xs font-medium text-[#374151] mb-1">새 비밀번호 확인</label>
              <input type="password" value={newPwConfirm} onChange={(e) => setNewPwConfirm(e.target.value)} required
                className="w-full border border-[#E5E7EB] rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#F97316] focus:border-transparent" />
            </div>
            {pwError && <div className="rounded-xl bg-[#FEF2F2] border border-[#FECACA] px-4 py-2.5 text-sm text-[#DC2626]">{pwError}</div>}
            {pwSuccess && <div className="rounded-xl bg-[#F0FDF4] border border-[#BBF7D0] px-4 py-2.5 text-sm text-[#16A34A]">비밀번호가 변경되었습니다</div>}
            <button type="submit" disabled={pwLoading}
              className="w-full py-2.5 rounded-xl bg-[#111827] text-white text-sm font-semibold hover:bg-[#374151] disabled:opacity-50 transition-colors">
              {pwLoading ? "변경 중..." : "비밀번호 변경"}
            </button>
          </form>
        </div>

        <div className="text-center">
          <Link href="/" className="text-sm text-[#6B7280] hover:text-[#111827] transition-colors">← 홈으로</Link>
        </div>
      </div>
    </div>
  );
}
