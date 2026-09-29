export interface NavItem {
  key: string;
  label: string;
  shortLabel: string;
  href: string;
  exact?: boolean;
  adminOnly?: boolean; // owner/admin만 표시
}

export type NavGroup = {
  group: string;
  items: NavItem[];
  adminOnly?: boolean;
};

// 채팅 중심 UI — 좌측 nav는 보고/확인용만. 세부 기능은 채팅으로 요청.
export const NAV_GROUPS: NavGroup[] = [
  {
    group: "홈",
    items: [
      { key: "home", label: "AI 콘솔", shortLabel: "AI", href: "/", exact: true },
      { key: "ops",  label: "운영센터", shortLabel: "운영", href: "/ops" },
      { key: "mail", label: "메일 비서", shortLabel: "메일", href: "/mail" },
      { key: "google", label: "구글 허브", shortLabel: "구글", href: "/google" },
      { key: "login-status", label: "로그인 현황", shortLabel: "로그인", href: "/login-status" },
      { key: "mypage", label: "설정", shortLabel: "설정", href: "/mypage" },
    ],
  },
  {
    group: "스마트스토어",
    items: [
      { key: "ss-home", label: "스토어 AI 채팅", shortLabel: "스토어", href: "/naver/smartstore" },
    ],
  },
  {
    group: "콘텐츠",
    items: [
      { key: "blog", label: "블로그 AI", shortLabel: "블로그", href: "/naver/blog" },
      // "마케팅 자료"(/marketing) 항목 임시 제거 — 페이지 미구현으로 클릭 시 404
      // (2026-09-30, docs/defect_index.json #104). 프론트/백엔드 모두 없음.
      // 복원 시 실제 페이지 신설 후 href 되살릴 것.
    ],
  },
  {
    group: "업무 현황",
    items: [
      { key: "tasks",    label: "작업 목록",   shortLabel: "작업", href: "/assistant/tasks" },
      { key: "approval", label: "승인 게이트", shortLabel: "승인", href: "/assistant/approval" },
    ],
  },
  // "관리자" 그룹("회원 승인" /admin/users, "라이선스 관리" /admin/licenses) 임시 제거
  // — 프론트 페이지·백엔드 라우터 모두 미구현으로 클릭 시 404
  // (2026-09-30, docs/defect_index.json #104). 복원 시 실제 기능 신설 후 되살릴 것.
];

// NAV_GROUPS_ALL(구 "전체 목록 보존" 상수)은 2026-09-30 삭제함(docs/defect_index.json #106).
// 실제 코드 사용처 0건(주석 2곳 언급뿐, grep 확인 완료) — 정의만 되고 아무 데서도 import 안 되는
// 죽은 코드였고, 안에 있던 항목 전부가 가리키는 페이지는 이미 2026-09-23 대청소(commit 889e4003,
// docs/deleted_code_index.md)에서 삭제된 것들이었다. 복원이 필요하면 deleted_code_index.md의
// `git checkout backup/pre-cleanup-20260923 -- <경로>` 절차를 그대로 쓰면 된다 — 이 상수는
// 그 복원 정보를 중복·구식으로 들고 있었을 뿐 별도 가치가 없었음.

// 기존 flat 목록 — 레거시 호환
export const NAV_ITEMS: NavItem[] = NAV_GROUPS.flatMap((g) => g.items);
