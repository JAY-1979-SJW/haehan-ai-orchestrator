from tools.code_map import query

M = {
    "import_edges": {"a.py": ["b.py"], "b.py": ["c.py"], "tests/test_a.py": ["a.py"]},
    "files": {"a.py": {"class": "LIVE"}},
}


def test_queries():
    assert query.who_imports(M, "b.py") == ["a.py"]
    assert query.imports_of(M, "a.py") == ["b.py"]
    assert query.impact(M, ["c.py"]) == ["a.py", "b.py", "tests/test_a.py"]
    assert query.tests_for(M, ["c.py"]) == ["tests/test_a.py"]
    assert query.class_of(M, "a.py") == "LIVE"
