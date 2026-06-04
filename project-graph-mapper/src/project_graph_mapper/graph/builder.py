from __future__ import annotations

from pathlib import Path

import networkx as nx

from .models import FileNode, Symbol
from ..parser.base import (
    BaseParser,
    clear_registry,
    get_parser,
    register,
    supported_extensions,
)

# Thư mục bỏ qua khi quét... Muốn bỏ gì thì thêm vào đây
SKIP_DIRS = {".venv", "venv", "__pycache__", ".git", ".pgm", "node_modules", ".tox", "dist", "build"}


def _init_registry(
    *,
    ai_extensions: list[str] | None = None,
    ai_api_key: str | None = None,
    ai_model: str = "claude-sonnet-4-20250514",
    cache_dir: Path | None = None,
) -> None:
    """Đăng ký tất cả parsers vào registry."""
    clear_registry()

    # ── Tree-sitter parsers ──────────────────────────────────────────────────
    from ..parser.python_parser import PythonParser
    from ..parser.js_parser import JavaScriptParser, TypeScriptParser, TSXParser
    from ..parser.go_parser import GoParser
    from ..parser.rust_parser import RustParser
    from ..parser.java_parser import JavaParser

    for parser_cls in [
        PythonParser, JavaScriptParser, TypeScriptParser,
        TSXParser, GoParser, RustParser, JavaParser,
    ]:
        register(parser_cls())

    # ── AI parser (opt-in) ───────────────────────────────────────────────────
    if ai_extensions:
        from ..parser.ai_parser import AiParser
        ai_parser = AiParser(
            ai_extensions=ai_extensions,
            api_key=ai_api_key,
            model=ai_model,
            cache_dir=cache_dir,
        )
        register(ai_parser)


class GraphBuilder:

    def __init__(
        self,
        *,
        ai_extensions: list[str] | None = None,
        ai_api_key: str | None = None,
        ai_model: str = "claude-sonnet-4-20250514",
    ) -> None:
        self.graph:   nx.DiGraph           = nx.DiGraph()
        self.symbols: dict[str, Symbol]    = {}
        self.files:   dict[str, FileNode]  = {}
        self._root:   Path | None          = None
        self._ai_extensions = ai_extensions
        self._ai_api_key = ai_api_key
        self._ai_model = ai_model

    def build(self, project_root: Path) -> GraphBuilder:
        self._root = project_root.resolve()

        _init_registry(
            ai_extensions=self._ai_extensions,
            ai_api_key=self._ai_api_key,
            ai_model=self._ai_model,
            cache_dir=self._root / ".pgm",
        )

        all_files = self._collect_files(project_root)

        # ── Pass 1: thu thập definitions
        for fpath in all_files:
            parser = get_parser(fpath)
            if parser is None:
                continue
            file_node, syms = parser.parse_file(fpath, self._root)
            file_node.language = file_node.language or parser.language_name()
            self.files[file_node.path] = file_node
            for sym in syms:
                self.symbols[sym.id] = sym
                self.graph.add_node(sym.id)

        # ── Pass 2: resolve call sites & xây edges
        for fpath in all_files:
            parser = get_parser(fpath)
            if parser is None:
                continue
            parser.resolve_calls(fpath, self._root, self.symbols)

        # ── Pass 3: back-populate `uses` cho caller symbols và xây edges đồ thị
        # Group symbols theo file để tra cứu nhanh
        symbols_by_file: dict[str, list[Symbol]] = {}
        for sym in self.symbols.values():
            symbols_by_file.setdefault(sym.loc.file, []).append(sym)

        # Sắp xếp các symbol trong mỗi file theo thứ tự dòng giảm dần để tìm kiếm nhanh
        for f_syms in symbols_by_file.values():
            f_syms.sort(key=lambda s: s.loc.line, reverse=True)

        for sym_id, sym in self.symbols.items():
            for call_site in sym.used_by:
                # Tìm caller symbol chứa dòng gọi này trong file gọi
                caller_sym = None
                f_syms = symbols_by_file.get(call_site.file, [])
                for fs in f_syms:
                    if fs.loc.line <= call_site.line:
                        caller_sym = fs
                        break

                if caller_sym:
                    # Tránh duplicate trong uses list
                    if sym_id not in caller_sym.uses:
                        caller_sym.uses.append(sym_id)
                    # Thêm edge thực tế giữa 2 symbols
                    self.graph.add_edge(caller_sym.id, sym_id)
                else:
                    # Fallback nếu dòng gọi ở ngoài phạm vi của bất kỳ symbol nào (ví dụ code chạy ở top-level)
                    caller_node = f"{call_site.file}::__caller__"
                    self.graph.add_edge(caller_node, sym_id)

        return self

    def update_file(self, filepath: Path) -> None:
        """Incremental update — chỉ re-parse 1 file, không rebuild toàn bộ."""
        import hashlib

        if self._root is None:
            raise RuntimeError("Gọi build() trước")

        parser = get_parser(filepath)
        if parser is None:
            return  # extension không hỗ trợ

        rel        = str(filepath.relative_to(self._root)).replace("\\", "/")
        new_hash   = hashlib.md5(filepath.read_bytes()).hexdigest()
        old_node   = self.files.get(rel)

        # Không thay đổi → bỏ qua
        if old_node and old_node.last_hash == new_hash:
            return

        # Xóa symbols cũ của file này
        for sid in (old_node.symbols if old_node else []):
            if self.graph.has_node(sid):
                self.graph.remove_node(sid)
            self.symbols.pop(sid, None)

        # Xóa edges từ file này (caller node)
        caller_node = f"{rel}::__caller__"
        if self.graph.has_node(caller_node):
            self.graph.remove_node(caller_node)

        # Xóa used_by entries của file này trong tất cả symbols
        for sym in self.symbols.values():
            sym.used_by = [cs for cs in sym.used_by if cs.file != rel]

        # Parse lại
        file_node, new_syms = parser.parse_file(filepath, self._root)
        file_node.language = file_node.language or parser.language_name()
        self.files[rel] = file_node

        for sym in new_syms:
            self.symbols[sym.id] = sym
            self.graph.add_node(sym.id)

        # Resolve calls cho file mới
        parser.resolve_calls(filepath, self._root, self.symbols)

        # Thêm edges mới
        for sym_id, sym in self.symbols.items():
            for cs in sym.used_by:
                if cs.file == rel:
                    self.graph.add_edge(f"{rel}::__caller__", sym_id)

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _collect_files(self, root: Path) -> list[Path]:
        """Scan tất cả extensions đã đăng ký."""
        result: list[Path] = []
        for ext in supported_extensions():
            for fpath in root.rglob(f"*{ext}"):
                if any(skip in fpath.parts for skip in SKIP_DIRS):
                    continue
                result.append(fpath)
        return sorted(set(result))

    # ── Stats ────────────────────────────────────────────────────────────────

    @property
    def stats(self) -> dict:
        return {
            "total_files":   len(self.files),
            "total_symbols": len(self.symbols),
            "total_edges":   self.graph.number_of_edges(),
        }
