from __future__ import annotations

import hashlib
from abc import abstractmethod
from pathlib import Path

import tree_sitter

from .base import BaseParser
from ..graph.models import CallSite, FileNode, Location, Symbol, SymbolKind


class TreeSitterParser(BaseParser):
    """Base class chung cho tất cả parsers dùng tree-sitter.

    Subclass chỉ cần implement:
      - extensions()
      - _get_language()     → tree_sitter.Language
      - _extract_symbols()  → list[Symbol] từ tree
      - _extract_imports()  → list[str] từ tree
    """

    def __init__(self) -> None:
        self._parser = tree_sitter.Parser(self._get_language())

    @abstractmethod
    def _get_language(self) -> tree_sitter.Language:
        """Trả về tree-sitter Language object."""
        ...

    @abstractmethod
    def _extract_symbols(
        self,
        tree: tree_sitter.Tree,
        source: bytes,
        rel_path: str,
    ) -> list[Symbol]:
        """Extract symbol definitions từ parse tree."""
        ...

    @abstractmethod
    def _extract_imports(
        self,
        tree: tree_sitter.Tree,
        source: bytes,
    ) -> list[str]:
        """Extract import paths từ parse tree."""
        ...

    def parse_file(self, filepath: Path, root: Path) -> tuple[FileNode, list[Symbol]]:
        """Parse file bằng tree-sitter, trả về FileNode + symbols."""
        rel = str(filepath.relative_to(root)).replace("\\", "/")
        source = filepath.read_bytes()

        tree = self._parser.parse(source)

        file_node = FileNode(
            path=rel,
            last_hash=hashlib.md5(source).hexdigest(),
            language=self.language_name(),
        )

        symbols = self._extract_symbols(tree, source, rel)
        file_node.symbols = [s.id for s in symbols]
        file_node.imports = self._extract_imports(tree, source)

        return file_node, symbols

    def resolve_calls(
        self,
        filepath: Path,
        root: Path,
        all_symbols: dict[str, Symbol],
    ) -> None:
        """Scan call expressions, điền vào used_by của symbols."""
        rel = str(filepath.relative_to(root)).replace("\\", "/")
        source = filepath.read_bytes()
        tree = self._parser.parse(source)
        lines = source.decode("utf-8", errors="ignore").splitlines()

        for call_node in self._find_calls(tree.root_node):
            callee_name = self._get_callee_name(call_node)
            if not callee_name:
                continue

            line_num = call_node.start_point.row + 1
            ctx = lines[line_num - 1].strip() if line_num <= len(lines) else ""

            for sym_id, sym in all_symbols.items():
                if sym.name == callee_name and not sym_id.startswith(f"{rel}::"):
                    already = any(cs.file == rel and cs.line == line_num for cs in sym.used_by)
                    if not already:
                        sym.used_by.append(CallSite(file=rel, line=line_num, context=ctx))

    # ── Helpers cho call resolution ──────────────────────────────────────────

    def _find_calls(self, node: tree_sitter.Node) -> list[tree_sitter.Node]:
        """Tìm tất cả call_expression nodes trong tree."""
        results: list[tree_sitter.Node] = []
        if node.type == "call_expression":
            results.append(node)
        for child in node.children:
            results.extend(self._find_calls(child))
        return results

    def _get_callee_name(self, call_node: tree_sitter.Node) -> str | None:
        """Extract tên function được gọi từ call_expression.

        Xử lý cả simple call `foo()` và member call `obj.foo()`.
        """
        func = call_node.child_by_field_name("function")
        if func is None:
            # Fallback: first child
            if call_node.children:
                func = call_node.children[0]
            else:
                return None

        if func.type == "identifier":
            return func.text.decode("utf-8")
        if func.type in ("member_expression", "field_expression"):
            # obj.method() → lấy "method"
            prop = func.child_by_field_name("property") or func.child_by_field_name("field")
            if prop:
                return prop.text.decode("utf-8")
        if func.type == "scoped_identifier":
            # Rust: Module::func()
            name = func.child_by_field_name("name")
            if name:
                return name.text.decode("utf-8")
        if func.type == "selector_expression":
            # Go: pkg.Func()
            field = func.child_by_field_name("field")
            if field:
                return field.text.decode("utf-8")
        return None

    # ── Utility ──────────────────────────────────────────────────────────────

    @staticmethod
    def _node_text(node: tree_sitter.Node) -> str:
        """Lấy text content của node."""
        return node.text.decode("utf-8")

    @staticmethod
    def _node_first_line(node: tree_sitter.Node, source: bytes) -> str:
        """Lấy dòng đầu tiên của node (dùng cho signature)."""
        line = source.decode("utf-8", errors="ignore").splitlines()[node.start_point.row]
        return line.strip()

    @staticmethod
    def _find_children_by_type(
        node: tree_sitter.Node,
        type_name: str,
        *,
        recursive: bool = False,
    ) -> list[tree_sitter.Node]:
        """Tìm children trực tiếp (hoặc đệ quy) có type cụ thể."""
        results: list[tree_sitter.Node] = []
        for child in node.children:
            if child.type == type_name:
                results.append(child)
            if recursive:
                results.extend(
                    TreeSitterParser._find_children_by_type(child, type_name, recursive=True)
                )
        return results

    def _extract_docstring(self, node: tree_sitter.Node, source: bytes) -> str:
        """Trích xuất comments/docstring liền trước một node."""
        parent = node.parent
        if not parent:
            return ""

        siblings = parent.children
        try:
            idx = siblings.index(node)
        except ValueError:
            return ""

        collected_comments = []
        current_node_start_row = node.start_point.row

        # Đi ngược từ sibling kề trước node
        for i in range(idx - 1, -1, -1):
            sibling = siblings[i]
            sib_type = sibling.type.lower()
            
            # Kiểm tra nếu là node comment
            is_comment = "comment" in sib_type or sib_type == "javadoc"
            if not is_comment:
                break
                
            # Đảm bảo khoảng cách dòng hợp lý (liền kề nhau, tối đa 1 dòng trống)
            distance = current_node_start_row - sibling.end_point.row
            if distance > 1:
                break
                
            # Trích xuất text
            text = sibling.text.decode("utf-8", errors="ignore").strip()
            # Dọn dẹp ký tự comment thông dụng
            lines = []
            for line in text.splitlines():
                line = line.strip()
                if line.startswith("//"):
                    line = line[2:]
                elif line.startswith("/*"):
                    line = line[2:]
                if line.endswith("*/"):
                    line = line[:-2]
                if line.startswith("*"):
                    line = line[1:]
                lines.append(line.strip())
            
            cleaned_text = "\n".join(lines).strip()
            if cleaned_text:
                collected_comments.insert(0, cleaned_text)
                
            # Cập nhật start row để kiểm tra sibling tiếp theo
            current_node_start_row = sibling.start_point.row

        return "\n".join(collected_comments)[:200]

    def _make_sym(
        self,
        decl_node: tree_sitter.Node,
        name_node: tree_sitter.Node,
        source: bytes,
        rel_path: str,
        *,
        kind: SymbolKind,
        class_name: str | None = None,
    ) -> Symbol:
        name = self._node_text(name_node)
        prefix = f"{class_name}." if class_name else ""
        sym_id = f"{rel_path}::{prefix}{name}"
        line = decl_node.start_point.row + 1
        sig = self._node_first_line(decl_node, source)
        doc = self._extract_docstring(decl_node, source)

        return Symbol(
            id=sym_id,
            name=name,
            kind=kind,
            loc=Location(file=rel_path, line=line),
            signature=sig,
            docstring=doc,
        )

    _make_symbol = _make_sym

