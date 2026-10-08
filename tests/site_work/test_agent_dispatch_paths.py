"""AI 에이전트 작업 분배 — 경로 정규화 우회 회귀 시험 (적대적 검증 2026-10-02).

같은 위치를 가리키는 서로 다른 표기가 충돌 판정을 피하면 두 쓰기 작업이 같은 파일을 동시에 바꾼다.
표기를 하나로 모으고, 판정할 수 없는 표기는 전역 직렬(fail-closed)로 처리하는지 확인한다.
"""

from __future__ import annotations

import pytest

from ai_orchestrator.agent_dispatch import agent_dispatch_policy as pol


@pytest.fixture(autouse=True)
def fixed_workdir(monkeypatch):
    monkeypatch.setattr(pol, "WORKDIR", "c:/p")  # 상대 경로 기준을 고정해 결정적으로 시험한다


def claim(*paths):
    return pol.claim_of({"id": "x", "read_only": False, "resources": list(paths)})


def same_place(a: str, b: str) -> bool:
    return pol.conflicts(claim(a), claim(b))


# 같은 위치의 다른 표기 — 모두 충돌해야 한다
@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("path:src", "path:./src"),  # 리뷰어 재현 1
        ("path:src", "path:SRC/"),  # 대소문자·끝 슬래시
        ("path:src", "path:src."),  # 리뷰어 재현 4: Windows 는 끝 점을 지운다
        ("path:src", "path:src "),  # 끝 공백
        ("path:src", "path:src/../src"),
        ("path:src", "path:./a/../src"),
        ("path:C:/p/src", "path:src"),  # 리뷰어 재현 2: 절대/상대 혼용
        (r"path:C:\p\src", "path:c:/p/src/"),
        (r"path:\\?\C:\p\src", "path:c:/p/src"),  # 확장 길이 접두
        ("path:c:/p/src/sub", "path:src"),  # 포함 관계
        ("path:src", "path:C:/p/src/sub/deep"),
        ("path:C:/", "path:C:/p/src"),  # 드라이브 루트는 아래 전부와 겹친다
        (r"path:\\H\S\x", "path://h/s/x/."),  # UNC
        (r"path:\\?\UNC\h\s\x", "path://h/s/x"),
        ("path:src", "path:src/./."),
    ],
)
def test_same_location_different_spelling_conflicts(a, b):
    assert same_place(a, b) and same_place(b, a)


# 서로 다른 위치 — 병렬 가능해야 한다(과도한 직렬화 방지)
@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("path:src", "path:src2"),  # 접두 문자열만 같음
        ("path:src", "path:srcs/x"),
        ("path:C:/p/a", "path:C:/p/b"),
        ("path:C:/p/a", "path:D:/p/a"),  # 다른 드라이브
        ("path://h/s1/x", "path://h/s2/x"),  # 다른 공유
        ("path://h/s/x", "path://h2/s/x"),
        ("path:a", "path:a.b"),  # 점이 중간에 있는 이름은 그대로
    ],
)
def test_different_locations_do_not_conflict(a, b):
    assert not same_place(a, b)


# 판정할 수 없는 표기 — 전역 직렬(fail-closed)
@pytest.mark.parametrize(
    "bad",
    [
        "path:C:src",  # 드라이브 상대
        "path:/etc/passwd",  # 앞 슬래시만(드라이브 불명)
        "path:src/*.py",  # 와일드카드
        "path:src/a?b",
        "path:a:stream",  # 대체 데이터 스트림
        "path:C:/p/a:hidden",
        "path:PROGRA~1/x",  # 8.3 짧은 이름
        "path:C:/../x",  # 드라이브 루트 밖으로 벗어남
        "path://h/s/../../x",  # 공유 루트 밖으로 벗어남
        r"path:\\h",  # 공유 없는 UNC
        "path:...",
        "path:",
        "path:C:/p/a\x00b",  # 제어문자
        'path:src/"x"',
    ],
)
def test_undecidable_spelling_is_global_serial(bad):
    c = claim(bad)
    assert c.is_global and not c.free
    assert pol.conflicts(c, claim("path:other"))  # 어떤 쓰기 작업과도 동시에 돌지 않는다


def test_relative_path_outside_workdir_is_resolved_not_trusted():
    # 기준 폴더 밖으로 나가는 상대 경로(../x)도 절대화해 비교한다 — 같은 위치를 절대 경로로 쓴 작업과 충돌
    assert same_place("path:../x", "path:C:/x")
    assert not same_place("path:../x", "path:src")


def test_workdir_not_drive_path_makes_relative_undecidable(monkeypatch):
    monkeypatch.setattr(pol, "WORKDIR", "/home/user/repo")  # 드라이브 경로가 아닌 기준 폴더
    assert claim("path:src").is_global  # 판정 불가 → 전역 직렬
    assert not claim("path:C:/p/src").is_global  # 절대 경로는 그대로 판정


def test_multiple_resources_any_overlap_conflicts():
    assert pol.conflicts(claim("path:a", "path:b"), claim("path:./B/"))
    assert not pol.conflicts(claim("path:a", "path:b"), claim("path:c"))
    assert pol.conflicts(claim("path:a", "git"), claim("path:zzz"))  # 전역 자원이 섞이면 전역
