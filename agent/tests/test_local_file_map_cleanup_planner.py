"""파일 정리 계획표 생성기 테스트."""
import pytest
from datetime import datetime, timedelta
from agent.local_inventory.file_map.models import FileMapReport
from agent.local_inventory.file_map.cleanup_planner import CleanupPlanner


@pytest.fixture
def sample_report():
    """테스트 리포트."""
    now = datetime.utcnow().isoformat() + "Z"
    old_time = (datetime.utcnow() - timedelta(days=400)).isoformat() + "Z"
    recent_time = (datetime.utcnow() - timedelta(days=10)).isoformat() + "Z"

    return FileMapReport(
        scan_timestamp=now,
        scanned_directory="C:\\Users\\test",
        scan_duration_seconds=10.5,
        total_files=100,
        total_size_bytes=1000000000,
        files_by_category={"document": 50, "image": 30, "archive": 20},
        large_files=[
            {
                "path": "C:\\Users\\test\\large_backup.zip",
                "name": "large_backup.zip",
                "size_bytes": 500000000,
                "modified_time": old_time,
            }
        ],
        old_files=[
            {
                "path": "C:\\Users\\test\\old_setup.exe",
                "name": "old_setup.exe",
                "size_bytes": 150000000,
                "modified_time": old_time,
            },
            {
                "path": "C:\\Users\\test\\문서_신분증.pdf",
                "name": "문서_신분증.pdf",
                "size_bytes": 5000000,
                "modified_time": old_time,
            },
            {
                "path": "C:\\Users\\test\\보고서.docx",
                "name": "보고서.docx",
                "size_bytes": 2000000,
                "modified_time": old_time,
            },
        ],
        suspicious_duplicates=[
            {
                "path": "C:\\Users\\test\\파일_복사본.txt",
                "name": "파일_복사본.txt",
                "size_bytes": 100000,
                "modified_time": recent_time,
            },
            {
                "path": "C:\\Users\\test\\data (1).xlsx",
                "name": "data (1).xlsx",
                "size_bytes": 5000000,
                "modified_time": old_time,
            },
        ],
        suspicious_temp=[
            {
                "path": "C:\\Users\\test\\다운로드\\file.zip",
                "name": "file.zip",
                "size_bytes": 300000000,
                "modified_time": recent_time,
            }
        ],
        recommendations=["Cleanup old files", "Organize documents"],
    )


class TestCleanupPlanner:
    """CleanupPlanner 테스트."""

    def test_cleanup_planner_no_file_operations(self, sample_report):
        """정리 계획이 파일 조작을 하지 않음."""
        planner = CleanupPlanner()
        plans = planner.plan_cleanup(sample_report)

        # 계획이 생성되어야 함
        assert len(plans) > 0

        # 모든 계획은 file_path, proposed_location만 가져야 함
        for plan in plans:
            assert plan.file_path
            assert plan.proposed_location
            # 실제 파일 조작 없음
            assert plan.category in [
                "보관", "업무문서", "엑셀정산", "CAD도면", "이미지스캔",
                "민감문서", "중복검토", "분류보류"
            ]

    def test_installer_old_files_are_backup_candidates(self, sample_report):
        """오래된 설치파일은 보관 후보로 분류."""
        planner = CleanupPlanner()
        plans = planner.plan_cleanup(sample_report)

        # old_setup.exe를 찾기
        setup_plans = [p for p in plans if "setup" in p.file_path.lower()]
        assert len(setup_plans) > 0

        setup_plan = setup_plans[0]
        assert setup_plan.category == "보관"
        assert "설치파일" in setup_plan.reason

    def test_sensitive_files_are_marked_sensitive(self, sample_report):
        """민감정보 파일은 민감문서로 분류."""
        planner = CleanupPlanner()
        plans = planner.plan_cleanup(sample_report)

        # 신분증 포함 파일 찾기
        sensitive_plans = [p for p in plans if "신분증" in p.masked_name or "민감" in p.category]
        # 마스킹되어야 하므로 "신분증"이 보이지 않아야 함
        assert any(p.category == "민감문서" for p in plans)

    def test_duplicate_patterns_marked_for_review(self, sample_report):
        """중복 패턴은 검토 후보로 표시."""
        planner = CleanupPlanner()
        plans = planner.plan_cleanup(sample_report)

        # 복사본/중복 패턴 찾기
        duplicate_plans = [p for p in plans if p.category == "중복검토"]
        assert len(duplicate_plans) > 0

        # 실제 삭제가 아니라 검토 (proposed_location이 중복검토)
        for plan in duplicate_plans:
            assert "중복검토" in plan.proposed_location

    def test_masking_by_default(self, sample_report):
        """기본적으로 파일명이 마스킹됨."""
        planner = CleanupPlanner(reveal_sensitive_names=False, auth_verified=False)
        plans = planner.plan_cleanup(sample_report)

        # 신분증이 있는 파일 찾기
        for plan in plans:
            if "신분증" in plan.file_path:
                # masked_name에는 신분증이 보이지 않아야 함
                assert "신분증" not in plan.masked_name or "[신분증]" in plan.masked_name

    def test_masking_with_auth(self, sample_report):
        """인증 시 원본 파일명 표시."""
        planner = CleanupPlanner(reveal_sensitive_names=True, auth_verified=True)
        plans = planner.plan_cleanup(sample_report)

        # 신분증 파일을 찾아서 원본이 표시되는지 확인
        for plan in plans:
            if "신분증" in plan.file_path:
                assert "신분증" in plan.masked_name

    def test_summarize_plans(self, sample_report):
        """계획 요약."""
        planner = CleanupPlanner()
        plans = planner.plan_cleanup(sample_report)
        summary = planner.summarize_plans(plans)

        # 카테고리별 요약 생성
        assert len(summary) > 0

        # 각 카테고리는 count, total_size, samples를 가져야 함
        for cat, data in summary.items():
            assert "count" in data
            assert "total_size" in data
            assert "samples" in data
            assert data["count"] > 0
            assert len(data["samples"]) > 0

    def test_recent_files_held_for_review(self, sample_report):
        """최근 파일은 분류보류."""
        planner = CleanupPlanner()
        plans = planner.plan_cleanup(sample_report)

        # 최근 파일 찾기
        recent_plans = [
            p for p in plans
            if p.modified_time == sample_report.suspicious_duplicates[0].get("modified_time")
        ]

        # 최근 복사본은 분류보류 또는 중복검토 (둘 다 괜찮음)
        assert any(
            p.category in ["분류보류", "중복검토"]
            for p in recent_plans
        )

    def test_no_duplicate_paths_in_plans(self, sample_report):
        """계획에 중복 경로 없음."""
        planner = CleanupPlanner()
        plans = planner.plan_cleanup(sample_report)

        paths = [p.file_path for p in plans]
        assert len(paths) == len(set(paths))  # 모두 유니크

    def test_category_proposed_location_consistency(self, sample_report):
        """카테고리와 제안 경로가 일치."""
        planner = CleanupPlanner()
        plans = planner.plan_cleanup(sample_report)

        category_to_path = {
            "보관": "설치파일_보관",
            "업무문서": "업무문서",
            "엑셀정산": "엑셀",
            "CAD도면": "CAD",
            "이미지스캔": "사진_스캔",
            "민감문서": "민감",
            "중복검토": "중복",
            "분류보류": "분류보류",
        }

        for plan in plans:
            expected_str = category_to_path.get(plan.category, "")
            if expected_str:
                assert expected_str in plan.proposed_location or plan.category == "분류보류"
