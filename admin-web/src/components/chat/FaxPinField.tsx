"use client";

import { useEffect, useState } from "react";
import { faxApi } from "@/app/hanafax/api";

/**
 * 승인 PIN 입력칸 — 팩스 승인·정지 해제는 사람만 아는 PIN 이 맞아야 한다(AI·다른 프로그램이 API 를 직접 불러도 승인되지 않게).
 * PIN 이 아직 없으면 여기서 처음 만든다. 값은 부모로만 올리고 저장하지 않는다.
 */
export function FaxPinField({ value, onChange }: { value: string; onChange: (pin: string) => void }) {
  const [configured, setConfigured] = useState<boolean | null>(null);
  const [fresh, setFresh] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    faxApi.pinStatus().then((s) => setConfigured(s.configured)).catch((e) => setError(String(e)));
  }, []);

  async function create() {
    setError(null);
    try {
      await faxApi.setPin(fresh);
      onChange(fresh);
      setFresh("");
      setConfigured(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  if (configured === null) return <div className="text-[11px] text-gray-500">{error ?? "PIN 상태 확인 중…"}</div>;
  const box = "rounded border border-[#D1D5DB] px-2 py-1 text-[11px]";
  return (
    <div className="space-y-1" data-testid="fax-pin-field">
      {configured ? (
        <label className="flex items-center gap-2">
          승인 PIN
          <input type="password" autoComplete="off" className={box} value={value} onChange={(e) => onChange(e.target.value)} placeholder="승인 PIN" />
        </label>
      ) : (
        <div className="space-y-1 rounded bg-amber-50 p-2">
          <div>승인 PIN 이 아직 없습니다. 팩스 승인은 사람만 아는 PIN 이 맞아야 합니다 — 6자 이상으로 만드세요.</div>
          <input type="password" autoComplete="new-password" className={box} value={fresh} onChange={(e) => setFresh(e.target.value)} placeholder="새 PIN (6자 이상)" />
          <button className="ml-2 rounded bg-[#F97316] px-2 py-1 text-white disabled:opacity-50" disabled={fresh.length < 6} onClick={create}>
            PIN 만들기
          </button>
        </div>
      )}
      {error && <div className="text-red-600">{error}</div>}
    </div>
  );
}
