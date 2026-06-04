from __future__ import annotations

import os
import sys
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import click
from rich.console import Console
from rich.table import Table


console = Console()


@click.group()
@click.version_option("0.2.0")
def cli():
    """Project Graph Mapper — multi-language dependency & impact analysis."""


# ── scan ──────────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("project_path", default=".", type=click.Path(exists=True))
@click.option("--output", "-o", default=".pgm", show_default=True, help="Thư mục output")
@click.option("--ai", "use_ai", is_flag=True, help="Bật AI parser cho extensions chỉ định")
@click.option("--ai-ext", multiple=True, help="Extension dùng AI (ví dụ: --ai-ext .vue --ai-ext .svelte)")
@click.option("--ai-all", is_flag=True, help="Dùng AI cho tất cả file")
@click.option("--ai-model", default="claude-sonnet-4-20250514", show_default=True, help="AI model")
def scan(
    project_path: str,
    output: str,
    use_ai: bool,
    ai_ext: tuple[str, ...],
    ai_all: bool,
    ai_model: str,
) -> None:
    """Quét project, sinh graph.json và CONTEXT.md."""
    from .graph.builder import GraphBuilder
    from .output.json_writer import JsonWriter
    from .output.md_writer import MarkdownWriter

    root    = Path(project_path).resolve()
    out_dir = root / output
    out_dir.mkdir(exist_ok=True)

    # Xác định AI extensions
    ai_extensions: list[str] | None = None
    if ai_all:
        ai_extensions = [".*"]  # wildcard — sẽ được xử lý riêng
    elif use_ai or ai_ext:
        ai_extensions = list(ai_ext) if ai_ext else []

    ai_api_key = os.environ.get("ANTHROPIC_API_KEY")
    if ai_extensions and not ai_api_key:
        console.print("[yellow]Warning:[/yellow] ANTHROPIC_API_KEY not set — AI parser sẽ bị bỏ qua")

    with console.status("[bold green]Đang quét project..."):
        builder = GraphBuilder(
            ai_extensions=ai_extensions or None,
            ai_api_key=ai_api_key,
            ai_model=ai_model,
        )
        builder.build(root)

    s = builder.stats
    console.print(
        f"[green]Xong![/green] "
        f"{s['total_files']} files · {s['total_symbols']} symbols · {s['total_edges']} edges"
    )

    # Language breakdown summary
    _print_language_summary(builder)

    JsonWriter().write(builder.files, builder.symbols, out_dir / "graph.json")
    MarkdownWriter().write_context(
        builder.files, builder.symbols, builder.graph, out_dir / "CONTEXT.md"
    )
    MarkdownWriter().write_mermaid(
        builder.symbols, out_dir / "graph.mermaid"
    )

    console.print(f"\nOutput → [bold]{out_dir}[/bold]")
    console.print(f"  [cyan]CONTEXT.md[/cyan]     — paste vào AI để dùng ngay")
    console.print(f"  [cyan]graph.json[/cyan]      — dùng cho IDE/plugin")
    console.print(f"  [cyan]graph.mermaid[/cyan]   — xem biểu đồ call graph trên Mermaid")


def _print_language_summary(builder) -> None:
    """In bảng tóm tắt ngôn ngữ."""
    from collections import Counter
    lang_files: Counter[str] = Counter()
    lang_symbols: Counter[str] = Counter()

    for fnode in builder.files.values():
        lang = fnode.language or "unknown"
        lang_files[lang] += 1
        lang_symbols[lang] += len(fnode.symbols)

    if len(lang_files) > 1:
        table = Table(title="Language breakdown", show_lines=False)
        table.add_column("Language", style="cyan")
        table.add_column("Files", style="yellow", justify="right")
        table.add_column("Symbols", style="green", justify="right")

        for lang, count in lang_files.most_common():
            table.add_row(lang.capitalize(), str(count), str(lang_symbols[lang]))
        console.print(table)


# ── langs ─────────────────────────────────────────────────────────────────────

@cli.command()
def langs():
    """Liệt kê ngôn ngữ hỗ trợ."""
    from .graph.builder import _init_registry
    from .parser.base import registered_parsers

    _init_registry()

    table = Table(title="Supported Languages", show_lines=True)
    table.add_column("Language", style="cyan")
    table.add_column("Extensions", style="yellow")
    table.add_column("Engine", style="green")

    seen_parsers: set[int] = set()
    for _ext, parser in registered_parsers():
        pid = id(parser)
        if pid in seen_parsers:
            continue
        seen_parsers.add(pid)

        lang = parser.language_name().capitalize()
        exts = " ".join(parser.extensions())
        engine = parser.engine_name()
        table.add_row(lang, exts, engine)

    # AI note
    table.add_row(
        "[dim]Any[/dim]",
        "[dim](dùng --ai-ext)[/dim]",
        "[dim]AI (opt-in)[/dim]",
    )

    console.print(table)


# ── impact ────────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("symbol_name")
@click.option("--project", "-p", default=".", show_default=True, type=click.Path(exists=True))
@click.option("--save", "-s", is_flag=True, help="Lưu report ra .pgm/impact_<name>.md")
def impact(symbol_name: str, project: str, save: bool):
    """Phân tích impact nếu sửa SYMBOL_NAME."""
    from .graph.builder import GraphBuilder
    from .graph.query import QueryEngine
    from .output.md_writer import MarkdownWriter

    root    = Path(project).resolve()
    builder = GraphBuilder()

    with console.status("[bold green]Đang quét..."):
        builder.build(root)

    result = QueryEngine(builder.graph, builder.symbols).impact(symbol_name)

    # Ambiguous — nhiều symbol cùng tên
    if result.get("ambiguous"):
        console.print(f"[yellow]Có {len(result['matches'])} symbol tên '{symbol_name}':[/yellow]")
        for m in result["matches"]:
            console.print(f"  {m['id']}  ({m['file']}:{m['line']})")
        return

    if "error" in result:
        console.print(f"[red]{result['error']}[/red]")
        return

    sym = result["symbol"]

    # ── In bảng callers ───────────────────────────────────────────────────────
    if result["direct_callers"]:
        table = Table(
            title=f"Direct callers of `{symbol_name}()`",
            show_lines=True,
        )
        table.add_column("File", style="cyan", no_wrap=True)
        table.add_column("Line", style="yellow", justify="right")
        table.add_column("Context", style="white")
        for cs in result["direct_callers"]:
            table.add_row(cs.file, str(cs.line), cs.context[:70])
        console.print(table)
    else:
        console.print(f"[dim]Không có caller nào cho `{symbol_name}`[/dim]")

    if result["transitive_files"]:
        console.print(f"\n[bold]Transitive ({len(result['transitive_files'])}):[/bold]")
        for f in sorted(result["transitive_files"]):
            console.print(f"  [dim]{f}[/dim]")

    console.print(f"\n[bold]Impact score:[/bold] {result['impact_score']} file(s)")
    console.print(f"[bold]Location:[/bold] {sym.loc.file}:{sym.loc.line}")

    # ── Checklist ─────────────────────────────────────────────────────────────
    console.print("\n[bold]Checklist:[/bold]")
    for item in result["checklist"]:
        console.print(f"  [green]•[/green] {item}")

    # ── Lưu file ──────────────────────────────────────────────────────────────
    if save:
        out_dir = root / ".pgm"
        out_dir.mkdir(exist_ok=True)
        out_file = out_dir / f"impact_{symbol_name}.md"
        MarkdownWriter().write_impact(result, out_file)
        console.print(f"\n[green]Saved:[/green] {out_file}")


# ── hotspots ──────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--project", "-p", default=".", type=click.Path(exists=True))
@click.option("--top", "-n", default=10, show_default=True, help="Số symbol hiển thị")
def hotspots(project: str, top: int):
    """Liệt kê symbols có impact cao nhất (dễ gây breaking change nhất)."""
    from .graph.builder import GraphBuilder
    from .graph.query import QueryEngine

    root    = Path(project).resolve()
    builder = GraphBuilder()

    with console.status("[bold green]Đang phân tích..."):
        builder.build(root)

    results = QueryEngine(builder.graph, builder.symbols).hotspots(top)

    if not results:
        console.print("[dim]Không tìm thấy hotspot nào[/dim]")
        return

    table = Table(title=f"Top {top} hotspot symbols", show_lines=True)
    table.add_column("#",       style="dim",    justify="right", width=4)
    table.add_column("Symbol",  style="cyan")
    table.add_column("Kind",    style="magenta")
    table.add_column("File",    style="white")
    table.add_column("Line",    style="yellow", justify="right")
    table.add_column("Callers", style="bold red", justify="right")

    for rank, (sid, score) in enumerate(results, 1):
        sym = builder.symbols[sid]
        table.add_row(
            str(rank),
            sym.name,
            sym.kind.value,
            sym.loc.file,
            str(sym.loc.line),
            str(score),
        )
    console.print(table)


# ── watch ─────────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--project", "-p", default=".", type=click.Path(exists=True))
@click.option("--output", "-o", default=".pgm", show_default=True)
@click.option("--ai", "use_ai", is_flag=True, help="Bật AI parser cho watch")
@click.option("--ai-ext", multiple=True, help="Extension dùng AI")
def watch(project: str, output: str, use_ai: bool, ai_ext: tuple[str, ...]):
    """Watch mode — tự động cập nhật graph khi file thay đổi."""
    from .graph.builder import GraphBuilder
    from .watcher import start_watch

    root    = Path(project).resolve()
    out_dir = root / output
    out_dir.mkdir(exist_ok=True)

    ai_extensions: list[str] | None = None
    if use_ai or ai_ext:
        ai_extensions = list(ai_ext) if ai_ext else []

    with console.status("[bold green]Lần quét đầu..."):
        builder = GraphBuilder(
            ai_extensions=ai_extensions or None,
            ai_api_key=os.environ.get("ANTHROPIC_API_KEY"),
        )
        builder.build(root)

    s = builder.stats
    console.print(
        f"[green]Sẵn sàng![/green] "
        f"{s['total_files']} files · {s['total_symbols']} symbols"
    )

    start_watch(root, builder, out_dir, console)


# ── cycles ────────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--project", "-p", default=".", type=click.Path(exists=True))
def cycles(project: str):
    """Tìm circular imports trong project."""
    from .graph.builder import GraphBuilder
    from .graph.query import QueryEngine

    root    = Path(project).resolve()
    builder = GraphBuilder()

    with console.status("[bold green]Đang phân tích..."):
        builder.build(root)

    found = QueryEngine(builder.graph, builder.symbols).cycles()

    if not found:
        console.print("[green]Không có circular dependency[/green] ✓")
        return

    console.print(f"[red]Tìm thấy {len(found)} cycle(s):[/red]")
    for i, cycle in enumerate(found, 1):
        console.print(f"  {i}. {' → '.join(cycle)}")


# ── path ──────────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("start_symbol")
@click.argument("end_symbol")
@click.option("--project", "-p", default=".", type=click.Path(exists=True))
def path(start_symbol: str, end_symbol: str, project: str):
    """Tìm đường dẫn cuộc gọi từ START_SYMBOL đến END_SYMBOL."""
    from .graph.builder import GraphBuilder
    from .graph.query import QueryEngine

    root    = Path(project).resolve()
    builder = GraphBuilder()

    with console.status("[bold green]Đang tìm đường đi..."):
        builder.build(root)

    found_paths = QueryEngine(builder.graph, builder.symbols).call_paths(start_symbol, end_symbol)

    if not found_paths:
        console.print(f"[yellow]Không tìm thấy đường dẫn cuộc gọi từ '{start_symbol}' đến '{end_symbol}'[/yellow]")
        return

    console.print(f"[green]Tìm thấy {len(found_paths)} đường đi:[/green]")
    for idx, call_path in enumerate(found_paths, 1):
        console.print(f"\nPath #{idx}:")
        for i, sid in enumerate(call_path):
            sym = builder.symbols[sid]
            indent = "  " * i
            arrow = " -> " if i > 0 else ""
            console.print(f"{indent}{arrow}[cyan]{sym.name}[/cyan] ({sym.loc.file}:{sym.loc.line})")


# ── deadcode ──────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--project", "-p", default=".", type=click.Path(exists=True))
def deadcode(project: str):
    """Tìm các hàm, lớp không được gọi/sử dụng (Dead Code)."""
    from .graph.builder import GraphBuilder
    from .graph.query import QueryEngine

    root    = Path(project).resolve()
    builder = GraphBuilder()

    with console.status("[bold green]Đang phân tích dead code..."):
        builder.build(root)

    dead_symbols = QueryEngine(builder.graph, builder.symbols).dead_code()

    if not dead_symbols:
        console.print("[green]Tuyệt vời! Không phát hiện symbol nào bị thừa (dead code)[/green]")
        return

    filtered_dead = []
    for sid in dead_symbols:
        sym = builder.symbols[sid]
        if not any(x in sym.loc.file.lower() for x in ["test", "setup", "conftest"]):
            filtered_dead.append(sym)

    if not filtered_dead:
        console.print("[green]Không phát hiện dead code ngoài các file test.[/green]")
        return

    table = Table(title=f"Tìm thấy {len(filtered_dead)} symbol có thể không được sử dụng", show_lines=True)
    table.add_column("Symbol", style="cyan")
    table.add_column("Kind", style="magenta")
    table.add_column("File", style="white")
    table.add_column("Line", style="yellow", justify="right")

    for sym in filtered_dead:
        table.add_row(
            sym.name,
            sym.kind.value,
            sym.loc.file,
            str(sym.loc.line),
        )
    console.print(table)


# ── viz ───────────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("project_path", default=".", type=click.Path(exists=True))
@click.option("--output", "-o", default=".pgm", show_default=True, help="Thư mục output")
@click.option("--no-open", is_flag=True, help="Chỉ sinh file, không tự động mở trình duyệt")
@click.option("--ai", "use_ai", is_flag=True, help="Bật AI parser cho extensions chỉ định")
@click.option("--ai-ext", multiple=True, help="Extension dùng AI (ví dụ: --ai-ext .vue --ai-ext .svelte)")
@click.option("--ai-all", is_flag=True, help="Dùng AI cho tất cả file")
@click.option("--ai-model", default="claude-sonnet-4-20250514", show_default=True, help="AI model")
def viz(
    project_path: str,
    output: str,
    no_open: bool,
    use_ai: bool,
    ai_ext: tuple[str, ...],
    ai_all: bool,
    ai_model: str,
) -> None:
    """Quét project và hiển thị đồ thị tương tác (interactive graph)."""
    import webbrowser
    from .graph.builder import GraphBuilder
    from .output.json_writer import JsonWriter
    from .output.html_writer import HtmlWriter
    from .output.md_writer import MarkdownWriter

    root    = Path(project_path).resolve()
    out_dir = root / output
    out_dir.mkdir(exist_ok=True)

    ai_extensions: list[str] | None = None
    if ai_all:
        ai_extensions = [".*"]
    elif use_ai or ai_ext:
        ai_extensions = list(ai_ext) if ai_ext else []

    ai_api_key = os.environ.get("ANTHROPIC_API_KEY")
    if ai_extensions and not ai_api_key:
        console.print("[yellow]Warning:[/yellow] ANTHROPIC_API_KEY not set — AI parser sẽ bị bỏ qua")

    with console.status("[bold green]Đang quét project để dựng đồ thị..."):
        builder = GraphBuilder(
            ai_extensions=ai_extensions or None,
            ai_api_key=ai_api_key,
            ai_model=ai_model,
        )
        builder.build(root)

    s = builder.stats
    console.print(
        f"[green]Xong![/green] Đã quét "
        f"{s['total_files']} files · {s['total_symbols']} symbols · {s['total_edges']} edges"
    )

    # In tóm tắt ngôn ngữ
    _print_language_summary(builder)

    # Ghi file json và html
    json_path = out_dir / "graph.json"
    html_path = out_dir / "graph.html"
    
    JsonWriter().write(builder.files, builder.symbols, json_path)
    HtmlWriter().write(builder.files, builder.symbols, html_path)
    MarkdownWriter().write_mermaid(builder.symbols, out_dir / "graph.mermaid")

    console.print(f"\n[green]Đã sinh đồ thị thành công:[/green]")
    console.print(f"  HTML: [bold cyan]{html_path}[/bold cyan]")
    console.print(f"  JSON: [bold cyan]{json_path}[/bold cyan]")
    console.print(f"  MMD:  [bold cyan]{out_dir / 'graph.mermaid'}[/bold cyan]")

    if not no_open:
        console.print("\nĐang khởi chạy Live-Reload Server và Watch Mode...")
        from .watcher import start_watch
        start_watch(root, builder, out_dir, console, open_browser=True)


def main():
    cli()

