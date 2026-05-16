import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: '해한 디자인 시스템',
  description: '비서앱·입찰앱·CAD앱·출퇴근앱 공통 UI 기준 프로젝트',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
