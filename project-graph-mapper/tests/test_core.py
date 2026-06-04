import textwrap
from pathlib import Path

import pytest

from project_graph_mapper.graph.builder import GraphBuilder
from project_graph_mapper.graph.models import SymbolKind
from project_graph_mapper.graph.query import QueryEngine
from project_graph_mapper.parser.python_parser import PythonParser


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_project(tmp_path: Path) -> Path:
    """
    Tạo mini project:
      utils/auth.py    — định nghĩa validate_token()
      services/user.py — import và gọi validate_token()
      api/orders.py    — import và gọi validate_token()
    """
    (tmp_path / "utils").mkdir()
    (tmp_path / "services").mkdir()
    (tmp_path / "api").mkdir()

    (tmp_path / "utils" / "auth.py").write_text(textwrap.dedent("""
        def validate_token(token: str) -> bool:
            \"\"\"Validate JWT token.\"\"\"
            return token.startswith("Bearer ")

        class AuthHelper:
            def check(self, token: str) -> bool:
                return validate_token(token)
    """), encoding="utf-8")

    (tmp_path / "services" / "user.py").write_text(textwrap.dedent("""
        from utils.auth import validate_token

        def get_user(token: str):
            if not validate_token(token):
                raise PermissionError("Invalid token")
            return {"id": 1}
    """), encoding="utf-8")

    (tmp_path / "api" / "orders.py").write_text(textwrap.dedent("""
        from utils.auth import validate_token

        def list_orders(token: str):
            validate_token(token)
            return []
    """), encoding="utf-8")

    return tmp_path


# ── Parser tests ──────────────────────────────────────────────────────────────

class TestPythonParser:

    def test_extracts_function(self, sample_project):
        parser = PythonParser()
        fpath  = sample_project / "utils" / "auth.py"
        file_node, symbols = parser.parse_file(fpath, sample_project)

        names = [s.name for s in symbols]
        assert "validate_token" in names

    def test_extracts_class_and_method(self, sample_project):
        parser = PythonParser()
        fpath  = sample_project / "utils" / "auth.py"
        _, symbols = parser.parse_file(fpath, sample_project)

        kinds = {s.name: s.kind for s in symbols}
        assert kinds["AuthHelper"] == SymbolKind.CLASS
        assert kinds["check"] == SymbolKind.METHOD

    def test_captures_docstring(self, sample_project):
        parser = PythonParser()
        fpath  = sample_project / "utils" / "auth.py"
        _, symbols = parser.parse_file(fpath, sample_project)

        fn = next(s for s in symbols if s.name == "validate_token")
        assert "JWT" in fn.docstring

    def test_captures_imports(self, sample_project):
        parser = PythonParser()
        fpath  = sample_project / "services" / "user.py"
        file_node, _ = parser.parse_file(fpath, sample_project)

        assert any("auth" in imp for imp in file_node.imports)

    def test_invalid_syntax_returns_empty(self, tmp_path):
        bad = tmp_path / "bad.py"
        bad.write_text("def broken(:\n    pass", encoding="utf-8")
        parser = PythonParser()
        file_node, syms = parser.parse_file(bad, tmp_path)
        assert syms == []


# ── Builder tests ─────────────────────────────────────────────────────────────

class TestGraphBuilder:

    def test_build_finds_all_files(self, sample_project):
        builder = GraphBuilder().build(sample_project)
        assert len(builder.files) == 3

    def test_build_finds_symbols(self, sample_project):
        builder = GraphBuilder().build(sample_project)
        names = [sym.name for sym in builder.symbols.values()]
        assert "validate_token" in names
        assert "get_user" in names
        assert "list_orders" in names

    def test_resolve_used_by(self, sample_project):
        builder = GraphBuilder().build(sample_project)

        # validate_token phải có used_by từ user.py và orders.py
        sym = next(
            s for s in builder.symbols.values()
            if s.name == "validate_token" and s.kind == SymbolKind.FUNCTION
        )
        caller_files = {cs.file for cs in sym.used_by}
        assert any("user" in f for f in caller_files)
        assert any("orders" in f for f in caller_files)

    def test_skip_venv(self, sample_project):
        venv_dir = sample_project / ".venv" / "lib"
        venv_dir.mkdir(parents=True)
        (venv_dir / "fake.py").write_text("def fake(): pass")

        builder = GraphBuilder().build(sample_project)
        assert all(".venv" not in path for path in builder.files)


# ── Query engine tests ────────────────────────────────────────────────────────

class TestQueryEngine:

    def test_impact_finds_direct_callers(self, sample_project):
        builder = GraphBuilder().build(sample_project)
        result  = QueryEngine(builder.graph, builder.symbols).impact("validate_token")

        assert "error" not in result
        assert result["impact_score"] >= 2

    def test_impact_unknown_symbol(self, sample_project):
        builder = GraphBuilder().build(sample_project)
        result  = QueryEngine(builder.graph, builder.symbols).impact("does_not_exist")
        assert "error" in result

    def test_hotspots_returns_sorted(self, sample_project):
        builder  = GraphBuilder().build(sample_project)
        results  = QueryEngine(builder.graph, builder.symbols).hotspots(5)

        if results:
            scores = [score for _, score in results]
            assert scores == sorted(scores, reverse=True)

    def test_checklist_not_empty(self, sample_project):
        builder = GraphBuilder().build(sample_project)
        result  = QueryEngine(builder.graph, builder.symbols).impact("validate_token")
        assert len(result["checklist"]) > 0

    def test_dead_code_finds_unused_symbols(self, sample_project):
        builder = GraphBuilder().build(sample_project)
        dead = QueryEngine(builder.graph, builder.symbols).dead_code()
        
        names = [builder.symbols[sid].name for sid in dead]
        assert "get_user" in names
        assert "list_orders" in names
        assert "check" in names
        assert "validate_token" not in names

    def test_call_paths_finds_valid_paths(self, sample_project):
        builder = GraphBuilder().build(sample_project)
        paths = QueryEngine(builder.graph, builder.symbols).call_paths("get_user", "validate_token")
        
        assert len(paths) >= 1
        path_names = [[builder.symbols[sid].name for sid in p] for p in paths]
        assert ["get_user", "validate_token"] in path_names

