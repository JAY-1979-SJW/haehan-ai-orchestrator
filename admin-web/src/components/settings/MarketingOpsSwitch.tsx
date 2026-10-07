"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { getMarketingOpsSettings, setMarketingOpsEnabled } from "@/lib/marketingOps";

/** 설정 화면(/mypage) 안의 위치 표식 — 마케팅 운영 안내에서 이 스위치로 바로 오게 한다. */
export const MARKETING_OPS_ANCHOR = "marketing-ops";
export const MARKETING_OPS_SETTINGS_HREF = `/mypage#${MARKETING_OPS_ANCHOR}`;

/** 마케팅 운영이 꺼져 있을 때 보여 주는 안내와 스위치로 가는 링크(서버의 403 "설정에서 마케팅 운영을 켜세요"와 같은 문구). */
export function MarketingOpsOffNotice() {
  return (
    <p className="text-sm text-[#6B7280]">
      설정에서 마케팅 운영을 켜세요.{" "}
      <Link href={MARKETING_OPS_SETTINGS_HREF} className="font-semibold text-[#F97316] hover:underline">
        설정으로 이동
      </Link>
    </p>
  );
}

/** 마케팅 운영 켜기/끄기 스위치(관리자·오너 전용 — 호출하는 쪽이 역할을 확인한다). 기본은 꺼짐. */
export function MarketingOpsSwitch() {
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    getMarketingOpsSettings()
      .then((s) => {
        if (alive) setEnabled(s.enabled);
      })
      .catch((e: unknown) => {
        if (alive) setError(e instanceof Error ? e.message : "상태를 불러오지 못했습니다");
      });
    return () => {
      alive = false;
    };
  }, []);

  const toggle = useCallback(async () => {
    if (enabled === null || busy) return;
    setBusy(true);
    setError(null);
    try {
      const s = await setMarketingOpsEnabled(!enabled);
      setEnabled(s.enabled);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "변경하지 못했습니다");
    } finally {
      setBusy(false);
    }
  }, [enabled, busy]);

  return (
    <div id={MARKETING_OPS_ANCHOR} className="bg-white border border-[#E5E7EB] rounded-2xl p-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h2 className="text-sm font-bold text-[#111827]">마케팅 운영</h2>
          <p className="mt-1 text-xs text-[#6B7280]">
            홍보 자료 만들기·블로그 발행·이웃 관리 기능을 사용합니다. 꺼져 있으면 사용할 수 없고, 켜고 끈 기록이 남습니다.
            블로그 발행은 켜져 있어도 실행 직전에 확인 문구를 직접 입력해야 합니다.
          </p>
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={enabled === true}
          aria-label="마케팅 운영 사용"
          disabled={enabled === null || busy}
          onClick={toggle}
          className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors disabled:opacity-50 ${
            enabled ? "bg-[#F97316]" : "bg-[#D1D5DB]"
          }`}
        >
          <span
            className={`inline-block h-5 w-5 transform rounded-full bg-white transition-transform ${
              enabled ? "translate-x-5" : "translate-x-0.5"
            }`}
          />
        </button>
      </div>
      <p className="mt-3 text-xs font-medium text-[#374151]">
        {enabled === null ? (error ? "상태를 알 수 없습니다" : "불러오는 중...") : enabled ? "켜짐" : "꺼짐 (기본값)"}
      </p>
      {error && (
        <div className="mt-3 rounded-xl bg-[#FEF2F2] border border-[#FECACA] px-4 py-2.5 text-sm text-[#DC2626]">{error}</div>
      )}
    </div>
  );
}
