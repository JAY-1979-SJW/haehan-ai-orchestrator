export interface ChatChip {
  label: string;
  prompt: string;
}

export const CHAT_PRESETS: Record<string, ChatChip[]> = {
  smartstore: [
    { label: "상품 목록",   prompt: "상품 목록을 보여줘" },
    { label: "주문 확인",   prompt: "최근 주문 목록을 확인해줘" },
    { label: "정산 조회",   prompt: "정산 내역을 조회해줘" },
    { label: "리뷰 확인",   prompt: "최근 리뷰와 문의를 확인해줘" },
    { label: "매출 통계",   prompt: "최근 매출 통계를 보여줘" },
  ],
  youtube: [
    { label: "채널 상태",   prompt: "YouTube 채널 상태를 확인해줘" },
    { label: "OAuth 확인",  prompt: "YouTube OAuth 토큰 상태를 확인해줘" },
    { label: "댓글 수집",   prompt: "최근 영상 댓글을 수집해줘" },
    { label: "시장 조사",   prompt: "스마트스토어 관련 YouTube 시장 조사를 실행해줘" },
  ],
  google: [
    { label: "Gmail 확인",  prompt: "Gmail 받은편지함 상태를 확인해줘" },
    { label: "Drive 파일",  prompt: "Google Drive 최근 파일을 보여줘" },
    { label: "캘린더 일정", prompt: "오늘 Google 캘린더 일정을 확인해줘" },
    { label: "GCP 상태",    prompt: "GCP 프로젝트 상태를 확인해줘" },
  ],
  cafe: [
    { label: "글 쓰기",        prompt: "https://cafe.naver.com/0moo 기업홍보/기업자료 게시판에 다음 내용으로 글을 써줘: " },
    { label: "글 발행",        prompt: "https://cafe.naver.com/0moo 기업홍보/기업자료 게시판에 다음 내용으로 글을 발행해줘 (confirmed=true): " },
    { label: "글 수집",        prompt: "건설공무 카페(https://cafe.naver.com/0moo) 최근 90일 글을 수집해줘" },
    { label: "키워드 필터",    prompt: "수집된 카페 글에서 다음 키워드로 필터링해줘: " },
    { label: "수집 현황",      prompt: "카페 수집 현황을 보여줘" },
    { label: "내 카페 목록",   prompt: "내가 가입한 카페 목록을 보여줘" },
  ],
  blog: [
    { label: "초안 작성",      prompt: "다음 주제로 네이버 블로그 글 초안을 AI로 생성해줘: " },
    { label: "임시저장",       prompt: "다음 내용으로 네이버 블로그에 임시저장해줘 — 제목: , 본문: , 태그: " },
    { label: "발행",           prompt: "다음 내용으로 네이버 블로그에 발행해줘 (confirmed=true) — 제목: , 본문: " },
    { label: "초안 목록",      prompt: "저장된 블로그 초안 목록을 보여줘" },
    { label: "SEO 분석",       prompt: "방금 작성한 블로그 글의 SEO를 분석해줘" },
  ],
  naver: [
    { label: "세션 상태",      prompt: "네이버 로그인 세션 상태를 확인해줘" },
    { label: "카페 글 수집",   prompt: "건설공무 카페(https://cafe.naver.com/0moo) 최근 글을 수집해줘" },
    { label: "블로그 글 작성", prompt: "다음 주제로 네이버 블로그 글을 작성해줘: " },
    { label: "키워드 검색",    prompt: "스마트스토어 관련 키워드를 검색해줘" },
  ],
  ops: [
    { label: "서버 상태",     prompt: "서버 상태를 확인해줘" },
    { label: "감사 로그",     prompt: "최근 감사 로그를 보여줘" },
    { label: "승인 대기",     prompt: "승인 대기 중인 항목을 확인해줘" },
    { label: "에이전트 상태", prompt: "로컬 에이전트 상태를 확인해줘" },
  ],
  inbox: [
    { label: "새 메일",   prompt: "새 메일을 확인해줘" },
    { label: "메일 요약", prompt: "받은 메일을 요약해줘" },
    { label: "메일 작성", prompt: "메일 초안을 작성해줘" },
    { label: "뉴스 수집", prompt: "오늘 주요 뉴스를 수집해줘" },
  ],
  cad: [
    { label: "도면 목록",   prompt: "현재 도면 파일 목록을 보여줘" },
    { label: "물량 추출",   prompt: "도면에서 물량을 추출해줘" },
    { label: "블록 분석",   prompt: "도면 블록 정보를 분석해줘" },
    { label: "텍스트 검색", prompt: "도면에서 텍스트를 검색해줘" },
  ],
  "file-map": [
    { label: "파일 스캔", prompt: "로컬 파일 지도를 스캔해줘" },
    { label: "정리 계획", prompt: "파일 정리 계획을 세워줘" },
    { label: "중복 파일", prompt: "중복 파일을 찾아줘" },
  ],
  market: [
    { label: "시장 분석",   prompt: "키워드 시장 분석을 실행해줘" },
    { label: "경쟁사 조사", prompt: "경쟁사 상품을 조사해줘" },
    { label: "트렌드",      prompt: "최근 트렌드 키워드를 분석해줘" },
  ],
  default: [
    { label: "카페 목록",   prompt: "내가 가입한 카페 목록을 보여줘" },
    { label: "세션 확인",   prompt: "네이버 로그인 세션 상태를 확인해줘" },
    { label: "스마트스토어 주문", prompt: "최근 스마트스토어 주문 목록을 확인해줘" },
    { label: "뉴스 검색",   prompt: "오늘 건설·소방·전기 관련 뉴스를 수집해줘" },
    { label: "서버 상태",   prompt: "서버 상태를 확인해줘" },
  ],
};

// ── B. 응답 후 후속 액션 패턴 ─────────────────────────────────────────────────
// AI 응답 텍스트에 키워드가 포함될 때 아래에 표시할 후속 버튼 목록

export interface ActionPattern {
  pattern: RegExp;
  actions: ChatChip[];
}

export const ACTION_PATTERNS: ActionPattern[] = [
  {
    // 카페 수집 완료 후 → 키워드 필터·엑셀·AI 분석
    pattern: /수집\s*(완료|저장|건)|collected|raw_articles/i,
    actions: [
      { label: "키워드 필터",  prompt: "수집된 카페 글에서 적산, 산출, 내역서, 단가 키워드로 필터링해줘" },
      { label: "엑셀 저장",    prompt: "필터링된 카페 글을 기간별 시트로 엑셀 파일에 저장해줘" },
      { label: "AI 분석",      prompt: "수집된 카페 글을 AI로 분석해줘" },
    ],
  },
  {
    // 엑셀 저장 완료 후 → 파일 열기·추가 키워드
    pattern: /\.xlsx|엑셀.*저장|저장.*엑셀/i,
    actions: [
      { label: "파일 열기",       prompt: "저장된 엑셀 파일을 열어줘" },
      { label: "다른 키워드 필터", prompt: "다른 키워드로 다시 필터링해줘: " },
      { label: "AI 분석",          prompt: "수집된 카페 글을 AI로 분석해줘" },
    ],
  },
  {
    // 블로그 초안 생성 완료 후 → 임시저장·발행·SEO
    pattern: /초안|draft|블로그.*작성|본문.*작성/i,
    actions: [
      { label: "임시저장",  prompt: "작성한 블로그 초안을 네이버 블로그에 임시저장해줘" },
      { label: "발행",      prompt: "임시저장된 블로그 초안을 실제 발행해줘" },
      { label: "SEO 분석",  prompt: "방금 작성한 블로그 글의 SEO를 분석해줘" },
    ],
  },
  {
    // 블로그 임시저장 완료 후 → 발행·수정
    pattern: /임시저장\s*(완료|됨)|save_draft/i,
    actions: [
      { label: "발행",      prompt: "임시저장된 블로그 초안을 실제 발행해줘" },
      { label: "SEO 분석",  prompt: "방금 작성한 블로그 글의 SEO를 분석해줘" },
      { label: "초안 목록", prompt: "저장된 블로그 초안 목록을 보여줘" },
    ],
  },
  {
    pattern: /카페|cafe/i,
    actions: [
      { label: "글 수집",        prompt: "건설공무 카페(https://cafe.naver.com/0moo) 최근 글을 수집해줘" },
      { label: "키워드 필터",    prompt: "수집된 카페 글에서 키워드로 필터링해줘: " },
      { label: "AI 분석",        prompt: "수집된 카페 글을 AI로 분석해줘" },
    ],
  },
  {
    pattern: /주문|order/i,
    actions: [
      { label: "미발송 확인", prompt: "미발송 주문을 확인해줘" },
      { label: "취소·반품",  prompt: "취소·반품 현황을 조회해줘" },
      { label: "배송 현황",  prompt: "발송 완료 주문의 배송 현황을 확인해줘" },
    ],
  },
  {
    pattern: /상품|product/i,
    actions: [
      { label: "판매 현황", prompt: "상품별 판매 현황을 보여줘" },
      { label: "재고 확인", prompt: "재고가 부족한 상품을 확인해줘" },
      { label: "상품 등록", prompt: "새 상품을 등록하고 싶어" },
    ],
  },
  {
    pattern: /정산|settlement/i,
    actions: [
      { label: "이번 달 정산", prompt: "이번 달 정산 예정액을 알려줘" },
      { label: "매출 통계",   prompt: "최근 월별 매출 통계를 보여줘" },
    ],
  },
  {
    pattern: /세션|로그인|login|session/i,
    actions: [
      { label: "네이버 재로그인", prompt: "네이버 로그인 페이지를 열어줘" },
      { label: "스토어 세션",    prompt: "스마트스토어 셀러센터 세션을 확인해줘" },
    ],
  },
  {
    pattern: /뉴스|news/i,
    actions: [
      { label: "더 수집",     prompt: "뉴스를 더 수집해줘" },
      { label: "키워드 분석", prompt: "수집한 뉴스에서 주요 키워드를 분석해줘" },
      { label: "요약",        prompt: "수집한 뉴스를 3줄로 요약해줘" },
    ],
  },
  {
    pattern: /키워드|keyword/i,
    actions: [
      { label: "블로그 글 작성", prompt: "이 키워드로 블로그 글을 작성해줘" },
      { label: "경쟁 분석",     prompt: "이 키워드의 경쟁 강도를 분석해줘" },
      { label: "추가 키워드",   prompt: "관련 키워드를 더 추천해줘" },
    ],
  },
  {
    pattern: /리뷰|review|문의/i,
    actions: [
      { label: "답변 초안",   prompt: "리뷰·문의 답변 초안을 작성해줘" },
      { label: "부정 리뷰",   prompt: "부정적인 리뷰만 모아서 보여줘" },
    ],
  },
  {
    pattern: /서버|server|상태|health/i,
    actions: [
      { label: "로그 확인",     prompt: "최근 서버 에러 로그를 확인해줘" },
      { label: "에이전트 상태", prompt: "로컬 에이전트 상태를 확인해줘" },
    ],
  },
];

/** AI 응답 텍스트에서 후속 액션 버튼을 추출한다. */
export function detectActions(text: string): ChatChip[] {
  if (!text || text.length < 20) return [];
  for (const ap of ACTION_PATTERNS) {
    if (ap.pattern.test(text)) return ap.actions;
  }
  return [];
}
