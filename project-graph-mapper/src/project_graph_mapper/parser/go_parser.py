from __future__ import annotations

import tree_sitter
import tree_sitter_go

from .tree_sitter_base import TreeSitterParser
from ..graph.models import Location, Symbol, SymbolKind


class GoParser(TreeSitterParser):
    """Parser cho Go — xử lý func, method (receiver), struct, interface."""

    def extensions(self) -> list[str]:
        return [".go"]

    def _get_language(self) -> tree_sitter.Language:
        return tree_sitter.Language(tree_sitter_go.language())

    def _extract_symbols(
        self,
        tree: tree_sitter.Tree,
        source: bytes,
        rel_path: str,
    ) -> list[Symbol]:
        symbols: list[Symbol] = []

        for child in tree.root_node.children:
            match child.type:
                case "function_declaration":
                    name_node = child.child_by_field_name("name")
                    if name_node:
                        symbols.append(self._make_sym(
                            child, name_node, source, rel_path,
                            kind=SymbolKind.FUNCTION,
                        ))

                case "method_declaration":
                    name_node = child.child_by_field_name("name")
                    receiver = child.child_by_field_name("receiver")
                    if name_node:
                        recv_name = self._extract_receiver_type(receiver) if receiver else None
                        symbols.append(self._make_sym(
                            child, name_node, source, rel_path,
                            kind=SymbolKind.METHOD,
                            class_name=recv_name,
                        ))

                case "type_declaration":
                    # type_declaration chứa type_spec children
                    for spec in child.children:
                        if spec.type == "type_spec":
                            self._extract_type_spec(spec, source, rel_path, symbols)

                case "const_declaration":
                    for spec in child.children:
                        if spec.type == "const_spec":
                            name_node = spec.child_by_field_name("name")
                            if name_node:
                                symbols.append(self._make_sym(
                                    spec, name_node, source, rel_path,
                                    kind=SymbolKind.CONSTANT,
                                ))

                case _:
                    pass

        return symbols

    def _extract_type_spec(
        self,
        spec: tree_sitter.Node,
        source: bytes,
        rel_path: str,
        symbols: list[Symbol],
    ) -> None:
        """Extract type_spec: `type Server struct { ... }` hoặc `type Handler interface { ... }`."""
        name_node = spec.child_by_field_name("name")
        type_node = spec.child_by_field_name("type")
        if not name_node or not type_node:
            return

        match type_node.type:
            case "struct_type":
                kind = SymbolKind.STRUCT
            case "interface_type":
                kind = SymbolKind.INTERFACE
            case _:
                kind = SymbolKind.CLASS  # type alias, fallback

        symbols.append(self._make_sym(
            spec, name_node, source, rel_path,
            kind=kind,
        ))

    def _extract_receiver_type(self, receiver: tree_sitter.Node) -> str | None:
        """Extract receiver type từ `(s *Server)` → 'Server'."""
        # parameter_list → parameter_declaration → type
        for param in receiver.children:
            if param.type == "parameter_declaration":
                type_node = param.child_by_field_name("type")
                if type_node:
                    # Có thể là *Server (pointer_type) hoặc Server (type_identifier)
                    if type_node.type == "pointer_type":
                        for child in type_node.children:
                            if child.type == "type_identifier":
                                return self._node_text(child)
                    elif type_node.type == "type_identifier":
                        return self._node_text(type_node)
        return None

    def _extract_imports(
        self,
        tree: tree_sitter.Tree,
        source: bytes,
    ) -> list[str]:
        imports: list[str] = []
        for child in tree.root_node.children:
            if child.type == "import_declaration":
                for spec in self._find_children_by_type(child, "import_spec", recursive=True):
                    path_node = spec.child_by_field_name("path")
                    if path_node:
                        imports.append(self._node_text(path_node).strip('"'))
        return imports

    # ── Go-specific call resolution ──────────────────────────────────────────

    def _find_calls(self, node: tree_sitter.Node) -> list[tree_sitter.Node]:
        """Go dùng call_expression."""
        results: list[tree_sitter.Node] = []
        if node.type == "call_expression":
            results.append(node)
        for child in node.children:
            results.extend(self._find_calls(child))
        return results

    def _get_callee_name(self, call_node: tree_sitter.Node) -> str | None:
        """Extract callee từ Go call: `Add(1,2)` hoặc `s.Start()`."""
        func = call_node.child_by_field_name("function")
        if func is None:
            return None

        if func.type == "identifier":
            return self._node_text(func)
        if func.type == "selector_expression":
            field = func.child_by_field_name("field")
            if field:
                return self._node_text(field)
        return None
