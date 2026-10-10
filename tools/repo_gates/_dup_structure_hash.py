"""함수 구조 지문(이름·상수를 지운 AST 해시) — G12 중복 게이트의 핵심 알고리즘.

원본: C:/work/audit-tools/dupscan/src/dupscan/extractor.py(normalize/structure_hash/
iter_functions/is_test_path). CI는 그 저장소(개인 PC 경로)에 접근할 수 없어 알고리즘만
그대로 가져온다(외부 경로 의존 금지, tools/repo_gates/dup_gate.py가 재구현하지 않도록 함).
dupscan 자체(유사도 분석·카탈로그·리포트)는 재구현하지 않는다 — 이 파일은 구조 해시 하나만 다룬다.

이전: 2026-10-07, dupscan 커밋 시점 기준 extractor.py 그대로 옮김(다른 프로젝트에서
의도적으로 복사한 코드 — 중복 감사(G12/dupscan) 결과에 이 파일 자신이 "중복"으로
걸려도 의도된 것이니 오해하지 말 것). dupscan 쪽 normalize/structure_hash/iter_functions/
is_test_path가 바뀌면 이 파일도 함께 동기화해야 한다.
"""

from __future__ import annotations

import ast
import copy
import hashlib
from collections.abc import Iterator
from pathlib import PurePosixPath
from typing import override


class _Normalizer(ast.NodeTransformer):
    """변수·인자·함수 이름과 상수 값을 지워 '구조'만 남긴다. 속성 이름(API 호출)은 유지한다."""

    @override
    def visit_Name(self, node: ast.Name) -> ast.AST:
        return ast.copy_location(ast.Name(id="_v", ctx=node.ctx), node)

    @override
    def visit_arg(self, node: ast.arg) -> ast.AST:
        node.arg = "_a"
        node.annotation = None
        return node

    @override
    def visit_Constant(self, node: ast.Constant) -> ast.AST:
        return ast.copy_location(ast.Constant(value=type(node.value).__name__), node)

    def _strip_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> ast.AST:
        node.name = "_f"
        node.returns = None
        node.decorator_list = []
        body = node.body
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
            body = body[1:] or [ast.Pass()]  # docstring 제거
        node.body = body
        return self.generic_visit(node)

    @override
    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        return self._strip_function(node)

    @override
    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AST:
        return self._strip_function(node)


def normalize(node: ast.FunctionDef | ast.AsyncFunctionDef) -> ast.AST:
    tree: ast.AST = _Normalizer().visit(copy.deepcopy(node))
    return ast.fix_missing_locations(tree)


def structure_hash(normalized: ast.AST) -> str:
    dump = ast.dump(normalized, annotate_fields=False, include_attributes=False)
    return hashlib.sha1(dump.encode("utf-8"), usedforsecurity=False).hexdigest()


def body_statement_count(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    """docstring을 뺀 함수 본문의 문장 수(얕은 count, 중첩 블록 내부는 세지 않음)."""
    body = node.body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]
    return len(body)


def iter_functions(
    tree: ast.Module,
) -> Iterator[tuple[str, ast.FunctionDef | ast.AsyncFunctionDef]]:
    """(qualname, 함수 노드). 클래스 메서드와 중첩 함수를 포함한다."""
    stack: list[tuple[str, ast.AST]] = [("", tree)]
    while stack:
        prefix, parent = stack.pop()
        for node in ast.iter_child_nodes(parent):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qual = f"{prefix}{node.name}"
                yield qual, node
                stack.append((f"{qual}.", node))
            elif isinstance(node, ast.ClassDef):
                stack.append((f"{prefix}{node.name}.", node))


def is_test_path(rel_path: str) -> bool:
    parts = PurePosixPath(rel_path).parts
    name = parts[-1]
    return "tests" in parts[:-1] or name.startswith("test_") or name == "conftest.py"
