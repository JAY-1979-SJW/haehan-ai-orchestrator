"""sqlite 스키마 버전 관리 — `PRAGMA user_version` 기반 순차 마이그레이션 (결함 #14).

설계: docs/specs/2026-10-01_sqlite_schema_versioning.md

사용:
    def _v1(con): con.execute("CREATE TABLE IF NOT EXISTS t (...)")
    def _v2(con): add_column_if_missing(con, "t", "extra", "TEXT")
    apply_schema(con, [_v1, _v2])

규칙: 한 번 배포된 단계는 수정하지 않고 새 단계를 뒤에 추가한다. 모든 단계는 멱등이어야 한다.
`user_version` 은 DB 파일당 정수 하나이므로 한 파일을 소유하는 모듈은 하나여야 한다.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Callable, Sequence

SchemaStep = Callable[[sqlite3.Connection], None]

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class SchemaTooNewError(RuntimeError):
    """DB 의 user_version 이 코드가 아는 최신 단계보다 크다 — 옛 코드가 새 DB 를 건드리지 못하게 막는다."""


def current_version(con: sqlite3.Connection) -> int:
    return int(con.execute("PRAGMA user_version").fetchone()[0])


def _ident(name: str) -> str:
    if not _IDENT.match(name):
        raise ValueError(f"잘못된 SQL 식별자: {name!r}")
    return name


def column_names(con: sqlite3.Connection, table: str) -> set[str]:
    return {
        row[1] for row in con.execute(f"PRAGMA table_info({_ident(table)})")
    }  # 식별자는 _ident 로 정규식 검증 후 조립


def add_column_if_missing(con: sqlite3.Connection, table: str, column: str, ddl: str) -> bool:
    """컬럼이 없을 때만 추가한다(멱등). 추가했으면 True. `ddl` 은 타입·기본값 정의(코드 상수만 넣을 것)."""
    if column in column_names(con, table):
        return False
    con.execute(
        f"ALTER TABLE {_ident(table)} ADD COLUMN {_ident(column)} {ddl}"
    )  # 식별자는 _ident 검증, ddl 은 코드 상수
    return True


def apply_schema(con: sqlite3.Connection, steps: Sequence[SchemaStep]) -> int:
    """현재 버전 이후의 단계만 순서대로 실행하고 최종 버전을 반환한다.

    - 이미 최신이면 `PRAGMA user_version` 한 번만 읽고 끝난다(연결마다 DDL 재실행 없음).
    - 단계 실행은 `BEGIN IMMEDIATE` 트랜잭션 하나다. 실패하면 전부 롤백하고 버전은 그대로다.
    - 잠금을 잡은 뒤 버전을 다시 읽어, 동시 프로세스가 같은 단계를 두 번 실행하지 않게 한다.
    - DB 가 코드보다 새로우면 SchemaTooNewError.
    """
    target = len(steps)
    version = current_version(con)
    if version == target:
        return version
    if version > target:
        raise SchemaTooNewError(f"DB 스키마 버전 {version} 이 코드 최신 {target} 보다 새롭다")

    con.execute("BEGIN IMMEDIATE")
    try:
        version = current_version(con)
        if version > target:
            raise SchemaTooNewError(f"DB 스키마 버전 {version} 이 코드 최신 {target} 보다 새롭다")
        for index in range(version, target):
            steps[index](con)
            con.execute(f"PRAGMA user_version = {int(index) + 1}")  # user_version 은 바인딩 불가 — int 만 포매팅
        con.execute("COMMIT")
    except BaseException:
        if con.in_transaction:
            con.execute("ROLLBACK")
        raise
    return target
