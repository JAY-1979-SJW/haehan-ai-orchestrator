/** 가비아 — 빠른버튼·칩·도구라벨 데이터 */

export const QUICK_ACTIONS = [
  {
    label: "업무 현황 조회",
    icon: "📋",
    prompt: "가비아 업무 현황을 보여줘",
    desc: "게이트 정책 + 가능 작업 목록",
    color: "#1D4ED8",
    bg: "#EFF6FF",
    border: "#BFDBFE",
  },
  {
    label: "로그인 감지 시작",
    icon: "🔐",
    prompt: "가비아 로그인 감지를 시작해줘",
    desc: "브라우저에서 로그인 후 DNS 화면 자동 이동",
    color: "#16A34A",
    bg: "#F0FDF4",
    border: "#BBF7D0",
  },
  {
    label: "DNS 화면 열기",
    icon: "🌐",
    prompt: "가비아 DNS 관리 화면을 열어줘",
    desc: "CDP 브라우저로 DNS 관리 화면 이동",
    color: "#7C3AED",
    bg: "#F5F3FF",
    border: "#DDD6FE",
  },
  {
    label: "업무 흐름 확인",
    icon: "📌",
    prompt: "DNS 작업 브라우저 단계별 흐름을 보여줘",
    desc: "8단계 자동화 계획 확인",
    color: "#374151",
    bg: "#F9FAFB",
    border: "#E5E7EB",
  },
  {
    label: "DNS 초안 작성",
    icon: "✏️",
    prompt: null, // 입력 모달 필요
    desc: "서브도메인 + IP 입력 → 초안 생성",
    color: "#F97316",
    bg: "#FFF7ED",
    border: "#FED7AA",
  },
];

export const CHIPS = [
  { label: "업무 현황",       prompt: "가비아 업무 현황을 보여줘" },
  { label: "로그인 감지 시작", prompt: "가비아 로그인 감지를 시작해줘" },
  { label: "DNS 업무 목록",   prompt: "DNS 업무 레지스트리 목록을 보여줘" },
  { label: "업무 흐름",       prompt: "DNS 작업 브라우저 단계별 흐름을 보여줘" },
  { label: "DNS 초안 작성",   prompt: "autowork 서브도메인 A 레코드 초안을 작성해줘" },
  { label: "DNS 화면 열기",   prompt: "가비아 DNS 관리 화면을 열어줘" },
];

export const TOOL_LABEL: Record<string, string> = {
  get_status:         "업무 현황 조회",
  start_login_watch:  "로그인 감지 시작",
  get_dns_tasks:      "DNS 업무 목록 조회",
  get_nav_plan:       "네비게이션 계획 조회",
  prepare_dns_record: "DNS 레코드 초안 작성",
  open_gabia_dns:     "DNS 관리 화면 열기",
};

export type Msg =
  | { role: "user"; text: string }
  | { role: "ai"; blocks: AiBlock[] };

export type AiBlock =
  | { type: "text"; text: string }
  | { type: "step"; tool: string; status: "running" | "ok" | "fail"; detail?: string }
  | { type: "done"; steps: number }
  | { type: "error"; message: string };

