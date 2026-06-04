"use client";
import { useState } from "react";

// 상품 정보 입력 폼 — JSON 코드 대신 라벨+입력칸.
// value(JSON 문자열) 를 내부에서 파싱/직렬화하여 기존 백엔드와 그대로 호환.
// 사용자가 모르는 항목은 비워도 AI가 보완(사진 분석 포함) → 각 칸에 안내 동봉.

type Obj = Record<string, unknown>;

function parseObj(s: string): Obj {
  try {
    const o = JSON.parse(s);
    return o && typeof o === "object" && !Array.isArray(o) ? (o as Obj) : {};
  } catch {
    return {};
  }
}

const featuresToText = (v: unknown): string =>
  Array.isArray(v)
    ? v.map((f) => (typeof f === "string" ? f : ((f as Obj)?.title as string) ?? "")).filter(Boolean).join("\n")
    : "";

const keywordsToText = (v: unknown): string =>
  Array.isArray(v) ? v.join(", ") : typeof v === "string" ? v : "";

export function ProductForm({ value, onChange }: { value: string; onChange: (json: string) => void }) {
  const data = parseObj(value);
  const [showJson, setShowJson] = useState(false);
  const emit = (patch: Obj) => onChange(JSON.stringify({ ...data, ...patch }, null, 2));
  const s = (k: string) => (data[k] == null ? "" : String(data[k]));

  const fieldCls =
    "w-full border border-[#E5E7EB] rounded-lg px-3 py-2 text-sm text-[#111827] focus:outline-none focus:ring-1 focus:ring-[#16A34A]";
  const labelCls = "text-xs font-semibold text-[#374151] mb-1 block";

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-3">
        <div className="col-span-2">
          <label className={labelCls}>상품명 <span className="text-[#DC2626]">*</span></label>
          <input className={fieldCls} value={s("name")} onChange={(e) => emit({ name: e.target.value })}
            placeholder="예: LED 슬림 T5 간접조명 1200mm" />
        </div>
        <div>
          <label className={labelCls}>판매가 (원) <span className="text-[#DC2626]">*</span></label>
          <input type="number" className={fieldCls} value={s("price")}
            onChange={(e) => emit({ price: Number(e.target.value) || 0 })} placeholder="29800" />
        </div>
        <div>
          <label className={labelCls}>재고 (개) <span className="text-[#DC2626]">*</span></label>
          <input type="number" className={fieldCls} value={s("stock")}
            onChange={(e) => emit({ stock: Number(e.target.value) || 0 })} placeholder="100" />
        </div>
        <div>
          <label className={labelCls}>카테고리</label>
          <input className={fieldCls} value={s("category")} onChange={(e) => emit({ category: e.target.value })}
            placeholder="예: 생활/주방 &gt; 조명" />
        </div>
        <div>
          <label className={labelCls}>브랜드</label>
          <input className={fieldCls} value={s("brand")} onChange={(e) => emit({ brand: e.target.value })}
            placeholder="브랜드명 (선택)" />
        </div>
        <div>
          <label className={labelCls}>원산지</label>
          <input className={fieldCls} value={s("origin")} onChange={(e) => emit({ origin: e.target.value })}
            placeholder="예: 국산 / 중국 (선택)" />
        </div>
        <div>
          <label className={labelCls}>모델명</label>
          <input className={fieldCls} value={s("model_name")} onChange={(e) => emit({ model_name: e.target.value })}
            placeholder="모델명 (선택)" />
        </div>
      </div>

      <div>
        <label className={labelCls}>핵심 특징</label>
        <textarea rows={3} className={fieldCls} value={featuresToText(data.features)}
          onChange={(e) => emit({ features: e.target.value.split("\n").map((t) => t.trim()).filter(Boolean) })}
          placeholder={"아는 특징만 한 줄에 하나씩\n예) 초슬림 7mm\n예) 눈부심 없는 확산커버"} />
        <p className="text-[11px] text-[#16A34A] mt-1 leading-relaxed">
          💡 아는 것만 적으세요 — AI가 카피로 다듬고, 📷 사진을 넣으면 사진에서 색상·소재·디자인 특징을 자동으로 뽑아 보완합니다.
          모르는 항목은 비워두면 지어내지 않고 “확인 중”으로 표시합니다 (허위광고 방지).
        </p>
      </div>

      <div>
        <label className={labelCls}>키워드</label>
        <input className={fieldCls} value={keywordsToText(data.keywords)}
          onChange={(e) => emit({ keywords: e.target.value.split(",").map((t) => t.trim()).filter(Boolean) })}
          placeholder="검색 키워드, 쉼표로 구분 (예: 간접조명, LED바, 무드등)" />
      </div>

      <button type="button" onClick={() => setShowJson((v) => !v)}
        className="text-[11px] text-[#9CA3AF] hover:text-[#6B7280]">
        {showJson ? "▲ 고급: 직접 편집(JSON) 닫기" : "⚙️ 고급: 직접 편집(JSON)"}
      </button>
      {showJson && (
        <textarea rows={8} value={value} onChange={(e) => onChange(e.target.value)}
          className="w-full border border-[#E5E7EB] rounded-lg p-2 text-xs font-mono text-[#374151] focus:outline-none focus:ring-1 focus:ring-[#16A34A]" />
      )}
    </div>
  );
}
