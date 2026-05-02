import { FileMapReportViewer } from "@/components/file-map";
import { PageShell } from "@/components/ui";

// 샘플 리포트 데이터 (개발/테스트용)
const SAMPLE_REPORT_DATA = {
  title: "LOCAL-FILE-MAP-1E: 프로젝트 파일 정밀 스캔 리포트",
  content: `# LOCAL-FILE-MAP-1E: 프로젝트 파일 정밀 스캔 리포트

**스캔 날짜**: 2026-05-02
**스캔 상태**: ✅ 완료 (읽기 전용, 파일 변경 없음)

---

## 스캔 대상

| 항목 | 내용 |
|-----|------|
| **스캔 루트** | C:\\Users\\skyjw\\OneDrive |
| **스캔 모드** | 읽기 전용 |
| **총 파일 수** | 3,842 개 |
| **스캔 시간** | 약 45초 |

---

## 스캔 결과 요약

| 항목 | 수량 |
|-----|------|
| **전체 파일** | 3,842 |
| **카테고리** | 12 개 |
| **대용량 파일** | 127 개 (>100MB) |
| **오래된 파일** | 234 개 (>3년) |
| **중복 의심** | 45 개 |
| **임시 의심** | 89 개 |

---

## 카테고리별 분포

- **문서** (1,243개): 71% — Word, Excel, PDF 등
- **이미지** (856개): 22% — JPG, PNG, GIF 등
- **코드** (234개): 6% — Python, TypeScript, JSON 등
- **기타** (509개): 1% — 아카이브, 영상, 음성 등

---

## 주요 발견사항

### 1. 대용량 파일 (127개)
- 최대: 4.2GB (backup_archive.zip)
- 평균: 312MB
- 권장: 클라우드 백업 정책 검토

### 2. 오래된 파일 (234개)
- 최고령: 2021년 5월
- 평균 나이: 2.3년
- 권장: 정기적 아카이브/삭제 정책 수립

### 3. 중복 의심 (45개)
- 이름 기준 중복: 23개
- 내용 기준 중복: 22개
- 권장: 정기적 중복 제거 작업

---

## 추천사항

1. **보관 정책**: 3년 이상 오래된 파일에 대한 보관/삭제 정책 수립
2. **중복 제거**: 정기적인 중복 파일 정리
3. **클라우드 최적화**: 대용량 파일의 클라우드 백업 전략 수립
4. **정기 감시**: 월 1회 파일 지도 스캔 및 리포트 생성

---

**정책 담당**: AI Orchestrator Team
**최종 수정**: 2026-05-02`,
  files: [
    {
      name: "****_[신분증].jpg",
      path: "C:\\Users\\skyjw\\OneDrive\\개인\\증명서",
      size: 2048576,
    },
    {
      name: "프로젝트_제안서.docx",
      path: "C:\\Users\\skyjw\\OneDrive\\업무\\문서",
      size: 512000,
    },
    {
      name: "2024_연말_****_[급여].xlsx",
      path: "C:\\Users\\skyjw\\OneDrive\\재정\\월급",
      size: 256000,
    },
    {
      name: "한컴오피스 2018.zip",
      path: "C:\\Users\\skyjw\\OneDrive\\소프트웨어",
      size: 1048576000,
    },
    {
      name: "backup_2023.zip",
      path: "C:\\Users\\skyjw\\OneDrive\\백업",
      size: 4398046511104,
    },
  ],
};

export default function FileMapPage() {
  return (
    <PageShell title="파일 지도 리포트" description="로컬 파일 지도 스캔 결과 뷰어">
      <div className="max-w-4xl">
        <FileMapReportViewer reportData={SAMPLE_REPORT_DATA} />
      </div>
    </PageShell>
  );
}
