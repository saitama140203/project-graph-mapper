from __future__ import annotations

from pathlib import Path

import tree_sitter
import tree_sitter_javascript
import tree_sitter_typescript

from .tree_sitter_base import TreeSitterParser
from ..graph.models import Location, Symbol, SymbolKind


# ── JavaScript ───────────────────────────────────────────────────────────────

class JavaScriptParser(TreeSitterParser):

    def extensions(self) -> list[str]:
        return [".js", ".mjs", ".cjs"]

    def _get_language(self) -> tree_sitter.Language:
        return tree_sitter.Language(tree_sitter_javascript.language())

    def _extract_symbols(
        self,
        tree: tree_sitter.Tree,
        source: bytes,
        rel_path: str,
    ) -> list[Symbol]:
        symbols: list[Symbol] = []
        self._walk_symbols(tree.root_node, source, rel_path, symbols, class_name=None)
        return symbols

    def _walk_symbols(
        self,
        node: tree_sitter.Node,
        source: bytes,
        rel_path: str,
        symbols: list[Symbol],
        *,
        class_name: str | None,
    ) -> None:
        for child in node.children:
            match child.type:
                case "function_declaration":
                    name_node = child.child_by_field_name("name")
                    if name_node:
                        sym = self._make_symbol(
                            child, name_node, source, rel_path,
                            kind=SymbolKind.FUNCTION,
                        )
                        symbols.append(sym)

                case "class_declaration":
                    name_node = child.child_by_field_name("name")
                    if name_node:
                        cls_name = self._node_text(name_node)
                        sym = self._make_symbol(
                            child, name_node, source, rel_path,
                            kind=SymbolKind.CLASS,
                        )
                        symbols.append(sym)
                        # Descend into class body for methods
                        body = child.child_by_field_name("body")
                        if body:
                            self._walk_symbols(
                                body, source, rel_path, symbols,
                                class_name=cls_name,
                            )

                case "method_definition":
                    name_node = child.child_by_field_name("name")
                    if name_node:
                        sym = self._make_symbol(
                            child, name_node, source, rel_path,
                            kind=SymbolKind.METHOD,
                            class_name=class_name,
                        )
                        symbols.append(sym)

                case "lexical_declaration" | "variable_declaration":
                    # const foo = () => {} hoặc const foo = function() {}
                    for decl in self._find_children_by_type(child, "variable_declarator"):
                        name_n = decl.child_by_field_name("name")
                        value_n = decl.child_by_field_name("value")
                        if name_n and value_n and value_n.type in (
                            "arrow_function", "function_expression",
                        ):
                            sym = self._make_symbol(
                                child, name_n, source, rel_path,
                                kind=SymbolKind.FUNCTION,
                            )
                            symbols.append(sym)

                case "export_statement":
                    # export function / export class / export const
                    self._walk_symbols(
                        child, source, rel_path, symbols,
                        class_name=class_name,
                    )

                case _:
                    pass

    def _extract_imports(
        self,
        tree: tree_sitter.Tree,
        source: bytes,
    ) -> list[str]:
        imports: list[str] = []
        for node in self._find_children_by_type(tree.root_node, "import_statement", recursive=True):
            src = node.child_by_field_name("source")
            if src:
                raw = self._node_text(src).strip("\"'`")
                imports.append(raw)
        # Also handle require()
        for node in self._find_children_by_type(
            tree.root_node, "call_expression", recursive=True
        ):
            func = node.child_by_field_name("function")
            if func and self._node_text(func) == "require":
                args = node.child_by_field_name("arguments")
                if args and args.children:
                    for arg in args.children:
                        if arg.type == "string":
                            imports.append(self._node_text(arg).strip("\"'`"))
        return imports


# ── TypeScript ───────────────────────────────────────────────────────────────

class TypeScriptParser(JavaScriptParser):
    """TypeScript parser — extends JavaScript with interface/enum support."""

    def extensions(self) -> list[str]:
        return [".ts"]

    def _get_language(self) -> tree_sitter.Language:
        return tree_sitter.Language(tree_sitter_typescript.language_typescript())

    def _walk_symbols(
        self,
        node: tree_sitter.Node,
        source: bytes,
        rel_path: str,
        symbols: list[Symbol],
        *,
        class_name: str | None,
    ) -> None:
        # Xử lý TypeScript-specific nodes trước
        for child in node.children:
            match child.type:
                case "interface_declaration":
                    name_node = child.child_by_field_name("name")
                    if name_node:
                        sym = self._make_symbol(
                            child, name_node, source, rel_path,
                            kind=SymbolKind.INTERFACE,
                        )
                        symbols.append(sym)

                case "enum_declaration":
                    name_node = child.child_by_field_name("name")
                    if name_node:
                        sym = self._make_symbol(
                            child, name_node, source, rel_path,
                            kind=SymbolKind.ENUM,
                        )
                        symbols.append(sym)

                case "type_alias_declaration":
                    # type Foo = ... → treat as interface
                    name_node = child.child_by_field_name("name")
                    if name_node:
                        sym = self._make_symbol(
                            child, name_node, source, rel_path,
                            kind=SymbolKind.INTERFACE,
                        )
                        symbols.append(sym)

                case _:
                    pass

        # Delegate to JS parser for functions/classes/methods
        super()._walk_symbols(
            node, source, rel_path, symbols,
            class_name=class_name,
        )


# ── TSX ──────────────────────────────────────────────────────────────────────

class TSXParser(TypeScriptParser):
    """TSX/JSX parser — same as TypeScript but for .tsx/.jsx files."""

    def extensions(self) -> list[str]:
        return [".tsx", ".jsx"]

    def _get_language(self) -> tree_sitter.Language:
        return tree_sitter.Language(tree_sitter_typescript.language_tsx())
