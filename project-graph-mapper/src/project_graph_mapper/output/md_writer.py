from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path

import networkx as nx

from ..graph.models import FileNode, Symbol
from ..graph.query import QueryEngine
from ..parser.base import get_parser


class MarkdownWriter:

    # ── CONTEXT.md — overview toàn project ───────────────────────────────────

    def write_context(
        self,
        files:   dict[str, FileNode],
        symbols: dict[str, Symbol],
        graph:   nx.DiGraph,
        output_path: Path,
    ) -> Path:
        qe   = QueryEngine(graph, symbols)
        now  = datetime.now().strftime("%Y-%m-%d %H:%M")
        lines: list[str] = []

        lines += [
            f"# Project Context Snapshot",
            f"",
            f"> Generated: {now}  |  Files: {len(files)}  |  Symbols: {len(symbols)}",
            f"",
            f"---",
            f"",
        ]

        # ── Language breakdown ────────────────────────────────────────────────
        lines += self._language_breakdown(files)

        # ── Entry points ─────────────────────────────────────────────────────
        lines += ["## Entry points", ""]
        all_imports = {imp for f in files.values() for imp in f.imports}
        entries = sorted([
            f for f in files
            if f.replace("/", ".").rstrip(".py") not in all_imports
            and not f.startswith("test")
        ])
        for e in entries[:15]:
            sym_count = len(files[e].symbols)
            lines.append(f"- `{e}` ({sym_count} symbols)")
        lines.append("")

        # ── Hotspot symbols ───────────────────────────────────────────────────
        lines += ["## Hotspot symbols (top 10 by impact)", ""]
        lines += [
            "| Symbol | File | Line | Callers | Kind |",
            "|--------|------|------|---------|------|",
        ]
        for sid, score in qe.hotspots(10):
            sym = symbols[sid]
            lines.append(
                f"| `{sym.name}` | `{sym.loc.file}` | {sym.loc.line} | {score} | {sym.kind.value} |"
            )
        lines.append("")

        # ── File overview ─────────────────────────────────────────────────────
        lines += ["## File overview", ""]
        lines += [
            "| File | Symbols | Imports |",
            "|------|---------|---------|",
        ]
        for path, fnode in sorted(files.items()):
            lines.append(f"| `{path}` | {len(fnode.symbols)} | {len(fnode.imports)} |")
        lines.append("")

        # ── Circular dependencies ─────────────────────────────────────────────
        lines += ["## Circular dependencies", ""]
        cycles = qe.cycles()
        if cycles:
            for c in cycles[:5]:
                lines.append(f"- {' → '.join(c)}")
        else:
            lines.append("_Không có circular dependency_ ✓")
        lines.append("")

        output_path.write_text("\n".join(lines), encoding="utf-8")
        return output_path

    # ── Impact report cho 1 symbol ────────────────────────────────────────────

    def write_impact(self, result: dict, output_path: Path) -> Path:
        if "error" in result:
            output_path.write_text(f"# Error\n\n{result['error']}\n")
            return output_path

        sym: Symbol = result["symbol"]
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        lines: list[str] = []

        lines += [
            f"# Impact report: `{sym.name}()`",
            f"",
            f"> File: `{sym.loc.file}:{sym.loc.line}`  |  Generated: {now}",
            f">",
            f"> Signature: `{sym.signature}`",
            f"",
            f"---",
            f"",
            f"**Impact score: {result['impact_score']} file(s) bị ảnh hưởng**",
            f"",
        ]

        # ── Direct callers ────────────────────────────────────────────────────
        lines += [
            f"## Direct callers ({len(result['direct_callers'])})",
            "",
            "| File | Line | Context |",
            "|------|------|---------|",
        ]
        for cs in result["direct_callers"]:
            ctx = cs.context.replace("|", "\\|")[:80]
            lines.append(f"| `{cs.file}` | {cs.line} | `{ctx}` |")
        lines.append("")

        # ── Transitive files ──────────────────────────────────────────────────
        if result["transitive_files"]:
            lines += [f"## Transitive files ({len(result['transitive_files'])})", ""]
            for f in sorted(result["transitive_files"]):
                lines.append(f"- `{f}`")
            lines.append("")

        # ── Docstring ─────────────────────────────────────────────────────────
        if sym.docstring:
            lines += ["## Docstring", "", f"> {sym.docstring}", ""]

        # ── Action checklist ──────────────────────────────────────────────────
        lines += ["## Action checklist", ""]
        for item in result["checklist"]:
            lines.append(f"- [ ] {item}")
        lines.append("")

        output_path.write_text("\n".join(lines), encoding="utf-8")
        return output_path

    # ── Language breakdown helper ─────────────────────────────────────────────

    @staticmethod
    def _language_breakdown(files: dict[str, FileNode]) -> list[str]:
        """Tạo bảng language breakdown."""
        lang_files: Counter[str] = Counter()
        lang_symbols: Counter[str] = Counter()
        lang_engine: dict[str, str] = {}

        for fnode in files.values():
            lang = fnode.language or "unknown"
            lang_files[lang] += 1
            lang_symbols[lang] += len(fnode.symbols)

            # Xác định engine
            if lang not in lang_engine:
                if lang == "ai":
                    lang_engine[lang] = "AI"
                elif lang == "python":
                    lang_engine[lang] = "ast"
                else:
                    lang_engine[lang] = "tree-sitter"

        if not lang_files:
            return []

        lines = [
            "## Language breakdown", "",
            "| Language | Files | Symbols | Engine |",
            "|----------|-------|---------|--------|",
        ]
        for lang, count in lang_files.most_common():
            engine = lang_engine.get(lang, "tree-sitter")
            lines.append(
                f"| {lang.capitalize()} | {count} | {lang_symbols[lang]} | {engine} |"
            )
        lines.append("")

        return lines

    def write_mermaid(
        self,
        symbols: dict[str, Symbol],
        output_path: Path,
    ) -> Path:
        """Sinh file đồ thị dạng Mermaid biểu diễn call graph."""
        lines = ["graph TD"]
        
        connections = []
        connected_symbols = set()
        
        for sym_id, sym in symbols.items():
            for target_id in sym.uses:
                if target_id in symbols:
                    connections.append((sym_id, target_id))
                    connected_symbols.add(sym_id)
                    connected_symbols.add(target_id)

        files_map = {}
        for sid in connected_symbols:
            sym = symbols[sid]
            files_map.setdefault(sym.loc.file, []).append(sym)

        subgraph_id = 0
        for fpath, syms in sorted(files_map.items()):
            lines.append(f"    subgraph SUB{subgraph_id} [\"{fpath}\"]")
            for sym in syms:
                safe_id = sym.id.replace("/", "_").replace(".", "_").replace(":", "_").replace("-", "_")
                lines.append(f"        {safe_id}[\"{sym.name}()\"]")
            lines.append("    end")
            subgraph_id += 1

        for src, dest in sorted(connections):
            safe_src = src.replace("/", "_").replace(".", "_").replace(":", "_").replace("-", "_")
            safe_dest = dest.replace("/", "_").replace(".", "_").replace(":", "_").replace("-", "_")
            lines.append(f"    {safe_src} --> {safe_dest}")

        output_path.write_text("\n".join(lines), encoding="utf-8")
        return output_path


