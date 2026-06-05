from __future__ import annotations

import tree_sitter
import tree_sitter_c_sharp

from ..graph.models import Symbol, SymbolKind
from .tree_sitter_base import TreeSitterParser


class CSharpParser(TreeSitterParser):
    """Parser cho C# — class, interface, struct, record, enum, method, property, import."""

    def extensions(self) -> list[str]:
        return [".cs"]

    def _get_language(self) -> tree_sitter.Language:
        return tree_sitter.Language(tree_sitter_c_sharp.language())

    def _extract_symbols(
        self,
        tree: tree_sitter.Tree,
        source: bytes,
        rel_path: str,
    ) -> list[Symbol]:
        symbols: list[Symbol] = []
        self._walk_declarations(
            tree.root_node,
            source,
            rel_path,
            symbols,
            namespace=None,
            class_name=None,
        )
        return symbols

    def _walk_declarations(
        self,
        node: tree_sitter.Node,
        source: bytes,
        rel_path: str,
        symbols: list[Symbol],
        *,
        namespace: str | None,
        class_name: str | None,
    ) -> None:
        for child in node.children:
            match child.type:
                case "namespace_declaration" | "file_scoped_namespace_declaration":
                    name_node = child.child_by_field_name("name")
                    if name_node:
                        ns_name = self._node_text(name_node)
                        new_ns = f"{namespace}.{ns_name}" if namespace else ns_name
                        self._walk_declarations(
                            child,
                            source,
                            rel_path,
                            symbols,
                            namespace=new_ns,
                            class_name=class_name,
                        )
                case (
                    "class_declaration"
                    | "interface_declaration"
                    | "struct_declaration"
                    | "record_declaration"
                ):
                    name_node = child.child_by_field_name("name")
                    if name_node:
                        cls_name = self._node_text(name_node)
                        full_cls_name = f"{namespace}.{cls_name}" if namespace else cls_name

                        kind = SymbolKind.CLASS
                        if child.type == "interface_declaration":
                            kind = SymbolKind.INTERFACE
                        elif child.type == "struct_declaration":
                            kind = SymbolKind.STRUCT

                        symbols.append(
                            self._make_sym(
                                child,
                                name_node,
                                source,
                                rel_path,
                                kind=kind,
                            )
                        )
                        # The body is either in declaration_list or body
                        body = child.child_by_field_name("body") or child.child_by_field_name(
                            "declaration_list"
                        )
                        # If not found by field name, let's just search for declaration_list child
                        if not body:
                            for c in child.children:
                                if c.type == "declaration_list":
                                    body = c
                                    break

                        if body:
                            self._walk_declarations(
                                body,
                                source,
                                rel_path,
                                symbols,
                                namespace=namespace,
                                class_name=full_cls_name,
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

                case "method_declaration" | "constructor_declaration" | "property_declaration":
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

                case "compilation_unit" | "declaration_list":
                    self._walk_declarations(
                        child,
                        source,
                        rel_path,
                        symbols,
                        namespace=namespace,
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
            if child.type == "using_directive":
                # Find the identifier or qualified_name inside the using directive
                # It might be child_by_field_name("name") or just the 2nd child.
                name_node = child.child_by_field_name("name")
                if name_node:
                    imports.append(self._node_text(name_node))
                else:
                    for c in child.children:
                        if c.type in ("identifier", "qualified_name"):
                            imports.append(self._node_text(c))
        return imports

    # ── C# call resolution ───────────────────────────────────────────────────

    def _find_calls(self, node: tree_sitter.Node) -> list[tree_sitter.Node]:
        """C# uses invocation_expression and object_creation_expression."""
        results: list[tree_sitter.Node] = []
        if node.type == "invocation_expression":
            results.append(node)
        elif node.type == "object_creation_expression":
            results.append(node)
        for child in node.children:
            results.extend(self._find_calls(child))
        return results

    def _get_callee_name(self, call_node: tree_sitter.Node) -> str | None:
        """Extract callee: `service.Call()` → 'Call', `new MyObject()` → 'MyObject'."""
        if call_node.type == "invocation_expression":
            # the callee is the first child (or function field)
            func = call_node.child_by_field_name("function")
            if not func and call_node.children:
                func = call_node.children[0]

            if func:
                if func.type == "identifier":
                    return self._node_text(func)
                if func.type == "member_access_expression":
                    name_node = func.child_by_field_name("name")
                    if name_node:
                        return self._node_text(name_node)
                    # fallback
                    for c in reversed(func.children):
                        if c.type == "identifier":
                            return self._node_text(c)
        elif call_node.type == "object_creation_expression":
            type_node = call_node.child_by_field_name("type")
            if not type_node:
                for c in call_node.children:
                    if c.type in ("identifier", "generic_name"):
                        type_node = c
                        break

            if type_node:
                if type_node.type == "identifier":
                    return self._node_text(type_node)
                if type_node.type == "generic_name":
                    # For generic types like List<int>, the class name is usually the first identifier
                    for c in type_node.children:
                        if c.type == "identifier":
                            return self._node_text(c)
        return None
