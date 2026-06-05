from __future__ import annotations

import ast
import hashlib
from pathlib import Path

from ..graph.models import CallSite, FileNode, Location, Symbol, SymbolKind
from .base import BaseParser


class PythonParser(BaseParser):
    def extensions(self) -> list[str]:
        return [".py"]

    def engine_name(self) -> str:
        return "ast"

    def parse_file(self, filepath: Path, root: Path) -> tuple[FileNode, list[Symbol]]:
        rel = str(filepath.relative_to(root)).replace("\\", "/")
        source = filepath.read_text(encoding="utf-8", errors="ignore")

        try:
            tree = ast.parse(source)
        except SyntaxError:
            return FileNode(path=rel, language="python"), []

        file_node = FileNode(
            path=rel,
            last_hash=hashlib.md5(source.encode()).hexdigest(),
            language="python",
        )
        symbols: list[Symbol] = []

        # ── Thu thập imports ────────────────────────────────────────────────
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                file_node.imports.append(node.module.replace(".", "/"))
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    file_node.imports.append(alias.name.replace(".", "/"))

        # ── Thu thập definitions (top-level và bên trong class) ─────────────
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                sym = self._extract_class(node, rel, source)
                symbols.append(sym)
                file_node.symbols.append(sym.id)
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        method = self._extract_function(item, rel, source, class_name=node.name)
                        symbols.append(method)
                        file_node.symbols.append(method.id)

            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # bỏ qua method (đã xử lý bên trên)
                if self._is_top_level(node, tree):
                    sym = self._extract_function(node, rel, source)
                    symbols.append(sym)
                    file_node.symbols.append(sym.id)

        return file_node, symbols

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _is_top_level(self, node: ast.AST, tree: ast.Module) -> bool:
        """Kiểm tra function có phải top-level không (không nằm trong class)."""
        for parent in ast.walk(tree):
            if isinstance(parent, ast.ClassDef):
                for child in ast.walk(parent):
                    if child is node:
                        return False
        return True

    def _extract_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        rel_path: str,
        source: str,
        class_name: str | None = None,
    ) -> Symbol:
        prefix = f"{class_name}." if class_name else ""
        sym_id = f"{rel_path}::{prefix}{node.name}"
        lines = source.splitlines()
        sig = lines[node.lineno - 1].strip() if node.lineno <= len(lines) else ""
        doc = (ast.get_docstring(node) or "")[:200]

        return Symbol(
            id=sym_id,
            name=node.name,
            kind=SymbolKind.METHOD if class_name else SymbolKind.FUNCTION,
            loc=Location(file=rel_path, line=node.lineno),
            signature=sig,
            docstring=doc,
        )

    def _extract_class(self, node: ast.ClassDef, rel_path: str, source: str) -> Symbol:
        lines = source.splitlines()
        sig = lines[node.lineno - 1].strip() if node.lineno <= len(lines) else ""
        doc = (ast.get_docstring(node) or "")[:200]

        return Symbol(
            id=f"{rel_path}::{node.name}",
            name=node.name,
            kind=SymbolKind.CLASS,
            loc=Location(file=rel_path, line=node.lineno),
            signature=sig,
            docstring=doc,
        )

    # ── Resolve call sites (dùng sau khi có đủ symbol map) ──────────────────

    def resolve_calls(
        self,
        filepath: Path,
        root: Path,
        all_symbols: dict[str, "Symbol"],
    ) -> None:
        """
        Scan lại file, tìm Call nodes, điền vào used_by của symbol được gọi.
        Gọi method này sau khi build() đã parse tất cả file.
        """
        rel = str(filepath.relative_to(root)).replace("\\", "/")
        source = filepath.read_text(encoding="utf-8", errors="ignore")

        try:
            tree = ast.parse(source)
        except SyntaxError:
            return

        lines = source.splitlines()

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue

            callee_name = self._get_call_name(node.func)
            if not callee_name:
                continue

            ctx = lines[node.lineno - 1].strip() if node.lineno <= len(lines) else ""

            for sym_id, sym in all_symbols.items():
                # Tên khớp, không phải gọi chính mình
                if sym.name == callee_name and not sym_id.startswith(rel + "::"):
                    # Tránh duplicate
                    already = any(cs.file == rel and cs.line == node.lineno for cs in sym.used_by)
                    if not already:
                        sym.used_by.append(CallSite(file=rel, line=node.lineno, context=ctx))

    def _get_call_name(self, node: ast.expr) -> str | None:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return node.attr
        return None
