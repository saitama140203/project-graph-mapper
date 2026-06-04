from __future__ import annotations

import tree_sitter
import tree_sitter_rust

from .tree_sitter_base import TreeSitterParser
from ..graph.models import Location, Symbol, SymbolKind


class RustParser(TreeSitterParser):
    """Parser cho Rust — xử lý fn, struct, enum, trait, impl block."""

    def extensions(self) -> list[str]:
        return [".rs"]

    def _get_language(self) -> tree_sitter.Language:
        return tree_sitter.Language(tree_sitter_rust.language())

    def _extract_symbols(
        self,
        tree: tree_sitter.Tree,
        source: bytes,
        rel_path: str,
    ) -> list[Symbol]:
        symbols: list[Symbol] = []
        self._walk_top_level(tree.root_node, source, rel_path, symbols)
        return symbols

    def _walk_top_level(
        self,
        node: tree_sitter.Node,
        source: bytes,
        rel_path: str,
        symbols: list[Symbol],
    ) -> None:
        for child in node.children:
            match child.type:
                case "function_item":
                    name_node = child.child_by_field_name("name")
                    if name_node:
                        symbols.append(self._make_sym(
                            child, name_node, source, rel_path,
                            kind=SymbolKind.FUNCTION,
                        ))

                case "struct_item":
                    name_node = child.child_by_field_name("name")
                    if name_node:
                        symbols.append(self._make_sym(
                            child, name_node, source, rel_path,
                            kind=SymbolKind.STRUCT,
                        ))

                case "enum_item":
                    name_node = child.child_by_field_name("name")
                    if name_node:
                        symbols.append(self._make_sym(
                            child, name_node, source, rel_path,
                            kind=SymbolKind.ENUM,
                        ))

                case "trait_item":
                    name_node = child.child_by_field_name("name")
                    if name_node:
                        symbols.append(self._make_sym(
                            child, name_node, source, rel_path,
                            kind=SymbolKind.TRAIT,
                        ))

                case "impl_item":
                    self._extract_impl(child, source, rel_path, symbols)

                case "const_item":
                    name_node = child.child_by_field_name("name")
                    if name_node:
                        symbols.append(self._make_sym(
                            child, name_node, source, rel_path,
                            kind=SymbolKind.CONSTANT,
                        ))

                case _:
                    pass

    def _extract_impl(
        self,
        impl_node: tree_sitter.Node,
        source: bytes,
        rel_path: str,
        symbols: list[Symbol],
    ) -> None:
        """Extract methods từ impl block.

        `impl Config { fn new() ... }` → symbol id = `file.rs::Config.new`
        `impl Display for Config { fn fmt() }` → `file.rs::Config.fmt`
        """
        # Tìm type name cho impl
        impl_type_name = self._get_impl_type_name(impl_node)

        # Tạo symbol cho impl block chính nó
        if impl_type_name:
            impl_sym = Symbol(
                id=f"{rel_path}::impl_{impl_type_name}",
                name=f"impl {impl_type_name}",
                kind=SymbolKind.IMPL,
                loc=Location(
                    file=rel_path,
                    line=impl_node.start_point.row + 1,
                ),
                signature=self._node_first_line(impl_node, source),
            )
            symbols.append(impl_sym)

        # Extract methods bên trong impl body
        body = impl_node.child_by_field_name("body")
        if not body:
            return

        for child in body.children:
            if child.type == "function_item":
                name_node = child.child_by_field_name("name")
                if name_node:
                    symbols.append(self._make_sym(
                        child, name_node, source, rel_path,
                        kind=SymbolKind.METHOD,
                        class_name=impl_type_name,
                    ))

    def _get_impl_type_name(self, impl_node: tree_sitter.Node) -> str | None:
        """Extract type name từ impl node.

        `impl Config { ... }` → 'Config'
        `impl Display for Config { ... }` → 'Config'
        `impl<T> Handler<T> { ... }` → 'Handler'
        """
        type_node = impl_node.child_by_field_name("type")
        if type_node:
            # type có thể là type_identifier hoặc generic_type
            if type_node.type == "type_identifier":
                return self._node_text(type_node)
            if type_node.type == "generic_type":
                # Generic<T> → lấy tên base
                type_ident = type_node.child_by_field_name("type")
                if type_ident:
                    return self._node_text(type_ident)
                # Fallback: first child
                if type_node.children:
                    return self._node_text(type_node.children[0])
        # Nếu là trait impl: `impl Trait for Type`
        # tree-sitter-rust: trait=... type=...
        trait_node = impl_node.child_by_field_name("trait")
        if trait_node and type_node:
            if type_node.type == "type_identifier":
                return self._node_text(type_node)
        return None

    def _extract_imports(
        self,
        tree: tree_sitter.Tree,
        source: bytes,
    ) -> list[str]:
        imports: list[str] = []
        for child in tree.root_node.children:
            if child.type == "use_declaration":
                # use std::io::Read → "std::io::Read"
                arg = child.child_by_field_name("argument")
                if arg:
                    imports.append(self._node_text(arg))
                else:
                    # Fallback: toàn bộ text trừ "use " và ";"
                    text = self._node_text(child)
                    text = text.removeprefix("use ").removesuffix(";").strip()
                    if text:
                        imports.append(text)
        return imports

    # ── Rust-specific call resolution ────────────────────────────────────────

    def _find_calls(self, node: tree_sitter.Node) -> list[tree_sitter.Node]:
        """Rust dùng call_expression."""
        results: list[tree_sitter.Node] = []
        if node.type == "call_expression":
            results.append(node)
        for child in node.children:
            results.extend(self._find_calls(child))
        return results

    def _get_callee_name(self, call_node: tree_sitter.Node) -> str | None:
        """Extract callee: `greet("world")`, `config.start()`, `Config::new()`."""
        func = call_node.child_by_field_name("function")
        if func is None:
            return None

        if func.type == "identifier":
            return self._node_text(func)
        if func.type == "field_expression":
            field = func.child_by_field_name("field")
            if field:
                return self._node_text(field)
        if func.type == "scoped_identifier":
            name = func.child_by_field_name("name")
            if name:
                return self._node_text(name)
        return None
