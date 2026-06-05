from __future__ import annotations

import tree_sitter
import tree_sitter_java

from ..graph.models import Symbol, SymbolKind
from .tree_sitter_base import TreeSitterParser


class JavaParser(TreeSitterParser):
    """Parser cho Java — class, interface, enum, method, import."""

    def extensions(self) -> list[str]:
        return [".java"]

    def _get_language(self) -> tree_sitter.Language:
        return tree_sitter.Language(tree_sitter_java.language())

    def _extract_symbols(
        self,
        tree: tree_sitter.Tree,
        source: bytes,
        rel_path: str,
    ) -> list[Symbol]:
        symbols: list[Symbol] = []
        self._walk_declarations(tree.root_node, source, rel_path, symbols, class_name=None)
        return symbols

    def _walk_declarations(
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
                case "class_declaration":
                    name_node = child.child_by_field_name("name")
                    if name_node:
                        cls_name = self._node_text(name_node)
                        symbols.append(
                            self._make_sym(
                                child,
                                name_node,
                                source,
                                rel_path,
                                kind=SymbolKind.CLASS,
                            )
                        )
                        body = child.child_by_field_name("body")
                        if body:
                            self._walk_declarations(
                                body,
                                source,
                                rel_path,
                                symbols,
                                class_name=cls_name,
                            )

                case "interface_declaration":
                    name_node = child.child_by_field_name("name")
                    if name_node:
                        iface_name = self._node_text(name_node)
                        symbols.append(
                            self._make_sym(
                                child,
                                name_node,
                                source,
                                rel_path,
                                kind=SymbolKind.INTERFACE,
                            )
                        )
                        body = child.child_by_field_name("body")
                        if body:
                            self._walk_declarations(
                                body,
                                source,
                                rel_path,
                                symbols,
                                class_name=iface_name,
                            )

                case "enum_declaration":
                    name_node = child.child_by_field_name("name")
                    if name_node:
                        symbols.append(
                            self._make_sym(
                                child,
                                name_node,
                                source,
                                rel_path,
                                kind=SymbolKind.ENUM,
                            )
                        )

                case "method_declaration":
                    name_node = child.child_by_field_name("name")
                    if name_node:
                        symbols.append(
                            self._make_sym(
                                child,
                                name_node,
                                source,
                                rel_path,
                                kind=SymbolKind.METHOD,
                                class_name=class_name,
                            )
                        )

                case "constructor_declaration":
                    name_node = child.child_by_field_name("name")
                    if name_node:
                        symbols.append(
                            self._make_sym(
                                child,
                                name_node,
                                source,
                                rel_path,
                                kind=SymbolKind.METHOD,
                                class_name=class_name,
                            )
                        )

                case "program":
                    # Top-level wrapper
                    self._walk_declarations(
                        child,
                        source,
                        rel_path,
                        symbols,
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
        for child in tree.root_node.children:
            if child.type == "import_declaration":
                # import com.example.Service; → "com.example.Service"
                # Lấy phần giữa "import " và ";"
                text = self._node_text(child)
                text = (
                    text.removeprefix("import ").removeprefix("static ").removesuffix(";").strip()
                )
                if text:
                    imports.append(text)
        return imports

    # ── Java call resolution ─────────────────────────────────────────────────

    def _find_calls(self, node: tree_sitter.Node) -> list[tree_sitter.Node]:
        """Java dùng method_invocation thay vì call_expression."""
        results: list[tree_sitter.Node] = []
        if node.type == "method_invocation":
            results.append(node)
        elif node.type == "object_creation_expression":
            results.append(node)
        for child in node.children:
            results.extend(self._find_calls(child))
        return results

    def _get_callee_name(self, call_node: tree_sitter.Node) -> str | None:
        """Extract callee: `service.call()` → 'call', `staticMethod()` → 'staticMethod'."""
        if call_node.type == "method_invocation":
            name_node = call_node.child_by_field_name("name")
            if name_node:
                return self._node_text(name_node)

        if call_node.type == "object_creation_expression":
            # new Foo() → Foo
            type_node = call_node.child_by_field_name("type")
            if type_node:
                if type_node.type == "type_identifier":
                    return self._node_text(type_node)
                # generic: new ArrayList<String>()
                ident = type_node.child_by_field_name("name")
                if ident:
                    return self._node_text(ident)
        return None
