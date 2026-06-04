import networkx as nx

from .models import Symbol


class QueryEngine:

    def __init__(self, graph: nx.DiGraph, symbols: dict[str, Symbol]):
        self.graph   = graph
        self.symbols = symbols

    # ── Impact ───────────────────────────────────────────────────────────────

    def impact(self, symbol_name: str) -> dict:
        """
        Trả về impact report đầy đủ cho một symbol:
        - direct_callers     : list[CallSite] — ai gọi trực tiếp
        - direct_files       : list[str]      — file gọi trực tiếp
        - transitive_files   : list[str]      — file bị ảnh hưởng gián tiếp
        - impact_score       : int            — tổng số file bị ảnh hưởng
        - checklist          : list[str]      — action items
        """
        matches = [sid for sid, sym in self.symbols.items() if sym.name == symbol_name]

        if not matches:
            return {"error": f"Không tìm thấy symbol '{symbol_name}'"}

        if len(matches) > 1:
            # Nhiều symbol cùng tên → trả về tất cả để user chọn
            return {
                "ambiguous": True,
                "matches": [
                    {"id": sid, "file": self.symbols[sid].loc.file, "line": self.symbols[sid].loc.line}
                    for sid in matches
                ],
            }

        sym_id = matches[0]
        sym    = self.symbols[sym_id]

        # BFS ngược: tìm tất cả nodes có đường đi đến sym_id
        try:
            transitive_nodes = nx.ancestors(self.graph, sym_id)
        except nx.NetworkXError:
            transitive_nodes = set()

        direct_files = list({cs.file for cs in sym.used_by})

        transitive_files = list({
            self.symbols[t].loc.file
            for t in transitive_nodes
            if t in self.symbols
        } - set(direct_files))

        return {
            "symbol":           sym,
            "symbol_id":        sym_id,
            "direct_callers":   sym.used_by,
            "direct_files":     direct_files,
            "transitive_files": transitive_files,
            "impact_score":     len(direct_files) + len(transitive_files),
            "checklist":        self._build_checklist(sym, direct_files, transitive_files),
        }

    def impact_by_id(self, symbol_id: str) -> dict:
        """Giống impact() nhưng dùng full symbol ID để tránh ambiguous."""
        if symbol_id not in self.symbols:
            return {"error": f"Không tìm thấy symbol ID '{symbol_id}'"}
        sym = self.symbols[symbol_id]
        return self.impact(sym.name)

    # ── Hotspots ─────────────────────────────────────────────────────────────

    def hotspots(self, top_n: int = 10) -> list[tuple[str, int]]:
        """Symbols có nhiều file phụ thuộc nhất — dễ gây breaking change."""
        scores = []
        for sid, sym in self.symbols.items():
            try:
                score = len(nx.ancestors(self.graph, sid))
            except Exception:
                score = len(sym.used_by)
            if score > 0:
                scores.append((sid, score))
        return sorted(scores, key=lambda x: x[1], reverse=True)[:top_n]

    # ── Cycles ───────────────────────────────────────────────────────────────

    def cycles(self) -> list[list[str]]:
        """Tìm circular imports trong graph."""
        return list(nx.simple_cycles(self.graph))

    # ── Dead Code ────────────────────────────────────────────────────────────

    def dead_code(self) -> list[str]:
        """Tìm các symbol không có incoming edge (0 call sites) và không phải entry point."""
        dead_symbols = []
        for sid, sym in self.symbols.items():
            if self.graph.has_node(sid):
                in_degree = self.graph.in_degree(sid)
                if in_degree == 0:
                    dead_symbols.append(sid)
        return sorted(dead_symbols)

    # ── Call Paths ───────────────────────────────────────────────────────────

    def call_paths(self, start_symbol: str, end_symbol: str) -> list[list[str]]:
        """Tìm tất cả các đường đi (call paths) từ start_symbol đến end_symbol."""
        start_matches = [sid for sid, sym in self.symbols.items() if sym.name == start_symbol]
        end_matches = [sid for sid, sym in self.symbols.items() if sym.name == end_symbol]
        
        if not start_matches or not end_matches:
            return []
            
        all_paths = []
        for start_id in start_matches:
            for end_id in end_matches:
                try:
                    paths = list(nx.all_simple_paths(self.graph, source=start_id, target=end_id))
                    all_paths.extend(paths)
                except Exception:
                    pass
        return all_paths


    # ── Helper ───────────────────────────────────────────────────────────────

    def _build_checklist(
        self,
        sym: Symbol,
        direct_files: list[str],
        transitive_files: list[str],
    ) -> list[str]:
        items = [f"Sửa code trong `{sym.loc.file}:{sym.loc.line}`"]

        for cs in sym.used_by:
            items.append(f"Kiểm tra `{cs.file}:{cs.line}` → `{cs.context[:60]}`")

        for f in transitive_files:
            items.append(f"[transitive] Xem lại `{f}`")

        test_files = [f for f in (direct_files + transitive_files) if "test" in f.lower()]
        if test_files:
            items.append(f"Chạy tests: {', '.join(f'`{f}`' for f in test_files)}")

        return items
