"""소프트웨어 리포트 생성기."""
from __future__ import annotations

from .models import SoftwareProgram, SoftwareSummary, SoftwareReport
from .catalog import get_catalog
from .detector import ProgramDetector


class SoftwareReportBuilder:
    """소프트웨어 진단 리포트 생성."""

    def build_report(self) -> SoftwareReport:
        """모든 프로그램 진단 리포트 생성."""
        catalog = get_catalog()
        programs = []
        installed_count = 0
        needs_setup_count = 0

        for program_id, program_def in catalog.items():
            installed, version, path = ProgramDetector.check_program(program_def, check_version=False)

            notes = []
            if not installed:
                notes.append(f"{program_def.name} 미설치")

            program = SoftwareProgram(
                id=program_id,
                name=program_def.name,
                installed=installed,
                version=version,
                path=path,
                install_required=not installed,
                admin_required_for_install=program_def.admin_required_for_install,
                reboot_may_be_required=program_def.reboot_may_be_required,
                notes=notes,
            )

            programs.append(program)

            if installed:
                installed_count += 1
            else:
                needs_setup_count += 1

        # 요약
        summary = SoftwareSummary(
            total=len(programs),
            installed=installed_count,
            missing=len(programs) - installed_count,
            needs_setup=needs_setup_count,
        )

        # 추천사항
        recommendations = self._generate_recommendations(programs)

        return SoftwareReport(
            ok=True,
            summary=summary,
            programs=programs,
            recommendations=recommendations,
        )

    @staticmethod
    def _generate_recommendations(programs: list[SoftwareProgram]) -> list[str]:
        """추천사항 생성."""
        recommendations = []

        # Docker 체크
        docker = next((p for p in programs if p.id == 'docker'), None)
        if docker and not docker.installed:
            recommendations.append('Docker Desktop 설치를 권장합니다 (컨테이너 기반 개발 환경)')

        # Git 체크
        git = next((p for p in programs if p.id == 'git'), None)
        if git and not git.installed:
            recommendations.append('Git 설치를 권장합니다 (버전 관리)')

        # Python/Node.js 체크
        python = next((p for p in programs if p.id == 'python'), None)
        node = next((p for p in programs if p.id == 'node'), None)

        if python and not python.installed:
            recommendations.append('Python 설치를 권장합니다 (스크립트 개발)')

        if node and not node.installed:
            recommendations.append('Node.js 설치를 권장합니다 (JavaScript 런타임)')

        return recommendations
