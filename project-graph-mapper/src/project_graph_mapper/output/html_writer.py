from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from ..graph.models import FileNode, Symbol


class HtmlWriter:
    def write(
        self,
        files: dict[str, FileNode],
        symbols: dict[str, Symbol],
        output_path: Path,
    ) -> Path:
        # 1. Build Symbol Graph nodes and links
        symbol_nodes = []
        symbol_links = []

        # Keep track of existing symbols so we don't link to non-existent ones
        symbol_ids = set(symbols.keys())

        # Pre-calculate file languages for symbols
        symbol_languages = {}
        for file_path, file_node in files.items():
            for sym_id in file_node.symbols:
                symbol_languages[sym_id] = file_node.language

        # Build networkx graph to calculate cycles & hotspots
        import networkx as nx

        from ..graph.query import QueryEngine

        graph = nx.DiGraph()
        for sym_id in symbols.keys():
            graph.add_node(sym_id)
        for sym_id, sym in symbols.items():
            for target_id in sym.uses:
                if target_id in symbols:
                    graph.add_edge(sym_id, target_id)

        query_engine = QueryEngine(graph, symbols)
        cycles_list = query_engine.cycles()

        # Transform hotspots to readable format
        hotspots_list = []
        for sym_id, score in query_engine.hotspots(15):
            sym = symbols.get(sym_id)
            if sym:
                hotspots_list.append(
                    {
                        "id": sym_id,
                        "name": sym.name,
                        "kind": sym.kind.value,
                        "filepath": sym.loc.file,
                        "score": score,
                    }
                )

        project_root = output_path.parent.parent.resolve()

        for sym_id, sym in symbols.items():
            lang = symbol_languages.get(sym_id, "unknown")
            try:
                score = len(nx.ancestors(graph, sym_id))
            except Exception:
                score = len(sym.used_by)
            snippet = _get_code_snippet(project_root, sym.loc.file, sym.loc.line)

            symbol_nodes.append(
                {
                    "id": sym.id,
                    "name": sym.name,
                    "kind": sym.kind,
                    "filepath": sym.loc.file,
                    "line": sym.loc.line,
                    "signature": sym.signature,
                    "docstring": sym.docstring,
                    "language": lang,
                    "impact_score": score,
                    "code_snippet": snippet,
                }
            )

            # Add call links
            for target_id in sym.uses:
                if target_id in symbol_ids:
                    symbol_links.append({"source": sym.id, "target": target_id, "type": "call"})

        # 2. Build File Graph nodes and links
        file_nodes = []
        file_links = []
        file_paths = set(files.keys())

        # Keep track of file connections to prevent duplicate links
        file_connections = set()
        project_root = output_path.parent.parent.resolve()

        for f_path, file in files.items():
            file_nodes.append(
                {
                    "id": file.path,
                    "name": Path(file.path).name,
                    "language": file.language,
                    "total_symbols": len(file.symbols),
                }
            )

            # Map symbol calls to file level connections
            for sym_id in file.symbols:
                sym = symbols.get(sym_id)
                if not sym:
                    continue
                for target_id in sym.uses:
                    target_sym = symbols.get(target_id)
                    if target_sym and target_sym.loc.file != f_path:
                        other_file = target_sym.loc.file
                        if other_file in file_paths:
                            conn = (f_path, other_file)
                            if conn not in file_connections:
                                file_connections.add(conn)
                                file_links.append(
                                    {
                                        "source": f_path,
                                        "target": other_file,
                                        "type": "call-dependency",
                                    }
                                )

            # Also try to map imports directly if they match a file path
            # (Best effort module path resolution)
            for imp in file.imports:
                # ── JS/TS specific resolution with alias / relative path ──
                if file.language in ("javascript", "typescript", "tsx"):
                    resolved = _resolve_js_ts_import(f_path, imp, file_paths, project_root)
                    if resolved:
                        conn = (f_path, resolved)
                        if conn not in file_connections:
                            file_connections.add(conn)
                            file_links.append(
                                {"source": f_path, "target": resolved, "type": "import-dependency"}
                            )
                        continue

                # ── General fallback resolution (python, go, rust, java, etc.) ──
                imp_parts = imp.split(".")
                potential_suffixes = [".py", ".js", ".ts", ".go", ".rs", ".java"]

                # Check absolute matches in project structure
                for suffix in potential_suffixes:
                    # e.g., utils/auth.py
                    check_path = "/".join(imp_parts) + suffix
                    if check_path in file_paths:
                        conn = (f_path, check_path)
                        if conn not in file_connections:
                            file_connections.add(conn)
                            file_links.append(
                                {
                                    "source": f_path,
                                    "target": check_path,
                                    "type": "import-dependency",
                                }
                            )
                            break

        # Assemble the data payload
        parent_dir = output_path.parent.resolve()
        project_name = parent_dir.name
        if project_name.startswith(".") and parent_dir.parent:
            project_name = parent_dir.parent.name

        data_payload = {
            "project_name": project_name,
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "stats": {
                "total_files": len(files),
                "total_symbols": len(symbols),
            },
            "symbol_graph": {
                "nodes": symbol_nodes,
                "links": symbol_links,
            },
            "file_graph": {
                "nodes": file_nodes,
                "links": file_links,
            },
            "cycles": cycles_list,
            "hotspots": hotspots_list,
        }

        # Generate HTML content
        html_content = self._generate_html(data_payload)

        # Ensure output directory exists and write
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html_content, encoding="utf-8")
        return output_path

    def _generate_html(self, data: dict) -> str:
        import re

        data_json = json.dumps(data, indent=2, ensure_ascii=False)
        # Escape </script> inside JSON to prevent browser HTML parser from terminating the script tag early
        data_json = re.sub(r"(?i)</script>", r"<\/script>", data_json)
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PGM Interactive Graph Viewer - {data["project_name"]}</title>
    <!-- Inter & Fira Code Fonts -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500&family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    
    <!-- D3.js -->
    <script src="https://cdn.jsdelivr.net/npm/d3@7.9.0/dist/d3.min.js"></script>
    
    <style>
        :root {{
            --bg-color: #0b0f19;
            --panel-bg: rgba(22, 27, 34, 0.75);
            --panel-border: rgba(255, 255, 255, 0.08);
            --text-primary: #f3f4f6;
            --text-secondary: #9ca3af;
            --text-muted: #6b7280;
            --accent: #6366f1;
            --accent-hover: #4f46e5;
            
            /* Languages colors */
            --color-python: #3b82f6;
            --color-javascript: #eab308;
            --color-typescript: #2563eb;
            --color-go: #06b6d4;
            --color-rust: #f97316;
            --color-java: #ef4444;
            --color-ai: #a855f7;
            --color-unknown: #10b981;
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}

        body {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-primary);
            overflow: hidden;
            width: 100vw;
            height: 100vh;
        }}

        /* SVG Grid Background */
        #viewport {{
            width: 100%;
            height: 100%;
            display: block;
        }}

        .grid-line {{
            stroke: rgba(255, 255, 255, 0.02);
            stroke-width: 1;
        }}

        /* Floating Layout */
        .panel {{
            position: absolute;
            background-color: var(--panel-bg);
            border: 1px solid var(--panel-border);
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
            border-radius: 12px;
            padding: 20px;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);
            z-index: 10;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }}

        /* Left Control Panel */
        #control-panel {{
            top: 20px;
            left: 20px;
            width: 320px;
            max-height: calc(100vh - 40px);
            display: flex;
            flex-direction: column;
            gap: 16px;
            overflow-y: auto;
        }}

        /* Right Detail Panel */
        #detail-panel {{
            top: 20px;
            right: 20px;
            width: 380px;
            max-height: calc(100vh - 40px);
            overflow-y: auto;
            transform: translateX(420px);
            opacity: 0;
        }}

        #detail-panel.visible {{
            transform: translateX(0);
            opacity: 1;
        }}

        /* Panel Typography & Elements */
        h1 {{
            font-size: 1.25rem;
            font-weight: 700;
            letter-spacing: -0.025em;
            display: flex;
            align-items: center;
            gap: 8px;
        }}

        h2 {{
            font-size: 0.95rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: var(--text-secondary);
            margin-bottom: 8px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            padding-bottom: 4px;
        }}

        .subtitle {{
            font-size: 0.75rem;
            color: var(--text-muted);
        }}

        .search-box {{
            position: relative;
        }}

        .search-box input {{
            width: 100%;
            background: rgba(0, 0, 0, 0.2);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 8px;
            padding: 10px 12px 10px 36px;
            color: var(--text-primary);
            font-size: 0.875rem;
            outline: none;
            transition: border-color 0.2s, box-shadow 0.2s;
        }}

        .search-box input:focus {{
            border-color: var(--accent);
            box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.2);
        }}

        .search-box svg {{
            position: absolute;
            left: 10px;
            top: 50%;
            transform: translateY(-50%);
            width: 16px;
            height: 16px;
            fill: var(--text-muted);
        }}

        /* Button Group / Mode Toggle */
        .btn-group {{
            display: flex;
            background: rgba(0, 0, 0, 0.2);
            padding: 4px;
            border-radius: 8px;
            border: 1px solid rgba(255, 255, 255, 0.05);
        }}

        .btn-group button {{
            flex: 1;
            background: none;
            border: none;
            color: var(--text-secondary);
            font-size: 0.8rem;
            font-weight: 600;
            padding: 8px 12px;
            border-radius: 6px;
            cursor: pointer;
            transition: all 0.2s;
        }}

        .btn-group button.active {{
            background: var(--accent);
            color: var(--text-primary);
            box-shadow: 0 2px 8px rgba(99, 102, 241, 0.3);
        }}

        /* Filter Section */
        .filter-group {{
            display: flex;
            flex-direction: column;
            gap: 8px;
        }}

        .filter-item {{
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 0.875rem;
            cursor: pointer;
            user-select: none;
            color: var(--text-secondary);
        }}

        .filter-item:hover {{
            color: var(--text-primary);
        }}

        .filter-item input {{
            cursor: pointer;
            accent-color: var(--accent);
        }}

        /* Stats & Legend */
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 8px;
            text-align: center;
        }}

        .stat-card {{
            background: rgba(0, 0, 0, 0.15);
            padding: 8px;
            border-radius: 6px;
            border: 1px solid rgba(255, 255, 255, 0.03);
        }}

        .stat-val {{
            font-size: 1.1rem;
            font-weight: 700;
            color: var(--accent);
        }}

        .stat-lbl {{
            font-size: 0.65rem;
            color: var(--text-muted);
            text-transform: uppercase;
        }}

        .legend-list {{
            display: flex;
            flex-direction: column;
            gap: 6px;
            font-size: 0.8rem;
        }}

        .legend-row {{
            display: flex;
            align-items: center;
            gap: 8px;
        }}

        .legend-color {{
            width: 10px;
            height: 10px;
            border-radius: 50%;
        }}
        
        .legend-shape {{
            width: 10px;
            height: 10px;
            background-color: var(--text-secondary);
        }}
        
        .shape-circle {{ border-radius: 50%; }}
        .shape-square {{ border-radius: 2px; }}
        .shape-diamond {{ transform: rotate(45deg); width: 8px; height: 8px; margin: 1px; }}

        /* Node Details styles */
        .detail-header {{
            display: flex;
            flex-direction: column;
            gap: 4px;
            margin-bottom: 16px;
        }}

        .detail-title {{
            font-size: 1.15rem;
            font-weight: 700;
            word-break: break-all;
        }}

        .badge {{
            display: inline-block;
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 0.7rem;
            font-weight: 600;
            text-transform: uppercase;
            background: rgba(255, 255, 255, 0.1);
            width: fit-content;
        }}

        .badge-lang-python {{ background: rgba(59, 130, 246, 0.2); color: var(--color-python); border: 1px solid rgba(59, 130, 246, 0.3); }}
        .badge-lang-javascript {{ background: rgba(234, 208, 12, 0.2); color: var(--color-javascript); border: 1px solid rgba(234, 208, 12, 0.3); }}
        .badge-lang-typescript {{ background: rgba(37, 99, 235, 0.2); color: var(--color-typescript); border: 1px solid rgba(37, 99, 235, 0.3); }}
        .badge-lang-go {{ background: rgba(6, 182, 212, 0.2); color: var(--color-go); border: 1px solid rgba(6, 182, 212, 0.3); }}
        .badge-lang-rust {{ background: rgba(249, 115, 22, 0.2); color: var(--color-rust); border: 1px solid rgba(249, 115, 22, 0.3); }}
        .badge-lang-java {{ background: rgba(239, 68, 68, 0.2); color: var(--color-java); border: 1px solid rgba(239, 68, 68, 0.3); }}
        .badge-lang-ai {{ background: rgba(168, 85, 247, 0.2); color: var(--color-ai); border: 1px solid rgba(168, 85, 247, 0.3); }}
        .badge-lang-unknown {{ background: rgba(16, 185, 129, 0.2); color: var(--color-unknown); border: 1px solid rgba(16, 185, 129, 0.3); }}

        .detail-meta {{
            font-size: 0.8rem;
            color: var(--text-secondary);
            margin-bottom: 12px;
            display: flex;
            flex-direction: column;
            gap: 4px;
        }}

        .detail-meta span {{
            word-break: break-all;
        }}

        .code-sig {{
            font-family: 'Fira Code', monospace;
            background: rgba(0, 0, 0, 0.4);
            border: 1px solid rgba(255, 255, 255, 0.05);
            border-radius: 6px;
            padding: 8px;
            font-size: 0.75rem;
            overflow-x: auto;
            white-space: pre-wrap;
            word-break: break-all;
            margin-bottom: 12px;
            color: #e5e7eb;
        }}

        .docstring {{
            font-size: 0.8rem;
            color: var(--text-secondary);
            line-height: 1.4;
            background: rgba(255, 255, 255, 0.02);
            border-left: 2px solid var(--accent);
            padding: 6px 10px;
            border-radius: 0 4px 4px 0;
            margin-bottom: 16px;
            font-style: italic;
            white-space: pre-wrap;
        }}

        .relations-list {{
            display: flex;
            flex-direction: column;
            gap: 6px;
            max-height: 200px;
            overflow-y: auto;
            background: rgba(0, 0, 0, 0.15);
            padding: 8px;
            border-radius: 6px;
            border: 1px solid rgba(255, 255, 255, 0.03);
            margin-bottom: 16px;
        }}

        .relation-item {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 0.75rem;
            padding: 4px;
            border-radius: 4px;
            cursor: pointer;
            transition: background 0.15s;
        }}

        .relation-item:hover {{
            background: rgba(255, 255, 255, 0.05);
            color: var(--accent);
        }}

        .relation-name {{
            font-weight: 500;
            text-overflow: ellipsis;
            overflow: hidden;
            white-space: nowrap;
            max-width: 75%;
        }}

        .relation-ctx {{
            font-size: 0.65rem;
            color: var(--text-muted);
            text-overflow: ellipsis;
            overflow: hidden;
            white-space: nowrap;
            max-width: 65%;
            font-family: 'Fira Code', monospace;
        }}

        /* Close detail button */
        .close-btn {{
            position: absolute;
            top: 15px;
            right: 15px;
            background: none;
            border: none;
            color: var(--text-muted);
            cursor: pointer;
            font-size: 1.2rem;
            line-height: 1;
            padding: 4px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            width: 28px;
            height: 28px;
            transition: all 0.2s;
        }}

        .close-btn:hover {{
            background: rgba(255, 255, 255, 0.1);
            color: var(--text-primary);
        }}

        /* SVG Graph Styling */
        .node {{
            cursor: pointer;
            stroke-width: 1.5;
            transition: stroke-width 0.15s, filter 0.15s;
        }}

        .node:hover {{
            stroke-width: 2.5;
        }}
        
        .node-text {{
            font-size: 9px;
            fill: var(--text-secondary);
            font-weight: 500;
            pointer-events: none;
            text-anchor: middle;
        }}

        .link {{
            stroke-opacity: 0.25;
            transition: stroke-opacity 0.2s, stroke-width 0.2s;
            fill: none;
        }}
        
        /* Highlight states */
        .node.faded, .link.faded {{
            opacity: 0.1;
        }}
        
        .node.highlighted {{
            opacity: 1;
            stroke: #fff !important;
            filter: drop-shadow(0px 0px 8px var(--accent));
        }}

        .node-text.faded {{
            opacity: 0.15;
        }}

        .node-text.highlighted {{
            opacity: 1;
            fill: var(--text-primary);
            font-weight: 600;
            font-size: 10px;
        }}

        .link.highlighted {{
            stroke-opacity: 0.85;
            stroke-width: 2px !important;
        }}
        
        /* Custom Scrollbar for floating panels */
        ::-webkit-scrollbar {{
            width: 6px;
        }}
        ::-webkit-scrollbar-track {{
            background: transparent;
        }}
        ::-webkit-scrollbar-thumb {{
            background: rgba(255, 255, 255, 0.1);
            border-radius: 3px;
        }}
        ::-webkit-scrollbar-thumb:hover {{
            background: rgba(255, 255, 255, 0.2);
        }}
        
        .relation-item.cycle-item {{
            color: #ef4444;
        }}
        .relation-item.cycle-item:hover {{
            background: rgba(239, 68, 68, 0.1);
            color: #f87171;
        }}
        .relation-item.hotspot-item {{
            color: #fb923c;
        }}
        .relation-item.hotspot-item:hover {{
            background: rgba(251, 146, 60, 0.1);
            color: #fdba74;
        }}
        @keyframes pulse-stroke {{
            0% {{ stroke-width: 1.8px; }}
            50% {{ stroke-width: 3.5px; }}
            100% {{ stroke-width: 1.8px; }}
        }}
        .pulsing-node {{
            animation: pulse-stroke 2s infinite;
        }}
    </style>
</head>
<body>
    <svg id="viewport">
        <!-- Defined markers for directional arrows -->
        <defs>
            <marker id="arrow-py" viewBox="0 -5 10 10" refX="18" refY="0" markerWidth="6" markerHeight="6" orient="auto">
                <path d="M0,-5L10,0L0,5" fill="var(--color-python)"></path>
            </marker>
            <marker id="arrow-js" viewBox="0 -5 10 10" refX="18" refY="0" markerWidth="6" markerHeight="6" orient="auto">
                <path d="M0,-5L10,0L0,5" fill="var(--color-javascript)"></path>
            </marker>
            <marker id="arrow-ts" viewBox="0 -5 10 10" refX="18" refY="0" markerWidth="6" markerHeight="6" orient="auto">
                <path d="M0,-5L10,0L0,5" fill="var(--color-typescript)"></path>
            </marker>
            <marker id="arrow-go" viewBox="0 -5 10 10" refX="18" refY="0" markerWidth="6" markerHeight="6" orient="auto">
                <path d="M0,-5L10,0L0,5" fill="var(--color-go)"></path>
            </marker>
            <marker id="arrow-rs" viewBox="0 -5 10 10" refX="18" refY="0" markerWidth="6" markerHeight="6" orient="auto">
                <path d="M0,-5L10,0L0,5" fill="var(--color-rust)"></path>
            </marker>
            <marker id="arrow-java" viewBox="0 -5 10 10" refX="18" refY="0" markerWidth="6" markerHeight="6" orient="auto">
                <path d="M0,-5L10,0L0,5" fill="var(--color-java)"></path>
            </marker>
            <marker id="arrow-ai" viewBox="0 -5 10 10" refX="18" refY="0" markerWidth="6" markerHeight="6" orient="auto">
                <path d="M0,-5L10,0L0,5" fill="var(--color-ai)"></path>
            </marker>
            <marker id="arrow-default" viewBox="0 -5 10 10" refX="18" refY="0" markerWidth="6" markerHeight="6" orient="auto">
                <path d="M0,-5L10,0L0,5" fill="var(--color-unknown)"></path>
            </marker>
        </defs>
    </svg>

    <!-- LEFT PANEL: Controls & Settings -->
    <div id="control-panel" class="panel">
        <div>
            <h1>🗺️ PGM Viewer</h1>
            <p class="subtitle" style="margin-top: 2px;">Project: <strong style="color: var(--text-primary);">{data["project_name"]}</strong></p>
            <p class="subtitle">Generated: {data["generated_at"]}</p>
        </div>

        <!-- Mode Toggle -->
        <div>
            <h2>Xem Đồ Thị</h2>
            <div class="btn-group">
                <button id="btn-file-mode" class="active" onclick="setMode('file')">Thư Mục / File</button>
                <button id="btn-symbol-mode" onclick="setMode('symbol')">Hàm / Lớp (Symbol)</button>
            </div>
        </div>

        <!-- Search -->
        <div class="search-box">
            <input type="text" id="search-input" placeholder="Tìm kiếm node..." oninput="handleSearch(this.value)">
            <svg viewBox="0 0 24 24">
                <path d="M9.5,3A6.5,6.5 0 0,1 16,9.5C16,11.11 15.41,12.59 14.44,13.73L14.71,14H15.5L20.5,19L19,20.5L14,15.5V14.71L13.73,14.44C12.59,15.41 11.11,16 9.5,16A6.5,6.5 0 0,1 3,9.5A6.5,6.5 0 0,1 9.5,3M9.5,5C7,5 5,7 5,9.5C5,12 7,14 9.5,14C12,14 14,12 14,9.5C14,7 12,5 9.5,5Z"></path>
            </svg>
        </div>

        <!-- Filters -->
        <div class="filter-group">
            <h2>Lọc Ngôn Ngữ</h2>
            <div id="lang-filters">
                <!-- Will be dynamically generated based on data -->
            </div>
        </div>

        <div class="filter-group" id="kind-filter-section" style="display: none;">
            <h2>Lọc Kiểu Symbol</h2>
            <div id="kind-filters">
                <!-- Dynamically generated kinds -->
            </div>
        </div>

        <!-- Statistics -->
        <div>
            <h2>Thống Kê</h2>
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-val" id="stat-nodes">-</div>
                    <div class="stat-lbl">Nodes</div>
                </div>
                <div class="stat-card">
                    <div class="stat-val" id="stat-links">-</div>
                    <div class="stat-lbl">Edges</div>
                </div>
                <div class="stat-card">
                    <div class="stat-val" id="stat-langs">-</div>
                    <div class="stat-lbl">Langs</div>
                </div>
            </div>
        </div>

        <!-- Cycles & Hotspots -->
        <div id="cycles-section" style="display: none;">
            <h2>Chu trình (Cycles)</h2>
            <div id="cycles-list" class="relations-list" style="max-height: 120px;">
                <!-- Will be dynamically populated -->
            </div>
        </div>

        <div id="hotspots-section" style="display: none;">
            <h2>Hotspots (Top 15)</h2>
            <div id="hotspots-list" class="relations-list" style="max-height: 150px;">
                <!-- Will be dynamically populated -->
            </div>
        </div>

        <!-- Legend -->
        <div>
            <h2>Chú giải</h2>
            <div class="legend-list" id="legend-languages">
                <!-- Dynamic Language legend -->
            </div>
            <div class="legend-list" id="legend-shapes" style="margin-top: 10px; display: none;">
                <div class="legend-row">
                    <div class="legend-shape shape-circle"></div>
                    <span>Hàm / Phương thức (Function/Method)</span>
                </div>
                <div class="legend-row">
                    <div class="legend-shape shape-square"></div>
                    <span>Lớp / Struct (Class/Struct)</span>
                </div>
                <div class="legend-row">
                    <div class="legend-shape shape-diamond"></div>
                    <span>Interface / Trait</span>
                </div>
            </div>
        </div>
    </div>

    <!-- RIGHT PANEL: Node Detail -->
    <div id="detail-panel" class="panel">
        <button class="close-btn" onclick="closeDetail()">&times;</button>
        
        <div class="detail-header">
            <span id="detail-badge" class="badge">class</span>
            <div id="detail-title" class="detail-title">validate_token</div>
        </div>

        <div class="detail-meta">
            <span><strong>File:</strong> <span id="detail-file">-</span></span>
            <span id="detail-line-wrapper"><strong>Dòng:</strong> <span id="detail-line">-</span></span>
        </div>

        <div id="detail-sig-section" style="display: none;">
            <h2>Khai báo (Signature)</h2>
            <pre class="code-sig"><code id="detail-signature"></code></pre>
        </div>

        <div id="detail-doc-section" style="display: none;">
            <h2>Tài liệu (Docstring)</h2>
            <div class="docstring" id="detail-docstring"></div>
        </div>

        <div id="detail-code-section" style="display: none;">
            <h2>Đoạn mã (Code Context)</h2>
            <pre class="code-sig"><code id="detail-code-snippet"></code></pre>
        </div>

        <div id="detail-callers-section">
            <h2>Được gọi bởi (Callers / Incoming)</h2>
            <div class="relations-list" id="detail-callers">
                <!-- Callers list -->
            </div>
        </div>

        <div id="detail-callees-section">
            <h2>Gọi đến (Callees / Outgoing)</h2>
            <div class="relations-list" id="detail-callees">
                <!-- Callees list -->
            </div>
        </div>
    </div>

    <!-- PGM Data script injected -->
    <script id="pgm-raw-data" type="application/json">
{data_json}
    </script>

    <script>
        // --- Core State ---
        let rawData = {{}};
        let currentMode = 'file'; // 'file' | 'symbol'
        let selectedNodeId = null;
        let searchQuery = '';
        
        let activeLanguages = new Set();
        let activeKinds = new Set();
        let availableLanguages = new Set();
        let availableKinds = new Set();

        // D3 Simulation & Selections
        let simulation = null;
        let svg, g, zoom, linkElements, nodeElements, textElements;
        const width = window.innerWidth;
        const height = window.innerHeight;

        // Initialize App robustly
        function initApp() {{
            try {{
                rawData = JSON.parse(document.getElementById('pgm-raw-data').textContent);
            }} catch(e) {{
                console.error("Failed to parse PGM graph data", e);
                return;
            }}

            setupSVG();
            extractMetadata();
            renderFilters();
            renderCyclesAndHotspots();
            updateStats();
            
            // Set initial mode & render
            setMode('file');
            
            // Handle window resizing
            window.addEventListener('resize', () => {{
                if (svg) svg.attr("width", window.innerWidth).attr("height", window.innerHeight);
            }});
        }}

        if (document.readyState === 'loading') {{
            window.addEventListener('DOMContentLoaded', initApp);
        }} else {{
            initApp();
        }}

        // --- UI State Management ---
        function setMode(mode) {{
            currentMode = mode;
            selectedNodeId = null;
            closeDetail();
            
            // Toggle active classes on buttons
            document.getElementById('btn-file-mode').classList.toggle('active', mode === 'file');
            document.getElementById('btn-symbol-mode').classList.toggle('active', mode === 'symbol');
            
            // Toggle kind filter section
            document.getElementById('kind-filter-section').style.display = mode === 'symbol' ? 'block' : 'none';
            document.getElementById('legend-shapes').style.display = mode === 'symbol' ? 'block' : 'none';
            document.getElementById('cycles-section').style.display = (mode === 'symbol' && rawData.cycles && rawData.cycles.length > 0) ? 'block' : 'none';
            document.getElementById('hotspots-section').style.display = mode === 'symbol' ? 'block' : 'none';

            // Reset filters for the mode
            renderFilters();
            
            // Build the graph
            renderGraph();
        }}

        function extractMetadata() {{
            availableLanguages.clear();
            availableKinds.clear();

            // Extract languages from files
            rawData.file_graph.nodes.forEach(n => {{
                if (n.language) availableLanguages.add(n.language);
            }});

            // Extract kinds from symbols
            rawData.symbol_graph.nodes.forEach(n => {{
                if (n.kind) availableKinds.add(n.kind);
                if (n.language) availableLanguages.add(n.language);
            }});
        }}

        function renderFilters() {{
            const langContainer = document.getElementById('lang-filters');
            langContainer.innerHTML = '';
            
            activeLanguages = new Set(availableLanguages);
            
            Array.from(availableLanguages).sort().forEach(lang => {{
                const label = document.createElement('label');
                label.className = 'filter-item';
                
                const dotColor = getLangColor(lang);
                label.innerHTML = `
                    <input type="checkbox" checked value="${{lang}}" onchange="toggleLangFilter(this)">
                    <span class="legend-color" style="background-color: ${{dotColor}}"></span>
                    <span>${{lang.toUpperCase()}}</span>
                `;
                langContainer.appendChild(label);
            }});

            // Kinds (only in symbol mode)
            const kindContainer = document.getElementById('kind-filters');
            kindContainer.innerHTML = '';
            
            activeKinds = new Set(availableKinds);
            
            if (currentMode === 'symbol') {{
                Array.from(availableKinds).sort().forEach(kind => {{
                    const label = document.createElement('label');
                    label.className = 'filter-item';
                    label.innerHTML = `
                        <input type="checkbox" checked value="${{kind}}" onchange="toggleKindFilter(this)">
                        <span>${{kind}}</span>
                    `;
                    kindContainer.appendChild(label);
                }});
            }}

            // Render legend languages
            const legendContainer = document.getElementById('legend-languages');
            legendContainer.innerHTML = '';
            Array.from(availableLanguages).sort().forEach(lang => {{
                const row = document.createElement('div');
                row.className = 'legend-row';
                row.innerHTML = `
                    <span class="legend-color" style="background-color: ${{getLangColor(lang)}}"></span>
                    <span>${{lang.toUpperCase()}}</span>
                `;
                legendContainer.appendChild(row);
            }});
        }}

        function toggleLangFilter(cb) {{
            if (cb.checked) {{
                activeLanguages.add(cb.value);
            }} else {{
                activeLanguages.delete(cb.value);
            }}
            applyFilterAndSearch();
        }}

        function toggleKindFilter(cb) {{
            if (cb.checked) {{
                activeKinds.add(cb.value);
            }} else {{
                activeKinds.delete(cb.value);
            }}
            applyFilterAndSearch();
        }}

        function handleSearch(val) {{
            searchQuery = val.trim().toLowerCase();
            applyFilterAndSearch();
        }}

        // --- Graph Helpers ---
        function getLangColor(lang) {{
            if (!lang || typeof lang !== 'string') return 'var(--color-unknown)';
            switch(lang.toLowerCase()) {{
                case 'python': return 'var(--color-python)';
                case 'javascript': return 'var(--color-javascript)';
                case 'typescript': return 'var(--color-typescript)';
                case 'go': return 'var(--color-go)';
                case 'rust': return 'var(--color-rust)';
                case 'java': return 'var(--color-java)';
                case 'ai': return 'var(--color-ai)';
                default: return 'var(--color-unknown)';
            }}
        }}

        function getMarkerId(lang) {{
            if (!lang || typeof lang !== 'string') return 'arrow-default';
            switch(lang.toLowerCase()) {{
                case 'python': return 'arrow-py';
                case 'javascript': return 'arrow-js';
                case 'typescript': return 'arrow-ts';
                case 'go': return 'arrow-go';
                case 'rust': return 'arrow-rs';
                case 'java': return 'arrow-java';
                case 'ai': return 'arrow-ai';
                default: return 'arrow-default';
            }}
        }}

        // --- SVG Drawing Setup ---
        function setupSVG() {{
            svg = d3.select("#viewport")
                .attr("width", width)
                .attr("height", height);

            // Clean up any old group
            svg.selectAll(".main-group").remove();

            g = svg.append("g").attr("class", "main-group");

            // Setup Zooming & Panning
            zoom = d3.zoom()
                .scaleExtent([0.1, 8])
                .on("zoom", (event) => {{
                    g.attr("transform", event.transform);
                }});

            svg.call(zoom);

            // Draw a subtle grid background
            const gridGroup = g.append("g").attr("class", "grid");
            const gridSize = 100;
            const gridLimit = 5000;

            for (let x = -gridLimit; x <= gridLimit; x += gridSize) {{
                gridGroup.append("line")
                    .attr("x1", x).attr("y1", -gridLimit)
                    .attr("x2", x).attr("y2", gridLimit)
                    .attr("class", "grid-line");
            }}
            for (let y = -gridLimit; y <= gridLimit; y += gridSize) {{
                gridGroup.append("line")
                    .attr("x1", -gridLimit).attr("y1", y)
                    .attr("x2", gridLimit).attr("y2", y)
                    .attr("class", "grid-line");
            }}
        }}

        // --- Main D3 Graph Rendering ---
        function renderGraph() {{
            if (simulation) simulation.stop();

            // Clear current elements
            g.selectAll(".links-group, .nodes-group").remove();

            // Select raw dataset
            const dataset = currentMode === 'file' ? rawData.file_graph : rawData.symbol_graph;
            
            // Clone the data to avoid modifying raw data in place (D3 mutates x, y, vx, vy)
            let nodes = dataset.nodes.map(d => Object.assign({{}}, d));
            let links = dataset.links.map(d => Object.assign({{}}, d));

            // Run initial filters: Language & Symbol Kinds
            nodes = nodes.filter(n => {{
                const langMatch = activeLanguages.has(n.language);
                const kindMatch = currentMode === 'file' || activeKinds.has(n.kind);
                return langMatch && kindMatch;
            }});

            const nodeIds = new Set(nodes.map(n => n.id));
            links = links.filter(l => nodeIds.has(l.source) && nodeIds.has(l.target));

            // Set up force simulation
            simulation = d3.forceSimulation(nodes)
                .force("link", d3.forceLink(links).id(d => d.id).distance(currentMode === 'file' ? 140 : 100).strength(0.8))
                .force("charge", d3.forceManyBody().strength(currentMode === 'file' ? -350 : -200))
                .force("center", d3.forceCenter(width / 2, height / 2))
                .force("collision", d3.forceCollide().radius(currentMode === 'file' ? 35 : 22));

            // Create container groups
            const linksGroup = g.append("g").attr("class", "links-group");
            const nodesGroup = g.append("g").attr("class", "nodes-group");

            // Draw links
            linkElements = linksGroup.selectAll("path")
                .data(links)
                .join("path")
                .attr("class", "link")
                .attr("stroke", d => {{
                    // Determine language from source node
                    const srcNode = nodes.find(n => n.id === d.source.id || n.id === d.source);
                    return srcNode ? getLangColor(srcNode.language) : "rgba(255,255,255,0.15)";
                }})
                .attr("stroke-width", 1.2)
                .attr("marker-end", d => {{
                    const srcNode = nodes.find(n => n.id === d.source.id || n.id === d.source);
                    return `url(#${{srcNode ? getMarkerId(srcNode.language) : 'arrow-default'}})`
                }});

            // Draw node groups (holds shape + text label)
            nodeElements = nodesGroup.selectAll("g")
                .data(nodes)
                .join("g")
                .attr("class", "node-container")
                .call(drag(simulation));

            // Append shape to node based on type/language
            nodeElements.each(function(d) {{
                const el = d3.select(this);
                const color = getLangColor(d.language);

                if (currentMode === 'file') {{
                    // File nodes are rendered as circles or styled capsules
                    el.append("circle")
                        .attr("class", "node")
                        .attr("r", 14 + Math.min(d.total_symbols * 0.4, 18))
                        .attr("fill", "rgba(15, 23, 42, 0.9)")
                        .attr("stroke", color)
                        .attr("stroke-width", 2);
                }} else {{
                    // Symbol nodes shapes based on SymbolKind & impact_score
                    let shape;
                    const rScale = 1 + Math.min(d.impact_score || 0, 15) * 0.15;
                    if (d.kind === 'class' || d.kind === 'struct') {{
                        // Square
                        shape = el.append("rect")
                            .attr("x", -10 * rScale)
                            .attr("y", -10 * rScale)
                            .attr("width", 20 * rScale)
                            .attr("height", 20 * rScale)
                            .attr("rx", 3);
                    }} else if (d.kind === 'interface' || d.kind === 'trait') {{
                        // Diamond
                        const dSize = 12 * rScale;
                        shape = el.append("polygon")
                            .attr("points", `0,-${{dSize}} ${{dSize}},0 0,${{dSize}} -${{dSize}},0`);
                    }} else {{
                        // Circle for functions/methods/constants/enums
                        shape = el.append("circle")
                            .attr("r", 9 * rScale);
                    }}
                    
                    shape.attr("class", "node")
                        .attr("fill", "rgba(15, 23, 42, 0.95)")
                        .attr("stroke", color)
                        .attr("stroke-width", 1.8);
                        
                    if (d.impact_score >= 5) {{
                        shape.classed("pulsing-node", true);
                    }}
                }}
            }});

            // Append text labels
            textElements = nodeElements.append("text")
                .attr("class", "node-text")
                .attr("y", d => currentMode === 'file' ? (18 + Math.min(d.total_symbols * 0.4, 18) + 2) : 18)
                .text(d => d.name);

            // Interaction Event Listeners
            nodeElements.on("click", (event, d) => {{
                event.stopPropagation();
                selectNode(d.id);
            }});

            nodeElements.on("mouseover", (event, d) => {{
                if (selectedNodeId === null) {{
                    highlightRelations(d.id);
                }}
            }});

            nodeElements.on("mouseout", () => {{
                if (selectedNodeId === null) {{
                    resetHighlights();
                }}
            }});

            svg.on("click", () => {{
                selectedNodeId = null;
                closeDetail();
                resetHighlights();
            }});

            // Update force simulation coordinates
            simulation.on("tick", () => {{
                // Custom link arcs or straight lines
                linkElements.attr("d", d => {{
                    // Draw a straight line
                    return `M${{d.source.x}},${{d.source.y}} L${{d.target.x}},${{d.target.y}}`;
                }});

                nodeElements.attr("transform", d => `translate(${{d.x}},${{d.y}})`);
            }});

            // Re-apply any search filter/state
            applyFilterAndSearch();
            
            // Update node/link statistics in control panel
            document.getElementById('stat-nodes').textContent = nodes.length;
            document.getElementById('stat-links').textContent = links.length;
            document.getElementById('stat-langs').textContent = activeLanguages.size;
        }}

        // --- Drag Actions ---
        function drag(sim) {{
            return d3.drag()
                .on("start", (event, d) => {{
                    if (!event.active) sim.alphaTarget(0.3).restart();
                    d.fx = d.x;
                    d.fy = d.y;
                }})
                .on("drag", (event, d) => {{
                    d.fx = event.x;
                    d.fy = event.y;
                }})
                .on("end", (event, d) => {{
                    if (!event.active) sim.alphaTarget(0);
                    d.fx = null;
                    d.fy = null;
                }});
        }}

        // --- Search and Highlight Engine ---
        function applyFilterAndSearch() {{
            if (!simulation) return;

            // Apply search query opacity styling
            if (searchQuery === '' && selectedNodeId === null) {{
                resetHighlights();
                return;
            }}

            if (selectedNodeId !== null) {{
                highlightRelations(selectedNodeId);
                return;
            }}

            // Searching mode
            nodeElements.select(".node").classed("faded", d => !d.name.toLowerCase().includes(searchQuery));
            textElements.classed("faded", d => !d.name.toLowerCase().includes(searchQuery));
            nodeElements.select(".node").classed("highlighted", d => searchQuery !== '' && d.name.toLowerCase().includes(searchQuery));
            linkElements.classed("faded", true).classed("highlighted", false);
        }}

        function highlightRelations(nodeId) {{
            const dataset = currentMode === 'file' ? rawData.file_graph : rawData.symbol_graph;
            
            // Find connected nodes
            const connectedTargets = new Set();
            const connectedSources = new Set();
            
            dataset.links.forEach(l => {{
                const sId = typeof l.source === 'object' ? l.source.id : l.source;
                const tId = typeof l.target === 'object' ? l.target.id : l.target;
                
                if (sId === nodeId) connectedTargets.add(tId);
                if (tId === nodeId) connectedSources.add(sId);
            }});

            // Apply CSS styling classes
            nodeElements.select(".node").classed("faded", d => d.id !== nodeId && !connectedTargets.has(d.id) && !connectedSources.has(d.id));
            textElements.classed("faded", d => d.id !== nodeId && !connectedTargets.has(d.id) && !connectedSources.has(d.id));
            
            nodeElements.select(".node").classed("highlighted", d => d.id === nodeId);
            
            linkElements.classed("faded", l => {{
                const sId = typeof l.source === 'object' ? l.source.id : l.source;
                const tId = typeof l.target === 'object' ? l.target.id : l.target;
                return sId !== nodeId && tId !== nodeId;
            }});

            linkElements.classed("highlighted", l => {{
                const sId = typeof l.source === 'object' ? l.source.id : l.source;
                const tId = typeof l.target === 'object' ? l.target.id : l.target;
                return sId === nodeId || tId === nodeId;
            }});
        }}

        function resetHighlights() {{
            if (nodeElements) {{
                nodeElements.select(".node")
                    .classed("faded", false)
                    .classed("highlighted", false)
                    .style("stroke", null);
            }}
            if (textElements) {{
                textElements.classed("faded", false).classed("highlighted", false);
            }}
            if (linkElements) {{
                linkElements
                    .classed("faded", false)
                    .classed("highlighted", false)
                    .style("stroke", null)
                    .style("stroke-width", null);
            }}
        }}

        // --- Node Details Panel ---
        function selectNode(id) {{
            selectedNodeId = id;
            highlightRelations(id);
            centerOnNode(id);

            // Populate the right side details panel
            const detailPanel = document.getElementById('detail-panel');
            
            if (currentMode === 'file') {{
                const node = rawData.file_graph.nodes.find(n => n.id === id);
                if (!node) return;

                document.getElementById('detail-badge').textContent = 'file / module';
                document.getElementById('detail-badge').className = `badge badge-lang-${{node.language}}`;
                document.getElementById('detail-title').textContent = node.name;
                document.getElementById('detail-file').textContent = node.id;
                document.getElementById('detail-line-wrapper').style.display = 'none';
                
                document.getElementById('detail-sig-section').style.display = 'none';
                document.getElementById('detail-doc-section').style.display = 'none';

                // Query callers (incoming file imports/references) & callees (outgoing)
                renderFileRelations(node);
            }} else {{
                const node = rawData.symbol_graph.nodes.find(n => n.id === id);
                if (!node) return;

                document.getElementById('detail-badge').textContent = node.kind;
                document.getElementById('detail-badge').className = `badge badge-lang-${{node.language}}`;
                document.getElementById('detail-title').textContent = node.name;
                document.getElementById('detail-file').textContent = node.filepath;
                document.getElementById('detail-line-wrapper').style.display = 'inline';
                document.getElementById('detail-line').textContent = node.line;

                // Code Signature
                const sigSection = document.getElementById('detail-sig-section');
                if (node.signature) {{
                    document.getElementById('detail-signature').textContent = node.signature;
                    sigSection.style.display = 'block';
                }} else {{
                    sigSection.style.display = 'none';
                }}

                // Docstring
                const docSection = document.getElementById('detail-doc-section');
                if (node.docstring) {{
                    document.getElementById('detail-docstring').textContent = node.docstring;
                    docSection.style.display = 'block';
                }} else {{
                    docSection.style.display = 'none';
                }}

                // Code Snippet Context
                const codeSection = document.getElementById('detail-code-section');
                if (node.code_snippet) {{
                    document.getElementById('detail-code-snippet').textContent = node.code_snippet;
                    codeSection.style.display = 'block';
                }} else {{
                    codeSection.style.display = 'none';
                }}

                renderSymbolRelations(node);
            }}

            detailPanel.classList.add('visible');
        }}

        function renderFileRelations(node) {{
            const callersContainer = document.getElementById('detail-callers');
            const calleesContainer = document.getElementById('detail-callees');
            callersContainer.innerHTML = '';
            calleesContainer.innerHTML = '';

            const callers = [];
            const callees = [];

            rawData.file_graph.links.forEach(l => {{
                if (l.target === node.id) callers.push(l.source);
                if (l.source === node.id) callees.push(l.target);
            }});

            if (callers.length === 0) {{
                callersContainer.innerHTML = '<div style="font-size:0.75rem;color:var(--text-muted);padding:4px;">Không có file nào phụ thuộc</div>';
            }} else {{
                callers.sort().forEach(cPath => {{
                    const div = document.createElement('div');
                    div.className = 'relation-item';
                    div.innerHTML = `
                        <span class="relation-name" title="${{cPath}}">${{cPath.split('/').pop()}}</span>
                        <span class="relation-ctx">${{cPath}}</span>
                    `;
                    div.onclick = (e) => {{ e.stopPropagation(); selectNode(cPath); }};
                    callersContainer.appendChild(div);
                }});
            }}

            if (callees.length === 0) {{
                calleesContainer.innerHTML = '<div style="font-size:0.75rem;color:var(--text-muted);padding:4px;">Không phụ thuộc file nào</div>';
            }} else {{
                callees.sort().forEach(cPath => {{
                    const div = document.createElement('div');
                    div.className = 'relation-item';
                    div.innerHTML = `
                        <span class="relation-name" title="${{cPath}}">${{cPath.split('/').pop()}}</span>
                        <span class="relation-ctx">${{cPath}}</span>
                    `;
                    div.onclick = (e) => {{ e.stopPropagation(); selectNode(cPath); }};
                    calleesContainer.appendChild(div);
                }});
            }}
        }}

        function renderSymbolRelations(node) {{
            const callersContainer = document.getElementById('detail-callers');
            const calleesContainer = document.getElementById('detail-callees');
            callersContainer.innerHTML = '';
            calleesContainer.innerHTML = '';

            const callers = [];
            const callees = [];

            rawData.symbol_graph.links.forEach(l => {{
                if (l.target === node.id) callers.push(l.source);
                if (l.source === node.id) callees.push(l.target);
            }});

            // We can also check rawData to get matching symbol details
            if (callers.length === 0) {{
                callersContainer.innerHTML = '<div style="font-size:0.75rem;color:var(--text-muted);padding:4px;">Không có ai gọi hàm này</div>';
            }} else {{
                callers.sort().forEach(cId => {{
                    const parts = cId.split('::');
                    const name = parts[parts.length - 1];
                    const div = document.createElement('div');
                    div.className = 'relation-item';
                    div.innerHTML = `
                        <span class="relation-name" title="${{cId}}">${{name}}()</span>
                        <span class="relation-ctx">${{parts[0].split('/').pop()}}</span>
                    `;
                    div.onclick = (e) => {{ e.stopPropagation(); selectNode(cId); }};
                    callersContainer.appendChild(div);
                }});
            }}

            if (callees.length === 0) {{
                calleesContainer.innerHTML = '<div style="font-size:0.75rem;color:var(--text-muted);padding:4px;">Không gọi hàm nào khác</div>';
            }} else {{
                callees.sort().forEach(cId => {{
                    const parts = cId.split('::');
                    const name = parts[parts.length - 1];
                    const div = document.createElement('div');
                    div.className = 'relation-item';
                    div.innerHTML = `
                        <span class="relation-name" title="${{cId}}">${{name}}()</span>
                        <span class="relation-ctx">${{parts[0].split('/').pop()}}</span>
                    `;
                    div.onclick = (e) => {{ e.stopPropagation(); selectNode(cId); }};
                    calleesContainer.appendChild(div);
                }});
            }}
        }}

        function renderCyclesAndHotspots() {{
            const cyclesList = document.getElementById('cycles-list');
            if (cyclesList && rawData.cycles) {{
                cyclesList.innerHTML = '';
                if (rawData.cycles.length === 0) {{
                    cyclesList.innerHTML = '<div style="font-size:0.75rem;color:var(--text-muted);padding:4px;">Không phát hiện circular dependencies</div>';
                }} else {{
                    rawData.cycles.forEach((cycle, index) => {{
                        const div = document.createElement('div');
                        div.className = 'relation-item cycle-item';
                        const names = cycle.map(id => id.split('::').pop().split('.').pop() + '()');
                        div.innerHTML = `
                            <span class="relation-name" title="${{cycle.join(' -> ')}}">Vòng #${{index + 1}}</span>
                            <span class="relation-ctx">${{names.join(' → ')}}</span>
                        `;
                        div.onclick = (e) => {{
                            e.stopPropagation();
                            highlightCycle(cycle);
                        }};
                        cyclesList.appendChild(div);
                    }});
                }}
            }}

            const hotspotsList = document.getElementById('hotspots-list');
            if (hotspotsList && rawData.hotspots) {{
                hotspotsList.innerHTML = '';
                if (rawData.hotspots.length === 0) {{
                    hotspotsList.innerHTML = '<div style="font-size:0.75rem;color:var(--text-muted);padding:4px;">Không có hotspots</div>';
                }} else {{
                    rawData.hotspots.forEach((hs, index) => {{
                        const div = document.createElement('div');
                        div.className = 'relation-item hotspot-item';
                        div.innerHTML = `
                            <span class="relation-name" title="${{hs.id}}">${{index + 1}}. ${{hs.name}} (${{hs.kind}})</span>
                            <span class="relation-ctx" style="color: var(--color-rust); font-weight: bold;">Score: ${{hs.score}}</span>
                        `;
                        div.onclick = (e) => {{
                            e.stopPropagation();
                            selectNode(hs.id);
                        }};
                        hotspotsList.appendChild(div);
                    }});
                }}
            }}
        }}

        function highlightCycle(cycleNodeIds) {{
            const cycleSet = new Set(cycleNodeIds);
            
            // Fade all nodes & links
            nodeElements.select(".node").classed("faded", true).classed("highlighted", false);
            textElements.classed("faded", true).classed("highlighted", false);
            linkElements.classed("faded", true).classed("highlighted", false);
            
            // Highlight nodes in the cycle
            nodeElements.filter(d => cycleSet.has(d.id))
                .select(".node")
                .classed("faded", false)
                .classed("highlighted", true)
                .style("stroke", "#ef4444");
                
            textElements.filter(d => cycleSet.has(d.id))
                .classed("faded", false)
                .classed("highlighted", true);
                
            // Highlight links between cycle nodes
            linkElements.filter(l => {{
                const sourceId = l.source.id || l.source;
                const targetId = l.target.id || l.target;
                return cycleSet.has(sourceId) && cycleSet.has(targetId);
            }})
            .classed("faded", false)
            .classed("highlighted", true)
            .style("stroke", "#ef4444")
            .style("stroke-width", "2.5px");
            
            if (cycleNodeIds.length > 0) {{
                centerOnNode(cycleNodeIds[0]);
            }}
        }}

        function closeDetail() {{
            document.getElementById('detail-panel').classList.remove('visible');
            selectedNodeId = null;
            resetHighlights();
        }}

        function centerOnNode(nodeId) {{
            // Find current layout position of node
            const d3Node = nodeElements.data().find(n => n.id === nodeId);
            if (!d3Node) return;

            const scale = 1.2;
            const x = width / 2 - d3Node.x * scale;
            const y = height / 2 - d3Node.y * scale;

            svg.transition()
                .duration(750)
                .call(
                    zoom.transform,
                    d3.zoomIdentity.translate(x, y).scale(scale)
                );
        }}

        function updateStats() {{
            // Project metrics from rawData stats
            if (!rawData.stats) return;
            const totalFiles = rawData.stats.total_files;
            const totalSymbols = rawData.stats.total_symbols;
        }}

        // Setup Live Reload
        if (window.location.protocol.startsWith('http')) {{
            const eventSource = new EventSource('/events');
            eventSource.onmessage = function(event) {{
                if (event.data === 'reload') {{
                    console.log('Reloading graph...');
                    window.location.reload();
                }}
            }};
            eventSource.onerror = function() {{
                console.log('SSE connection error. Retrying...');
            }};
        }}
    </script>
</body>
</html>
"""


def _resolve_js_ts_import(
    f_path: str,
    imp: str,
    file_paths: set[str],
    project_root: Path,
) -> str | None:
    # 1. Relative import (starts with . or ..)
    if imp.startswith(".") or imp.startswith(".."):
        parts = f_path.split("/")[:-1] + imp.split("/")
        normalized_parts = []
        for part in parts:
            if part == "." or part == "":
                continue
            elif part == "..":
                if normalized_parts:
                    normalized_parts.pop()
            else:
                normalized_parts.append(part)
        rel_to_root = "/".join(normalized_parts)

        # Test suffixes
        for suffix in [".ts", ".tsx", ".js", ".jsx", ".d.ts", ""]:
            check_path = rel_to_root + suffix
            if check_path in file_paths:
                return check_path
            # Also test folder/index
            check_index = f"{rel_to_root}/index{suffix}"
            if check_index in file_paths:
                return check_index

    # 2. Alias / Absolute path via tsconfig.json or jsconfig.json
    for name in ["tsconfig.json", "jsconfig.json"]:
        config_path = project_root / name
        if config_path.exists():
            try:
                import re

                content = config_path.read_text(encoding="utf-8", errors="ignore")
                content = re.sub(r"//.*", "", content)
                content = re.sub(r"/\*.*?\*/", "", content, flags=re.DOTALL)
                content = re.sub(r",\s*([\]}])", r"\1", content)
                config = json.loads(content)

                compiler_options = config.get("compilerOptions", {})
                paths = compiler_options.get("paths", {})
                base_url = compiler_options.get("baseUrl", "").strip("./").strip("/")

                # Resolve paths mapping
                for pattern, targets in paths.items():
                    if "*" in pattern:
                        prefix = pattern.replace("*", "")
                        if imp.startswith(prefix):
                            suffix = imp[len(prefix) :]
                            for target in targets:
                                target_prefix = target.replace("*", "")
                                target_path = target_prefix + suffix
                                # Combine with baseUrl if any
                                if base_url:
                                    target_path = f"{base_url}/{target_path}"
                                target_path = target_path.strip("./").strip("/")
                                resolved = _check_absolute_import_path(target_path, file_paths)
                                if resolved:
                                    return resolved
                    else:
                        if imp == pattern:
                            for target in targets:
                                target_path = target
                                if base_url:
                                    target_path = f"{base_url}/{target_path}"
                                target_path = target_path.strip("./").strip("/")
                                resolved = _check_absolute_import_path(target_path, file_paths)
                                if resolved:
                                    return resolved

                # Resolve baseUrl fallback
                if base_url:
                    target_path = f"{base_url}/{imp}".strip("./").strip("/")
                    resolved = _check_absolute_import_path(target_path, file_paths)
                    if resolved:
                        return resolved
            except Exception:
                pass

    # 3. Fallback absolute import (best effort)
    return _check_absolute_import_path(imp, file_paths)


def _check_absolute_import_path(target_path_str: str, file_paths: set[str]) -> str | None:
    target_path_str = target_path_str.replace("\\", "/").strip("./").strip("/")
    for suffix in [".ts", ".tsx", ".js", ".jsx", ".d.ts", ""]:
        check = target_path_str + suffix
        if check in file_paths:
            return check
        check_index = f"{target_path_str}/index{suffix}"
        if check_index in file_paths:
            return check_index
    return None


def _get_code_snippet(
    project_root: Path, file_path: str, start_line: int, max_lines: int = 15
) -> str:
    try:
        full_path = project_root / file_path
        if not full_path.exists():
            return ""
        lines = full_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        start = max(0, start_line - 1)
        end = min(len(lines), start + max_lines)
        snippet = "\n".join(lines[start:end])
        if len(lines) > end:
            snippet += "\n..."
        return snippet
    except Exception:
        return ""
