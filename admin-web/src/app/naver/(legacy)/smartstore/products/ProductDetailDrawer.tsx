"use client";
/**
 * ProductDetailDrawer — 상품 상세 우측 슬라이드 패널
 * 행 클릭 → 캐시 즉시 표시 → 백그라운드 CDP 새로고침
 */
import { useState, useEffect, useCallback } from "react";
import {
  getSSProductDetail,
  collectSSProductDetail,
  type ProductDetail,
  type ProductDetailResponse,
} from "@/lib/assistant/api";

interface Props {
  productId: string | null;
  onClose: () => void;
}

const STATUS_STYLE: Record<string, string> = {
  SALE:        "bg-green-100 text-green-700 border-green-200",
  OUTOFSTOCK:  "bg-yellow-100 text-yellow-700 border-yellow-200",
  SUSPENSION:  "bg-red-100 text-red-700 border-red-200",
  CLOSE:       "bg-gray-100 text-gray-500 border-gray-200",
};
const STATUS_LABEL: Record<string, string> = {
  SALE: "판매중", OUTOFSTOCK: "품절", SUSPENSION: "판매중지", CLOSE: "숨김",
};

function fmt(n?: number | null) {
  if (n == null) return "—";
  return n.toLocaleString("ko-KR");
}

function fmtDate(iso?: string | null) {
  if (!iso) return "—";
  try { return new Date(iso).toLocaleString("ko-KR", { timeZone: "Asia/Seoul" }); }
  catch { return iso; }
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex justify-between items-center py-1.5 border-b border-[#F3F4F6] last:border-0">
      <span className="text-xs text-[#6B7280] shrink-0 w-24">{label}</span>
      <span className="text-xs text-[#111827] text-right">{value ?? "—"}</span>
    </div>
  );
}

export default function ProductDetailDrawer({ productId, onClose }: Props) {
  const [product, setProduct]   = useState<ProductDetail | null>(null);
  const [source, setSource]     = useState<string | null>(null);
  const [loading, setLoading]   = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError]       = useState<string | null>(null);
  const [tab, setTab]           = useState<"info" | "options" | "stats">("info");
  const [liveToast, setLiveToast] = useState(false);

  const load = useCallback(async (id: string) => {
    setLoading(true);
    setError(null);
    setProduct(null);
    try {
      // 1. 캐시 즉시 표시
      const cached: ProductDetailResponse = await getSSProductDetail(id, false);
      if (cached.ok && cached.product) {
        setProduct(cached.product);
        setSource("cache");
      }

      // 2. 백그라운드 CDP 새로고침
      setRefreshing(true);
      const live: ProductDetailResponse = await getSSProductDetail(id, true);
      if (live.ok && live.product) {
        setProduct(live.product);
        setSource("cdp");
        setLiveToast(true);
        setTimeout(() => setLiveToast(false), 2500);
      } else if (!cached.ok) {
        setError(live.error ?? "수집 실패");
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    if (productId) {
      setTab("info");
      load(productId);
    }
  }, [productId, load]);

  const handleManualCollect = async () => {
    if (!productId || refreshing) return;
    setRefreshing(true);
    try {
      const res = await collectSSProductDetail(productId);
      if (res.ok && res.product) {
        setProduct(res.product);
        setSource("cdp");
        setLiveToast(true);
        setTimeout(() => setLiveToast(false), 2500);
      } else {
        setError(res.error ?? "수집 실패");
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setRefreshing(false);
    }
  };

  if (!productId) return null;

  const status = product?.status ?? "UNKNOWN";
  const statusStyle = STATUS_STYLE[status] ?? "bg-gray-100 text-gray-500 border-gray-200";
  const statusLabel = STATUS_LABEL[status] ?? status;

  return (
    <>
      {/* 오버레이 */}
      <div
        className="fixed inset-0 bg-black/20 z-40"
        onClick={onClose}
      />

      {/* 드로어 패널 */}
      <div className="fixed right-0 top-0 h-full w-[420px] max-w-full bg-white shadow-2xl z-50 flex flex-col">

        {/* 헤더 */}
        <div className="flex items-start justify-between p-4 border-b border-[#E5E7EB] shrink-0">
          <div className="flex-1 min-w-0">
            {product?.name
              ? <h2 className="text-sm font-semibold text-[#111827] truncate">{product.name}</h2>
              : <h2 className="text-sm font-semibold text-[#9CA3AF]">{loading ? "로딩 중…" : "상품 상세"}</h2>}
            <p className="text-xs text-[#9CA3AF] mt-0.5">#{productId}</p>
          </div>
          <div className="flex items-center gap-2 ml-3 shrink-0">
            {product && (
              <span className={`text-xs px-2 py-0.5 rounded-full border font-medium ${statusStyle}`}>
                {statusLabel}
              </span>
            )}
            <button onClick={onClose} className="text-[#9CA3AF] hover:text-[#111827] text-lg leading-none">✕</button>
          </div>
        </div>

        {/* 라이브 갱신 토스트 */}
        {liveToast && (
          <div className="mx-4 mt-3 px-3 py-2 bg-green-50 border border-green-200 rounded-lg text-xs text-green-700 text-center shrink-0">
            실시간 갱신됨 ✓
          </div>
        )}

        {/* 로딩 */}
        {loading && !product && (
          <div className="flex-1 flex items-center justify-center">
            <p className="text-sm text-[#9CA3AF]">데이터 수집 중…</p>
          </div>
        )}

        {/* 에러 */}
        {error && !product && (
          <div className="m-4 p-4 bg-red-50 border border-red-200 rounded-xl space-y-3">
            <p className="text-sm text-red-600">{error}</p>
            <div className="flex gap-2">
              <button
                onClick={handleManualCollect}
                disabled={refreshing}
                className="text-xs px-3 py-1.5 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50"
              >
                재시도
              </button>
              <a
                href={`https://sell.smartstore.naver.com/#/products/${productId}/edit`}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs px-3 py-1.5 border border-[#E5E7EB] rounded-lg hover:bg-[#F9FAFB]"
              >
                셀러센터 바로가기
              </a>
            </div>
          </div>
        )}

        {/* 본문 */}
        {product && (
          <div className="flex-1 overflow-y-auto flex flex-col">

            {/* 대표 이미지 */}
            {product.main_image_url && (
              <div className="px-4 pt-4 shrink-0">
                <img
                  src={product.main_image_url}
                  alt={product.name ?? "상품 이미지"}
                  className="w-full h-48 object-contain rounded-xl border border-[#E5E7EB] bg-[#F9FAFB]"
                />
              </div>
            )}

            {/* 탭 */}
            <div className="flex gap-1 px-4 pt-3 border-b border-[#E5E7EB] shrink-0">
              {(["info", "options", "stats"] as const).map((t) => (
                <button
                  key={t}
                  onClick={() => setTab(t)}
                  className={`text-xs px-3 py-1.5 -mb-px border-b-2 transition-colors ${
                    tab === t
                      ? "border-[#F97316] text-[#F97316] font-semibold"
                      : "border-transparent text-[#6B7280] hover:text-[#111827]"
                  }`}
                >
                  {{ info: "기본정보", options: "옵션", stats: "통계" }[t]}
                </button>
              ))}
            </div>

            <div className="p-4 space-y-1 flex-1">

              {/* 기본정보 탭 */}
              {tab === "info" && (
                <div className="space-y-1">
                  <Row label="상품명"     value={product.name} />
                  <Row label="카테고리"   value={product.category} />
                  <Row label="판매가"     value={product.price != null ? `${fmt(product.price)}원` : undefined} />
                  <Row label="정가"       value={product.original_price != null ? `${fmt(product.original_price)}원` : undefined} />
                  <Row label="재고"       value={product.stock != null ? `${fmt(product.stock)}개` : undefined} />
                  <Row label="최소 구매"  value={product.min_purchase != null ? `${product.min_purchase}개` : undefined} />
                  <Row label="최대 구매"  value={product.max_purchase != null ? `${product.max_purchase}개` : undefined} />
                  <Row label="배송비"     value={product.delivery_fee === 0 ? "무료" : product.delivery_fee != null ? `${fmt(product.delivery_fee)}원` : undefined} />
                  <Row label="수집 시각"  value={fmtDate(product.collected_at)} />
                  <Row label="출처"       value={source === "cdp" ? "실시간 CDP" : "캐시"} />
                  {product._missing_fields && product._missing_fields.length > 0 && (
                    <div className="mt-2 p-2 bg-yellow-50 border border-yellow-200 rounded-lg text-xs text-yellow-700">
                      누락 필드: {product._missing_fields.join(", ")}
                    </div>
                  )}
                </div>
              )}

              {/* 옵션 탭 */}
              {tab === "options" && (
                product.has_options && product.options && product.options.length > 0
                  ? (
                    <div className="overflow-x-auto">
                      <table className="w-full text-xs">
                        <thead className="bg-[#F9FAFB] border-b border-[#E5E7EB]">
                          <tr>
                            {["옵션명", "옵션값", "추가가격", "재고"].map(h => (
                              <th key={h} className="text-left px-2 py-2 text-[#6B7280] font-semibold">{h}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {product.options.map((opt, i) => (
                            <tr key={i} className={i % 2 === 0 ? "bg-white" : "bg-[#F9FAFB]"}>
                              <td className="px-2 py-1.5 text-[#374151]">{opt.option_name}</td>
                              <td className="px-2 py-1.5 text-[#374151]">{opt.option_value}</td>
                              <td className="px-2 py-1.5 text-[#374151]">{opt.price_diff ? `+${fmt(opt.price_diff)}원` : "—"}</td>
                              <td className="px-2 py-1.5 text-[#374151]">{fmt(opt.stock)}개</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <p className="text-sm text-[#9CA3AF] text-center py-8">옵션 없음</p>
                  )
              )}

              {/* 통계 탭 */}
              {tab === "stats" && (
                <div className="space-y-1">
                  <Row label="조회수"   value={fmt(product.view_count)} />
                  <Row label="주문수"   value={fmt(product.order_count)} />
                  <Row label="리뷰 수"  value={fmt(product.review_count)} />
                  <Row label="리뷰 점수" value={product.review_score != null ? `${product.review_score}점` : undefined} />
                </div>
              )}
            </div>
          </div>
        )}

        {/* 푸터 */}
        <div className="p-4 border-t border-[#E5E7EB] flex items-center justify-between shrink-0">
          <button
            onClick={handleManualCollect}
            disabled={refreshing}
            className="text-xs px-3 py-1.5 border border-[#E5E7EB] rounded-lg hover:bg-[#F9FAFB] disabled:opacity-50 transition-colors"
          >
            {refreshing ? "수집 중…" : "실시간 수집"}
          </button>
          <a
            href={`https://sell.smartstore.naver.com/#/products/${productId}/edit`}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs px-3 py-1.5 bg-[#F97316] text-white rounded-lg hover:bg-[#EA6D0E] transition-colors font-semibold"
          >
            셀러센터에서 편집 →
          </a>
        </div>
      </div>
    </>
  );
}
