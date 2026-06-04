"""Tests for multi-language parsers (v0.2.0)."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from project_graph_mapper.graph.builder import GraphBuilder
from project_graph_mapper.graph.models import SymbolKind
from project_graph_mapper.parser.base import clear_registry, register, get_parser, supported_extensions


# ══════════════════════════════════════════════════════════════════════════════
# JavaScript Parser
# ══════════════════════════════════════════════════════════════════════════════

class TestJavaScriptParser:

    @pytest.fixture
    def js_file(self, tmp_path: Path) -> tuple[Path, Path]:
        f = tmp_path / "app.js"
        f.write_text(textwrap.dedent("""\
            import { Router } from 'express';

            function greet(name) {
                return `Hello ${name}`;
            }

            class UserService {
                constructor(db) {
                    this.db = db;
                }

                findById(id) {
                    return this.db.find(id);
                }
            }

            const fetchData = async (url) => {
                return fetch(url);
            };

            module.exports = { greet, UserService, fetchData };
        """), encoding="utf-8")
        return f, tmp_path

    def test_extracts_functions(self, js_file):
        from project_graph_mapper.parser.js_parser import JavaScriptParser
        fpath, root = js_file
        parser = JavaScriptParser()
        _, symbols = parser.parse_file(fpath, root)

        names = [s.name for s in symbols]
        assert "greet" in names

    def test_extracts_class(self, js_file):
        from project_graph_mapper.parser.js_parser import JavaScriptParser
        fpath, root = js_file
        parser = JavaScriptParser()
        _, symbols = parser.parse_file(fpath, root)

        kinds = {s.name: s.kind for s in symbols}
        assert kinds.get("UserService") == SymbolKind.CLASS

    def test_extracts_methods(self, js_file):
        from project_graph_mapper.parser.js_parser import JavaScriptParser
        fpath, root = js_file
        parser = JavaScriptParser()
        _, symbols = parser.parse_file(fpath, root)

        methods = [s for s in symbols if s.kind == SymbolKind.METHOD]
        method_names = [m.name for m in methods]
        assert "findById" in method_names

    def test_extracts_arrow_function(self, js_file):
        from project_graph_mapper.parser.js_parser import JavaScriptParser
        fpath, root = js_file
        parser = JavaScriptParser()
        _, symbols = parser.parse_file(fpath, root)

        names = [s.name for s in symbols]
        assert "fetchData" in names

    def test_extracts_imports(self, js_file):
        from project_graph_mapper.parser.js_parser import JavaScriptParser
        fpath, root = js_file
        parser = JavaScriptParser()
        file_node, _ = parser.parse_file(fpath, root)

        assert "express" in file_node.imports

    def test_file_node_language(self, js_file):
        from project_graph_mapper.parser.js_parser import JavaScriptParser
        fpath, root = js_file
        parser = JavaScriptParser()
        file_node, _ = parser.parse_file(fpath, root)
        assert file_node.language == "javascript"

    def test_captures_comments(self, tmp_path: Path):
        from project_graph_mapper.parser.js_parser import JavaScriptParser
        f = tmp_path / "comments.js"
        f.write_text(textwrap.dedent("""
            // This is a line comment
            // second line
            function greet() {}

            /* This is a block comment */
            class User {
                /**
                 * Method comment
                 */
                find() {}
            }
        """), encoding="utf-8")
        
        parser = JavaScriptParser()
        _, symbols = parser.parse_file(f, tmp_path)
        
        # Check greet docstring
        greet_sym = next(s for s in symbols if s.name == "greet")
        assert "This is a line comment" in greet_sym.docstring
        assert "second line" in greet_sym.docstring
        
        # Check User docstring
        user_sym = next(s for s in symbols if s.name == "User")
        assert "This is a block comment" in user_sym.docstring
        
        # Check find docstring
        find_sym = next(s for s in symbols if s.name == "find")
        assert "Method comment" in find_sym.docstring



# ══════════════════════════════════════════════════════════════════════════════
# TypeScript Parser
# ══════════════════════════════════════════════════════════════════════════════

class TestTypeScriptParser:

    @pytest.fixture
    def ts_file(self, tmp_path: Path) -> tuple[Path, Path]:
        f = tmp_path / "service.ts"
        f.write_text(textwrap.dedent("""\
            import { Database } from './db';

            interface UserRepo {
                findById(id: string): Promise<User>;
            }

            enum Status {
                Active = 'active',
                Inactive = 'inactive',
            }

            class UserService implements UserRepo {
                constructor(private db: Database) {}

                async findById(id: string): Promise<User> {
                    return this.db.query(id);
                }
            }

            export function createService(db: Database): UserService {
                return new UserService(db);
            }
        """), encoding="utf-8")
        return f, tmp_path

    def test_extracts_interface(self, ts_file):
        from project_graph_mapper.parser.js_parser import TypeScriptParser
        fpath, root = ts_file
        parser = TypeScriptParser()
        _, symbols = parser.parse_file(fpath, root)

        interfaces = [s for s in symbols if s.kind == SymbolKind.INTERFACE]
        assert any(s.name == "UserRepo" for s in interfaces)

    def test_extracts_enum(self, ts_file):
        from project_graph_mapper.parser.js_parser import TypeScriptParser
        fpath, root = ts_file
        parser = TypeScriptParser()
        _, symbols = parser.parse_file(fpath, root)

        enums = [s for s in symbols if s.kind == SymbolKind.ENUM]
        assert any(s.name == "Status" for s in enums)

    def test_extracts_class_and_function(self, ts_file):
        from project_graph_mapper.parser.js_parser import TypeScriptParser
        fpath, root = ts_file
        parser = TypeScriptParser()
        _, symbols = parser.parse_file(fpath, root)

        names = [s.name for s in symbols]
        assert "UserService" in names
        assert "createService" in names


# ══════════════════════════════════════════════════════════════════════════════
# Go Parser
# ══════════════════════════════════════════════════════════════════════════════

class TestGoParser:

    @pytest.fixture
    def go_file(self, tmp_path: Path) -> tuple[Path, Path]:
        f = tmp_path / "server.go"
        f.write_text(textwrap.dedent("""\
            package main

            import (
                "fmt"
                "net/http"
            )

            type Server struct {
                port int
                host string
            }

            type Handler interface {
                ServeHTTP(w http.ResponseWriter, r *http.Request)
            }

            func NewServer(port int) *Server {
                return &Server{port: port, host: "localhost"}
            }

            func (s *Server) Start() error {
                addr := fmt.Sprintf("%s:%d", s.host, s.port)
                return http.ListenAndServe(addr, nil)
            }

            func (s *Server) Stop() {
                fmt.Println("Stopping server")
            }
        """), encoding="utf-8")
        return f, tmp_path

    def test_extracts_struct(self, go_file):
        from project_graph_mapper.parser.go_parser import GoParser
        fpath, root = go_file
        parser = GoParser()
        _, symbols = parser.parse_file(fpath, root)

        structs = [s for s in symbols if s.kind == SymbolKind.STRUCT]
        assert any(s.name == "Server" for s in structs)

    def test_extracts_interface(self, go_file):
        from project_graph_mapper.parser.go_parser import GoParser
        fpath, root = go_file
        parser = GoParser()
        _, symbols = parser.parse_file(fpath, root)

        interfaces = [s for s in symbols if s.kind == SymbolKind.INTERFACE]
        assert any(s.name == "Handler" for s in interfaces)

    def test_extracts_function(self, go_file):
        from project_graph_mapper.parser.go_parser import GoParser
        fpath, root = go_file
        parser = GoParser()
        _, symbols = parser.parse_file(fpath, root)

        funcs = [s for s in symbols if s.kind == SymbolKind.FUNCTION]
        assert any(s.name == "NewServer" for s in funcs)

    def test_extracts_methods_with_receiver(self, go_file):
        from project_graph_mapper.parser.go_parser import GoParser
        fpath, root = go_file
        parser = GoParser()
        _, symbols = parser.parse_file(fpath, root)

        methods = [s for s in symbols if s.kind == SymbolKind.METHOD]
        method_names = [m.name for m in methods]
        assert "Start" in method_names
        assert "Stop" in method_names

        # Method ID should have receiver prefix
        start = next(s for s in symbols if s.name == "Start")
        assert "Server.Start" in start.id

    def test_extracts_imports(self, go_file):
        from project_graph_mapper.parser.go_parser import GoParser
        fpath, root = go_file
        parser = GoParser()
        file_node, _ = parser.parse_file(fpath, root)

        assert "fmt" in file_node.imports
        assert "net/http" in file_node.imports


# ══════════════════════════════════════════════════════════════════════════════
# Rust Parser
# ══════════════════════════════════════════════════════════════════════════════

class TestRustParser:

    @pytest.fixture
    def rs_file(self, tmp_path: Path) -> tuple[Path, Path]:
        f = tmp_path / "lib.rs"
        f.write_text(textwrap.dedent("""\
            use std::io::Read;
            use std::collections::HashMap;

            pub struct Config {
                host: String,
                port: u16,
            }

            pub enum Status {
                Active,
                Inactive,
                Error(String),
            }

            pub trait Handler {
                fn handle(&self, request: &str) -> String;
            }

            impl Config {
                pub fn new(host: &str, port: u16) -> Self {
                    Config {
                        host: host.to_string(),
                        port,
                    }
                }

                pub fn address(&self) -> String {
                    format!("{}:{}", self.host, self.port)
                }
            }

            pub fn greet(name: &str) -> String {
                format!("Hello, {}!", name)
            }
        """), encoding="utf-8")
        return f, tmp_path

    def test_extracts_struct(self, rs_file):
        from project_graph_mapper.parser.rust_parser import RustParser
        fpath, root = rs_file
        parser = RustParser()
        _, symbols = parser.parse_file(fpath, root)

        structs = [s for s in symbols if s.kind == SymbolKind.STRUCT]
        assert any(s.name == "Config" for s in structs)

    def test_extracts_enum(self, rs_file):
        from project_graph_mapper.parser.rust_parser import RustParser
        fpath, root = rs_file
        parser = RustParser()
        _, symbols = parser.parse_file(fpath, root)

        enums = [s for s in symbols if s.kind == SymbolKind.ENUM]
        assert any(s.name == "Status" for s in enums)

    def test_extracts_trait(self, rs_file):
        from project_graph_mapper.parser.rust_parser import RustParser
        fpath, root = rs_file
        parser = RustParser()
        _, symbols = parser.parse_file(fpath, root)

        traits = [s for s in symbols if s.kind == SymbolKind.TRAIT]
        assert any(s.name == "Handler" for s in traits)

    def test_extracts_impl_methods(self, rs_file):
        from project_graph_mapper.parser.rust_parser import RustParser
        fpath, root = rs_file
        parser = RustParser()
        _, symbols = parser.parse_file(fpath, root)

        methods = [s for s in symbols if s.kind == SymbolKind.METHOD]
        method_names = [m.name for m in methods]
        assert "new" in method_names
        assert "address" in method_names

        # Method ID should have struct prefix
        new_sym = next(s for s in symbols if s.name == "new" and s.kind == SymbolKind.METHOD)
        assert "Config.new" in new_sym.id

    def test_extracts_function(self, rs_file):
        from project_graph_mapper.parser.rust_parser import RustParser
        fpath, root = rs_file
        parser = RustParser()
        _, symbols = parser.parse_file(fpath, root)

        funcs = [s for s in symbols if s.kind == SymbolKind.FUNCTION]
        assert any(s.name == "greet" for s in funcs)

    def test_extracts_imports(self, rs_file):
        from project_graph_mapper.parser.rust_parser import RustParser
        fpath, root = rs_file
        parser = RustParser()
        file_node, _ = parser.parse_file(fpath, root)

        assert any("std::io::Read" in imp for imp in file_node.imports)
        assert any("HashMap" in imp for imp in file_node.imports)

    def test_extracts_impl_block(self, rs_file):
        from project_graph_mapper.parser.rust_parser import RustParser
        fpath, root = rs_file
        parser = RustParser()
        _, symbols = parser.parse_file(fpath, root)

        impls = [s for s in symbols if s.kind == SymbolKind.IMPL]
        assert len(impls) >= 1
        assert any("Config" in s.name for s in impls)


# ══════════════════════════════════════════════════════════════════════════════
# Java Parser
# ══════════════════════════════════════════════════════════════════════════════

class TestJavaParser:

    @pytest.fixture
    def java_file(self, tmp_path: Path) -> tuple[Path, Path]:
        f = tmp_path / "UserService.java"
        f.write_text(textwrap.dedent("""\
            import com.example.db.Database;
            import com.example.models.User;

            public interface UserRepository {
                User findById(String id);
            }

            public enum UserStatus {
                ACTIVE,
                INACTIVE,
                BANNED
            }

            public class UserService implements UserRepository {
                private final Database db;

                public UserService(Database db) {
                    this.db = db;
                }

                public User findById(String id) {
                    return db.query(User.class, id);
                }

                public void deleteUser(String id) {
                    db.delete(User.class, id);
                }
            }
        """), encoding="utf-8")
        return f, tmp_path

    def test_extracts_class(self, java_file):
        from project_graph_mapper.parser.java_parser import JavaParser
        fpath, root = java_file
        parser = JavaParser()
        _, symbols = parser.parse_file(fpath, root)

        classes = [s for s in symbols if s.kind == SymbolKind.CLASS]
        assert any(s.name == "UserService" for s in classes)

    def test_extracts_interface(self, java_file):
        from project_graph_mapper.parser.java_parser import JavaParser
        fpath, root = java_file
        parser = JavaParser()
        _, symbols = parser.parse_file(fpath, root)

        interfaces = [s for s in symbols if s.kind == SymbolKind.INTERFACE]
        assert any(s.name == "UserRepository" for s in interfaces)

    def test_extracts_enum(self, java_file):
        from project_graph_mapper.parser.java_parser import JavaParser
        fpath, root = java_file
        parser = JavaParser()
        _, symbols = parser.parse_file(fpath, root)

        enums = [s for s in symbols if s.kind == SymbolKind.ENUM]
        assert any(s.name == "UserStatus" for s in enums)

    def test_extracts_methods(self, java_file):
        from project_graph_mapper.parser.java_parser import JavaParser
        fpath, root = java_file
        parser = JavaParser()
        _, symbols = parser.parse_file(fpath, root)

        methods = [s for s in symbols if s.kind == SymbolKind.METHOD]
        method_names = [m.name for m in methods]
        assert "findById" in method_names
        assert "deleteUser" in method_names

    def test_extracts_constructor(self, java_file):
        from project_graph_mapper.parser.java_parser import JavaParser
        fpath, root = java_file
        parser = JavaParser()
        _, symbols = parser.parse_file(fpath, root)

        methods = [s for s in symbols if s.kind == SymbolKind.METHOD]
        assert any(s.name == "UserService" for s in methods)  # constructor

    def test_extracts_imports(self, java_file):
        from project_graph_mapper.parser.java_parser import JavaParser
        fpath, root = java_file
        parser = JavaParser()
        file_node, _ = parser.parse_file(fpath, root)

        assert any("Database" in imp for imp in file_node.imports)
        assert any("User" in imp for imp in file_node.imports)


# ══════════════════════════════════════════════════════════════════════════════
# Registry
# ══════════════════════════════════════════════════════════════════════════════

class TestRegistry:

    def setup_method(self):
        clear_registry()

    def test_register_and_get_parser(self):
        from project_graph_mapper.parser.python_parser import PythonParser
        p = PythonParser()
        register(p)
        assert get_parser(Path("test.py")) is p

    def test_unsupported_extension_returns_none(self):
        assert get_parser(Path("test.xyz")) is None

    def test_supported_extensions_lists_all(self):
        from project_graph_mapper.parser.python_parser import PythonParser
        from project_graph_mapper.parser.go_parser import GoParser
        register(PythonParser())
        register(GoParser())
        exts = supported_extensions()
        assert ".py" in exts
        assert ".go" in exts


# ══════════════════════════════════════════════════════════════════════════════
# Multi-language GraphBuilder
# ══════════════════════════════════════════════════════════════════════════════

class TestMultiLangBuilder:

    @pytest.fixture
    def mixed_project(self, tmp_path: Path) -> Path:
        """Create a project with Python + Go + TypeScript files."""
        # Python
        (tmp_path / "utils").mkdir()
        (tmp_path / "utils" / "auth.py").write_text(textwrap.dedent("""\
            def validate_token(token: str) -> bool:
                return token.startswith("Bearer ")
        """), encoding="utf-8")

        # Go
        (tmp_path / "server").mkdir()
        (tmp_path / "server" / "main.go").write_text(textwrap.dedent("""\
            package main

            import "fmt"

            type Server struct {
                Port int
            }

            func NewServer(port int) *Server {
                return &Server{Port: port}
            }

            func (s *Server) Start() {
                fmt.Printf("Starting on port %d\\n", s.Port)
            }
        """), encoding="utf-8")

        # TypeScript
        (tmp_path / "frontend").mkdir()
        (tmp_path / "frontend" / "app.ts").write_text(textwrap.dedent("""\
            import { Router } from 'express';

            interface AppConfig {
                port: number;
            }

            function createApp(config: AppConfig) {
                return new Router();
            }

            export { createApp };
        """), encoding="utf-8")

        return tmp_path

    def test_detects_all_languages(self, mixed_project):
        builder = GraphBuilder().build(mixed_project)
        languages = {fnode.language for fnode in builder.files.values()}
        assert "python" in languages
        assert "go" in languages
        assert "typescript" in languages

    def test_finds_all_files(self, mixed_project):
        builder = GraphBuilder().build(mixed_project)
        assert len(builder.files) >= 3

    def test_finds_symbols_across_languages(self, mixed_project):
        builder = GraphBuilder().build(mixed_project)
        names = [sym.name for sym in builder.symbols.values()]
        assert "validate_token" in names  # Python
        assert "NewServer" in names       # Go
        assert "createApp" in names       # TypeScript

    def test_stats_include_all(self, mixed_project):
        builder = GraphBuilder().build(mixed_project)
        s = builder.stats
        assert s["total_files"] >= 3
        assert s["total_symbols"] >= 5  # at least some symbols from each language


class TestJsTsImportResolution:

    def test_relative_import_resolution(self):
        from project_graph_mapper.output.html_writer import _resolve_js_ts_import
        
        file_paths = {
            "src/utils/auth.ts",
            "src/services/user.ts",
            "src/components/button/index.tsx",
        }
        
        # Test relative import to file
        res = _resolve_js_ts_import("src/services/user.ts", "../utils/auth", file_paths, Path("."))
        assert res == "src/utils/auth.ts"
        
        # Test relative import to index file in folder
        res = _resolve_js_ts_import("src/services/user.ts", "../components/button", file_paths, Path("."))
        assert res == "src/components/button/index.tsx"

    def test_alias_and_baseurl_resolution(self, tmp_path: Path):
        from project_graph_mapper.output.html_writer import _resolve_js_ts_import
        
        # Write temporary tsconfig.json
        tsconfig = tmp_path / "tsconfig.json"
        tsconfig.write_text("""{
            "compilerOptions": {
                "baseUrl": "src",
                "paths": {
                    "@/components/*": ["components/*"],
                    "@services/*": ["services/*"]
                }
            }
        }""")
        
        file_paths = {
            "src/components/button.tsx",
            "src/services/user.ts",
            "src/utils/auth.ts",
        }
        
        # Test paths alias mapping
        res = _resolve_js_ts_import("src/app.ts", "@/components/button", file_paths, tmp_path)
        assert res == "src/components/button.tsx"
        
        # Test baseUrl fallback
        res = _resolve_js_ts_import("src/app.ts", "utils/auth", file_paths, tmp_path)
        assert res == "src/utils/auth.ts"

