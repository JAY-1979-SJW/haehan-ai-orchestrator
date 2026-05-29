/**
 * 스마트스토어 AI 에이전트 도구 정의 — 단일 소스 (MCP·Chat 공용)
 * Claude(Anthropic SDK) / GPT(OpenAI SDK) 양쪽 형식으로 변환해 export합니다.
 */
import type Anthropic from "@anthropic-ai/sdk";
import type OpenAI    from "openai";

// ── 쓰기 도구 (승인 필요) ────────────────────────────────────────────────────
export const WRITE_TOOL_NAMES = new Set(["auto_register_product", "edit_product"]);

// ── 공통 도구 정의 ────────────────────────────────────────────────────────────
interface ToolDef {
  name:        string;
  description: string;
  params:      Record<string, unknown>;
  required?:   string[];
}

export const TOOL_DEFS: ToolDef[] = [
  { name: "list_products",       description: "스마트스토어 상품 목록을 캐시에서 조회합니다.", params: {} },
  { name: "collect_products",    description: "CDP로 상품 목록을 실시간 수집합니다.",
    params: { limit: { type: "integer", description: "수집 최대 개수 (기본 50)" } } },
  { name: "list_orders",         description: "주문 목록을 캐시에서 조회합니다.", params: {} },
  { name: "collect_orders",      description: "CDP로 주문 목록을 실시간 수집합니다.",
    params: { limit: { type: "integer" } } },
  { name: "list_settlements",    description: "정산 내역을 캐시에서 조회합니다.", params: {} },
  { name: "collect_settlements", description: "CDP로 정산 내역을 실시간 수집합니다.",
    params: { limit: { type: "integer" } } },
  { name: "list_reviews",        description: "리뷰·문의 목록을 캐시에서 조회합니다.", params: {} },
  { name: "collect_reviews",     description: "CDP로 리뷰·문의를 실시간 수집합니다.",
    params: { limit: { type: "integer" } } },
  { name: "list_stats",          description: "데이터 분석(통계)을 캐시에서 조회합니다.", params: {} },
  { name: "collect_stats",       description: "CDP로 데이터 분석(통계)을 실시간 수집합니다.", params: {} },
  { name: "open_seller_center",  description: "CDP 브라우저를 셀러센터 지정 페이지로 이동합니다.",
    params: {
      page_key: { type: "string",
        enum: ["dashboard", "list", "register", "orders", "settlement", "reviews", "stats"],
        description: "이동할 페이지 (기본: dashboard)" },
    } },
  { name: "auto_register_product",
    description: "CDP로 상품 등록 폼을 자동으로 채웁니다 (임시저장까지). 쓰기 작업.",
    params: {
      name:        { type: "string",  description: "상품명" },
      price:       { type: "integer", description: "판매가 (원)" },
      stock:       { type: "integer", description: "재고 수량" },
      category:    { type: "string",  description: "카테고리 경로" },
      brand:       { type: "string",  description: "브랜드명" },
      keywords:    { type: "array", items: { type: "string" }, description: "검색 키워드" },
      description: { type: "string",  description: "상세설명 HTML" },
      model_name:  { type: "string",  description: "모델명" },
      origin:      { type: "string",  description: "원산지" },
    },
    required: ["name", "price", "stock"] },
  { name: "edit_product",
    description: "CDP로 기존 상품을 수정합니다 (임시저장까지). 쓰기 작업.",
    params: {
      product_id:  { type: "string",  description: "수정할 상품번호" },
      name:        { type: "string",  description: "변경할 상품명" },
      price:       { type: "integer", description: "변경할 판매가" },
      stock:       { type: "integer", description: "변경할 재고" },
      description: { type: "string",  description: "변경할 상세설명 HTML" },
      keywords:    { type: "array", items: { type: "string" }, description: "변경할 키워드" },
      brand:       { type: "string",  description: "변경할 브랜드명" },
      origin:      { type: "string",  description: "변경할 원산지" },
    },
    required: ["product_id"] },
  { name: "generate_description",
    description: "Claude 또는 GPT로 상품 상세설명 HTML을 생성합니다.",
    params: {
      data:  { type: "object", description: "상품 데이터" },
      model: { type: "string", enum: ["claude", "gpt"], description: "생성 모델" },
    },
    required: ["data"] },
  { name: "search_categories",
    description: "카테고리 이름·경로를 검색합니다.",
    params: { q: { type: "string", description: "검색어 (예: 무드등, 조명)" } },
    required: ["q"] },
  { name: "popup_handle", description: "CDP 브라우저 팝업을 자동으로 닫습니다.", params: {} },
];

// ── Claude 형식 변환 ──────────────────────────────────────────────────────────
export function toClaudeTools(defs: ToolDef[] = TOOL_DEFS): Anthropic.Tool[] {
  return defs.map((t) => {
    const schema: Anthropic.Tool["input_schema"] = { type: "object", properties: t.params };
    if (t.required) (schema as Record<string, unknown>).required = t.required;
    return { name: t.name, description: t.description, input_schema: schema };
  });
}

// ── GPT 형식 변환 ─────────────────────────────────────────────────────────────
export function toGptTools(defs: ToolDef[] = TOOL_DEFS): OpenAI.Chat.ChatCompletionTool[] {
  return defs.map((t) => {
    const params: Record<string, unknown> = { type: "object", properties: t.params };
    if (t.required) params.required = t.required;
    return { type: "function" as const, function: { name: t.name, description: t.description, parameters: params } };
  });
}

// ── 쓰기 도구 필터링 헬퍼 ────────────────────────────────────────────────────
export function filterWriteTools<T extends { name?: string; function?: { name?: string } }>(
  tools: T[],
  confirmed: boolean,
): T[] {
  if (confirmed) return tools;
  return tools.filter((t) => {
    const name = t.name ?? t.function?.name ?? "";
    return !WRITE_TOOL_NAMES.has(name);
  });
}
