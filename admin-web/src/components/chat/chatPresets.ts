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
  blog: [
    { label: "주제로 글 작성", prompt: "다음 주제로 네이버 블로그 글을 작성해줘: " },
    { label: "글 작성→임시저장", prompt: "다음 주제로 네이버 블로그 글을 써서 임시저장해줘: " },
    { label: "SEO 분석",       prompt: "방금 작성한 블로그 글의 SEO를 분석해줘" },
    { label: "초안 목록",      prompt: "저장된 블로그 초안 목록을 보여줘" },
    { label: "블로그 현황",    prompt: "네이버 블로그 현황을 확인해줘" },
  ],
  naver: [
    { label: "세션 상태",   prompt: "네이버 로그인 세션 상태를 확인해줘" },
    { label: "로그인",      prompt: "네이버 로그인을 실행해줘" },
    { label: "키워드 검색", prompt: "스마트스토어 관련 키워드를 검색해줘" },
    { label: "블로그 현황", prompt: "네이버 블로그 현황을 확인해줘" },
  ],
  ops: [
    { label: "서버 상태",   prompt: "서버 상태를 확인해줘" },
    { label: "감사 로그",   prompt: "최근 감사 로그를 보여줘" },
    { label: "승인 대기",   prompt: "승인 대기 중인 항목을 확인해줘" },
    { label: "에이전트 상태", prompt: "로컬 에이전트 상태를 확인해줘" },
  ],
  inbox: [
    { label: "새 메일",     prompt: "새 메일을 확인해줘" },
    { label: "메일 요약",   prompt: "받은 메일을 요약해줘" },
    { label: "메일 작성",   prompt: "메일 초안을 작성해줘" },
    { label: "뉴스 수집",   prompt: "오늘 주요 뉴스를 수집해줘" },
  ],
  cad: [
    { label: "도면 목록",   prompt: "현재 도면 파일 목록을 보여줘" },
    { label: "물량 추출",   prompt: "도면에서 물량을 추출해줘" },
    { label: "블록 분석",   prompt: "도면 블록 정보를 분석해줘" },
    { label: "텍스트 검색", prompt: "도면에서 텍스트를 검색해줘" },
  ],
  "file-map": [
    { label: "파일 스캔",   prompt: "로컬 파일 지도를 스캔해줘" },
    { label: "정리 계획",   prompt: "파일 정리 계획을 세워줘" },
    { label: "중복 파일",   prompt: "중복 파일을 찾아줘" },
  ],
  market: [
    { label: "시장 분석",   prompt: "키워드 시장 분석을 실행해줘" },
    { label: "경쟁사 조사", prompt: "경쟁사 상품을 조사해줘" },
    { label: "트렌드",      prompt: "최근 트렌드 키워드를 분석해줘" },
  ],
  default: [
    { label: "도움말",      prompt: "이 페이지에서 무엇을 할 수 있어?" },
    { label: "상태 확인",   prompt: "현재 시스템 상태를 확인해줘" },
    { label: "최근 작업",   prompt: "최근 작업 내역을 보여줘" },
  ],
};
