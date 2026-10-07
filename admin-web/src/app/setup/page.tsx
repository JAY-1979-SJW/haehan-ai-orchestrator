"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { desktopSession, desktopSetup, getDesktopSetupStatus, setToken } from "@/lib/userAuth";

// 데스크톱 앱 전용 진입 화면.
// - 첫 실행(등록된 사용자 없음): 이름·이메일을 한 번만 입력한다(비밀번호 없음).
// - 이미 등록됨: 이 화면이 자동 세션을 받아 바로 원래 가려던 곳으로 보낸다.
// 서버(웹) 모드에서는 백엔드가 404 로 응답해 "데스크톱 앱에서만" 안내가 나온다.

type Phase = "checking" | "form" | "unavailable";

function safeReturnTo(): string {
  const raw = new URLSearchParams(window.location.search).get("returnTo") ?? "/";
  return raw.startsWith("/") && !raw.startsWith("//") ? raw : "/";
}

export default function SetupPage() {
  const router = useRouter();
  const [phase, setPhase] = useState<Phase>("checking");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const status = await getDesktopSetupStatus();
      if (cancelled) return;
      if (!status) {
        setPhase("unavailable");
        return;
      }
      if (status.needs_setup) {
        setPhase("form");
        return;
      }
      const session = await desktopSession();
      if (cancelled) return;
      if (session && session !== "needs_setup") {
        setToken(session.token);
        router.replace(safeReturnTo());
      } else {
        setPhase(session === "needs_setup" ? "form" : "unavailable");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [router]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSaving(true);
    try {
      const result = await desktopSetup(name, email);
      setToken(result.token);
      router.replace(safeReturnTo());
    } catch (err) {
      setError(err instanceof Error ? err.message : "등록 실패");
    } finally {
      setSaving(false);
    }
  };

  if (phase === "checking") {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#F9FAFB] text-sm text-[#6B7280]">
        시작하는 중...
      </div>
    );
  }

  if (phase === "unavailable") {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#F9FAFB] px-4">
        <div className="max-w-sm text-center text-sm text-[#374151]">
          <p className="font-semibold text-[#111827] mb-2">시작할 수 없습니다</p>
          <p>이 화면은 데스크톱 앱에서만 사용할 수 있습니다. 앱을 다시 실행해 주세요.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#F9FAFB] px-4">
      <div className="w-full max-w-sm bg-white border border-[#E5E7EB] rounded-2xl p-6">
        <h1 className="text-lg font-bold text-[#111827] mb-1">사용자 정보</h1>
        <p className="text-sm text-[#6B7280] mb-5">처음 한 번만 입력합니다. 이후에는 비밀번호 없이 바로 시작됩니다.</p>
        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <label htmlFor="setup-name" className="block text-xs font-medium text-[#374151] mb-1">이름</label>
            <input
              id="setup-name"
              name="name"
              data-testid="setup-name"
              autoComplete="name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              maxLength={50}
              className="w-full border border-[#E5E7EB] rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#F97316] focus:border-transparent"
            />
          </div>
          <div>
            <label htmlFor="setup-email" className="block text-xs font-medium text-[#374151] mb-1">이메일</label>
            <input
              id="setup-email"
              name="email"
              data-testid="setup-email"
              autoComplete="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="w-full border border-[#E5E7EB] rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#F97316] focus:border-transparent"
            />
          </div>
          {error && (
            <div role="alert" data-testid="setup-error" className="rounded-xl bg-[#FEF2F2] border border-[#FECACA] px-4 py-2.5 text-sm text-[#DC2626]">{error}</div>
          )}
          <button
            type="submit"
            id="setup-submit"
            data-testid="setup-submit"
            disabled={saving}
            className="w-full py-2.5 rounded-xl bg-[#111827] text-white text-sm font-semibold hover:bg-[#374151] disabled:opacity-50 transition-colors"
          >
            {saving ? "저장 중..." : "시작하기"}
          </button>
        </form>
      </div>
    </div>
  );
}
