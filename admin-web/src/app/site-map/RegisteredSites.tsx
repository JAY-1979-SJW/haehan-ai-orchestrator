"use client";

import { useCallback, useEffect, useState } from "react";
import {
  AUTH_LABEL,
  SITE_STATE_LABEL,
  siteRegistryApi,
  type Auth,
  type OfficialApiAdvice,
  type RegisteredSite,
  type SiteState,
} from "./api";

/**
 * 등록 사이트(M7-S1) — 로그인한 사이트의 호스트를 등록하면 최초 탐색으로 업무 지도를 만든다.
 * 기준서: docs/specs/2026-10-05_site_task_map_m7_onboarding_auto_prepare.md (F1)
 * 등록 버튼이 곧 최초 탐색의 승인이다(사람이 누른다). 로그인은 사람이 먼저 해 둔다 — 이 화면은 로그인하지 않는다.
 */

const STATE_STYLE: Record<SiteState, string> = {
  registered: "bg-gray-100 text-gray-700",
  exploring: "bg-blue-100 text-blue-800",
  ready: "bg-green-100 text-green-800",
  incomplete: "bg-orange-100 text-orange-800",
  needs_login: "bg-amber-100 text-amber-800",
  blocked: "bg-red-100 text-red-800",
  deregistered: "bg-gray-200 text-gray-600",
};
const field = "rounded-lg border border-[#E5E7EB] px-2 py-1 text-[12px]";
const btn = "rounded-lg border border-[#E5E7EB] bg-white px-3 py-1 text-[12px] hover:bg-[#F9FAFB] disabled:opacity-50";
const btnPrimary = "rounded-lg border border-[#F97316] bg-[#F97316] px-3 py-1 text-[12px] text-white hover:bg-[#EA580C] disabled:opacity-50";
const errText = (e: unknown) => (e instanceof Error ? e.message : String(e));
const day = (iso: string) => (iso ? iso.slice(0, 10) : "-");
const POLL_MS = 3000;

export function RegisteredSites({ onChanged, onPick }: { onChanged: () => void; onPick: (host: string) => void }) {
  const [sites, setSites] = useState<RegisteredSite[]>([]);
  const [host, setHost] = useState("");
  const [auth, setAuth] = useState<Auth>("login");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [advice, setAdvice] = useState<{ host: string; api: OfficialApiAdvice } | null>(null);
  const [confirming, setConfirming] = useState<string | null>(null); // 해제 확인 중인 호스트(인라인 2단계 — 브라우저 대화상자는 쓰지 않는다)

  const refresh = useCallback(async () => {
    try {
      setSites(await siteRegistryApi.list());
    } catch (e) {
      setError(errText(e));
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // 탐색 중인 사이트가 있을 때만 상태를 다시 읽는다(서버가 읽을 때 갱신한다 — 별도 백그라운드 루프 없음).
  const exploring = sites.some((s) => s.state === "exploring");
  useEffect(() => {
    if (!exploring) return;
    const id = setInterval(() => {
      void refresh().then(onChanged);
    }, POLL_MS);
    return () => clearInterval(id);
  }, [exploring, refresh, onChanged]);

  async function register() {
    const target = host.trim();
    if (!target) return;
    setBusy(true);
    setError(null);
    setAdvice(null);
    try {
      const out = await siteRegistryApi.register(target, auth);
      setAdvice({ host: out.site.host, api: out.official_api });
      setHost("");
      await refresh();
      onChanged();
    } catch (e) {
      setError(errText(e));
    } finally {
      setBusy(false);
    }
  }

  async function deregister(h: string) {
    setConfirming(null);
    setBusy(true);
    setError(null);
    try {
      await siteRegistryApi.deregister(h);
      await refresh();
      onChanged();
    } catch (e) {
      setError(errText(e));
    } finally {
      setBusy(false);
    }
  }

  const active = sites.filter((s) => s.state !== "deregistered");

  return (
    <div className="rounded-xl border border-[#E5E7EB] bg-white p-3" data-testid="registered-sites">
      <div className="mb-1 font-semibold">사이트 등록</div>
      <p className="mb-2 text-[12px] text-[#6B7280]">
        먼저 브라우저에서 사이트에 로그인해 두고 호스트를 등록하세요. 등록하면 읽기 전용으로 둘러보며 업무 지도를 만듭니다(입력·제출은 하지 않습니다).
        이 화면은 로그인하지 않으며, 로그인이 풀리면 &quot;로그인 필요&quot;로 표시됩니다.
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <input
          className={`${field} w-64`}
          placeholder="예: cafe.naver.com 또는 사이트 주소"
          value={host}
          onChange={(e) => setHost(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") void register();
          }}
          aria-label="등록할 사이트 호스트"
        />
        <select className={field} value={auth} onChange={(e) => setAuth(e.target.value as Auth)} aria-label="로그인 요건">
          <option value="login">{AUTH_LABEL.login} 사이트</option>
          <option value="public">{AUTH_LABEL.public} 사이트</option>
          <option value="certificate">{AUTH_LABEL.certificate} 사이트</option>
        </select>
        <button className={btnPrimary} disabled={busy || !host.trim()} onClick={() => void register()}>
          등록하고 탐색 시작
        </button>
      </div>
      {error && <div className="mt-2 rounded-lg bg-red-50 p-2 text-red-700" role="alert">{error}</div>}
      {advice && (
        <div className="mt-2 rounded-lg bg-blue-50 p-2 text-[12px] text-blue-900" data-testid="official-api-advice">
          {advice.host} 등록 완료 — 공식 API 확인: {advice.api.checked ? advice.api.advice : `확인하지 못했습니다(${advice.api.error ?? ""})`}
          {advice.api.vendors && advice.api.vendors.length > 0 && (
            <ul className="mt-1 list-disc pl-5">
              {advice.api.vendors.map((v) => (
                <li key={v.name}>
                  {v.name} · {v.status} · {v.cost}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      {active.length > 0 && (
        <ul className="mt-3 space-y-1">
          {active.map((s) => (
            <li key={s.host} className="flex flex-wrap items-center gap-2 rounded-lg border border-[#F3F4F6] px-2 py-1">
              <button className="font-medium underline-offset-2 hover:underline" onClick={() => onPick(s.host)}>
                {s.host}
              </button>
              <span className={`rounded px-2 text-[11px] ${STATE_STYLE[s.state]}`}>{SITE_STATE_LABEL[s.state]}</span>
              <span className="text-[12px] text-[#6B7280]">
                업무 {s.map.tasks}개 · 검증 {s.map.verified} · 탐색 {day(s.last_explored_at)} · 갱신 방식: 승인 카드(ask)
                {s.explored && (
                  <>
                    {" "}
                    · 이동한 {s.explored.host} 업무 {s.explored.tasks}개
                  </>
                )}
              </span>
              {s.note && <span className="text-[12px] text-[#6B7280]">— {s.note}</span>}
              {confirming === s.host ? (
                <span className="ml-auto flex items-center gap-1 text-[12px]">
                  <span className="text-[#6B7280]">지도는 지우지 않습니다.</span>
                  <button className={btnPrimary} disabled={busy} onClick={() => void deregister(s.host)}>
                    해제 확인
                  </button>
                  <button className={btn} onClick={() => setConfirming(null)}>
                    취소
                  </button>
                </span>
              ) : (
                <button className={`${btn} ml-auto`} disabled={busy} onClick={() => setConfirming(s.host)}>
                  등록 해제
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
