# Project Context Snapshot

> Generated: 2026-06-03 16:12  |  Files: 23  |  Symbols: 201

---

## Language breakdown

| Language | Files | Symbols | Engine |
|----------|-------|---------|--------|
| Python | 23 | 202 | ast |

## Entry points

- `src/project_graph_mapper/__init__.py` (0 symbols)
- `src/project_graph_mapper/cli.py` (10 symbols)
- `src/project_graph_mapper/graph/builder.py` (7 symbols)
- `src/project_graph_mapper/graph/models.py` (5 symbols)
- `src/project_graph_mapper/graph/query.py` (7 symbols)
- `src/project_graph_mapper/output/html_writer.py` (3 symbols)
- `src/project_graph_mapper/output/json_writer.py` (2 symbols)
- `src/project_graph_mapper/output/md_writer.py` (4 symbols)
- `src/project_graph_mapper/parser/__init__.py` (0 symbols)
- `src/project_graph_mapper/parser/ai_parser.py` (11 symbols)
- `src/project_graph_mapper/parser/base.py` (11 symbols)
- `src/project_graph_mapper/parser/go_parser.py` (10 symbols)
- `src/project_graph_mapper/parser/java_parser.py` (9 symbols)
- `src/project_graph_mapper/parser/js_parser.py` (14 symbols)
- `src/project_graph_mapper/parser/python_parser.py` (9 symbols)

## Hotspot symbols (top 10 by impact)

| Symbol | File | Line | Callers | Kind |
|--------|------|------|---------|------|
| `Location` | `src/project_graph_mapper/graph/models.py` | 20 | 6 | class |
| `Symbol` | `src/project_graph_mapper/graph/models.py` | 35 | 6 | class |
| `GraphBuilder` | `src/project_graph_mapper/graph/builder.py` | 55 | 4 | class |
| `build` | `src/project_graph_mapper/graph/builder.py` | 72 | 4 | method |
| `_node_text` | `src/project_graph_mapper/parser/tree_sitter_base.py` | 141 | 4 | method |
| `_node_first_line` | `src/project_graph_mapper/parser/tree_sitter_base.py` | 146 | 4 | method |
| `CallSite` | `src/project_graph_mapper/graph/models.py` | 27 | 3 | class |
| `FileNode` | `src/project_graph_mapper/graph/models.py` | 61 | 3 | class |
| `QueryEngine` | `src/project_graph_mapper/graph/query.py` | 6 | 3 | class |
| `hotspots` | `src/project_graph_mapper/graph/query.py` | 74 | 3 | method |

## File overview

| File | Symbols | Imports |
|------|---------|---------|
| `src/project_graph_mapper/__init__.py` | 0 | 1 |
| `src/project_graph_mapper/cli.py` | 10 | 25 |
| `src/project_graph_mapper/graph/builder.py` | 7 | 12 |
| `src/project_graph_mapper/graph/models.py` | 5 | 3 |
| `src/project_graph_mapper/graph/query.py` | 7 | 2 |
| `src/project_graph_mapper/output/html_writer.py` | 3 | 6 |
| `src/project_graph_mapper/output/json_writer.py` | 2 | 5 |
| `src/project_graph_mapper/output/md_writer.py` | 4 | 8 |
| `src/project_graph_mapper/parser/__init__.py` | 0 | 0 |
| `src/project_graph_mapper/parser/ai_parser.py` | 11 | 9 |
| `src/project_graph_mapper/parser/base.py` | 11 | 4 |
| `src/project_graph_mapper/parser/go_parser.py` | 10 | 5 |
| `src/project_graph_mapper/parser/java_parser.py` | 9 | 5 |
| `src/project_graph_mapper/parser/js_parser.py` | 14 | 7 |
| `src/project_graph_mapper/parser/python_parser.py` | 9 | 6 |
| `src/project_graph_mapper/parser/rust_parser.py` | 11 | 5 |
| `src/project_graph_mapper/parser/tree_sitter_base.py` | 12 | 7 |
| `src/project_graph_mapper/watcher.py` | 6 | 10 |
| `src/project_graph_mapper/{parser,graph,output}/__init__.py` | 0 | 0 |
| `tests/__init__.py` | 0 | 0 |
| `tests/test_core.py` | 17 | 7 |
| `tests/test_parsers.py` | 48 | 37 |
| `tests/test_viz.py` | 6 | 10 |

## Circular dependencies

_Không có circular dependency_ ✓
