# Project Context Snapshot

> Generated: 2026-06-04 09:34  |  Files: 24  |  Symbols: 224

---

## Language breakdown

| Language | Files | Symbols | Engine |
|----------|-------|---------|--------|
| Python | 24 | 224 | ast |

## Entry points

- `project-graph-mapper/src/project_graph_mapper/__init__.py` (0 symbols)
- `project-graph-mapper/src/project_graph_mapper/cli.py` (12 symbols)
- `project-graph-mapper/src/project_graph_mapper/graph/builder.py` (7 symbols)
- `project-graph-mapper/src/project_graph_mapper/graph/models.py` (5 symbols)
- `project-graph-mapper/src/project_graph_mapper/graph/query.py` (9 symbols)
- `project-graph-mapper/src/project_graph_mapper/output/html_writer.py` (6 symbols)
- `project-graph-mapper/src/project_graph_mapper/output/json_writer.py` (2 symbols)
- `project-graph-mapper/src/project_graph_mapper/output/md_writer.py` (5 symbols)
- `project-graph-mapper/src/project_graph_mapper/parser/__init__.py` (0 symbols)
- `project-graph-mapper/src/project_graph_mapper/parser/ai_parser.py` (11 symbols)
- `project-graph-mapper/src/project_graph_mapper/parser/base.py` (11 symbols)
- `project-graph-mapper/src/project_graph_mapper/parser/go_parser.py` (9 symbols)
- `project-graph-mapper/src/project_graph_mapper/parser/java_parser.py` (8 symbols)
- `project-graph-mapper/src/project_graph_mapper/parser/js_parser.py` (13 symbols)
- `project-graph-mapper/src/project_graph_mapper/parser/python_parser.py` (9 symbols)

## Hotspot symbols (top 10 by impact)

| Symbol | File | Line | Callers | Kind |
|--------|------|------|---------|------|
| `_node_text` | `project-graph-mapper/src/project_graph_mapper/parser/tree_sitter_base.py` | 141 | 75 | method |
| `Location` | `project-graph-mapper/src/project_graph_mapper/graph/models.py` | 20 | 72 | class |
| `Symbol` | `project-graph-mapper/src/project_graph_mapper/graph/models.py` | 35 | 72 | class |
| `_make_sym` | `project-graph-mapper/src/project_graph_mapper/parser/tree_sitter_base.py` | 224 | 68 | method |
| `_find_children_by_type` | `project-graph-mapper/src/project_graph_mapper/parser/tree_sitter_base.py` | 152 | 66 | method |
| `FileNode` | `project-graph-mapper/src/project_graph_mapper/graph/models.py` | 61 | 65 | class |
| `language_name` | `project-graph-mapper/src/project_graph_mapper/parser/ai_parser.py` | 85 | 64 | method |
| `language_name` | `project-graph-mapper/src/project_graph_mapper/parser/base.py` | 38 | 64 | method |
| `_extract_symbols` | `project-graph-mapper/src/project_graph_mapper/parser/go_parser.py` | 19 | 63 | method |
| `_extract_imports` | `project-graph-mapper/src/project_graph_mapper/parser/go_parser.py` | 111 | 63 | method |

## File overview

| File | Symbols | Imports |
|------|---------|---------|
| `project-graph-mapper/src/project_graph_mapper/__init__.py` | 0 | 1 |
| `project-graph-mapper/src/project_graph_mapper/cli.py` | 12 | 32 |
| `project-graph-mapper/src/project_graph_mapper/graph/builder.py` | 7 | 12 |
| `project-graph-mapper/src/project_graph_mapper/graph/models.py` | 5 | 3 |
| `project-graph-mapper/src/project_graph_mapper/graph/query.py` | 9 | 2 |
| `project-graph-mapper/src/project_graph_mapper/output/html_writer.py` | 6 | 10 |
| `project-graph-mapper/src/project_graph_mapper/output/json_writer.py` | 2 | 5 |
| `project-graph-mapper/src/project_graph_mapper/output/md_writer.py` | 5 | 8 |
| `project-graph-mapper/src/project_graph_mapper/parser/__init__.py` | 0 | 0 |
| `project-graph-mapper/src/project_graph_mapper/parser/ai_parser.py` | 11 | 9 |
| `project-graph-mapper/src/project_graph_mapper/parser/base.py` | 11 | 4 |
| `project-graph-mapper/src/project_graph_mapper/parser/go_parser.py` | 9 | 5 |
| `project-graph-mapper/src/project_graph_mapper/parser/java_parser.py` | 8 | 5 |
| `project-graph-mapper/src/project_graph_mapper/parser/js_parser.py` | 13 | 7 |
| `project-graph-mapper/src/project_graph_mapper/parser/python_parser.py` | 9 | 6 |
| `project-graph-mapper/src/project_graph_mapper/parser/rust_parser.py` | 10 | 5 |
| `project-graph-mapper/src/project_graph_mapper/parser/tree_sitter_base.py` | 14 | 7 |
| `project-graph-mapper/src/project_graph_mapper/server.py` | 9 | 9 |
| `project-graph-mapper/src/project_graph_mapper/watcher.py` | 6 | 13 |
| `project-graph-mapper/src/project_graph_mapper/{parser,graph,output}/__init__.py` | 0 | 0 |
| `project-graph-mapper/tests/__init__.py` | 0 | 0 |
| `project-graph-mapper/tests/test_core.py` | 19 | 7 |
| `project-graph-mapper/tests/test_parsers.py` | 52 | 40 |
| `project-graph-mapper/tests/test_viz.py` | 7 | 14 |

## Circular dependencies

- project-graph-mapper/src/project_graph_mapper/parser/rust_parser.py::RustParser._find_calls → project-graph-mapper/src/project_graph_mapper/parser/go_parser.py::GoParser._find_calls → project-graph-mapper/src/project_graph_mapper/parser/java_parser.py::JavaParser._find_calls
- project-graph-mapper/src/project_graph_mapper/parser/rust_parser.py::RustParser._find_calls → project-graph-mapper/src/project_graph_mapper/parser/go_parser.py::GoParser._find_calls → project-graph-mapper/src/project_graph_mapper/parser/java_parser.py::JavaParser._find_calls → project-graph-mapper/src/project_graph_mapper/parser/tree_sitter_base.py::TreeSitterParser._find_calls
- project-graph-mapper/src/project_graph_mapper/parser/rust_parser.py::RustParser._find_calls → project-graph-mapper/src/project_graph_mapper/parser/go_parser.py::GoParser._find_calls
- project-graph-mapper/src/project_graph_mapper/parser/rust_parser.py::RustParser._find_calls → project-graph-mapper/src/project_graph_mapper/parser/go_parser.py::GoParser._find_calls → project-graph-mapper/src/project_graph_mapper/parser/tree_sitter_base.py::TreeSitterParser._find_calls → project-graph-mapper/src/project_graph_mapper/parser/java_parser.py::JavaParser._find_calls
- project-graph-mapper/src/project_graph_mapper/parser/rust_parser.py::RustParser._find_calls → project-graph-mapper/src/project_graph_mapper/parser/go_parser.py::GoParser._find_calls → project-graph-mapper/src/project_graph_mapper/parser/tree_sitter_base.py::TreeSitterParser._find_calls
