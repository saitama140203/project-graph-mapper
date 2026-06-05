from __future__ import annotations

from pathlib import Path

from watchdog.events import FileCreatedEvent, FileModifiedEvent, FileSystemEventHandler
from watchdog.observers import Observer

from .graph.builder import GraphBuilder
from .output.html_writer import HtmlWriter
from .output.json_writer import JsonWriter
from .output.md_writer import MarkdownWriter
from .parser.base import supported_extensions


class _Handler(FileSystemEventHandler):
    def __init__(
        self, builder: GraphBuilder, out_dir: Path, console, *, summary: str | None = None
    ) -> None:
        self._builder = builder
        self._out_dir = out_dir
        self._console = console
        self._summary = summary
        self._valid_exts: set[str] = set(supported_extensions())

    def on_modified(self, event: FileModifiedEvent) -> None:
        self._handle(event.src_path)

    def on_created(self, event: FileCreatedEvent) -> None:
        self._handle(event.src_path)

    def _handle(self, src_path: str) -> None:
        fpath = Path(src_path)
        if fpath.suffix.lower() not in self._valid_exts:
            return
        self._console.print(f"[yellow]Changed:[/yellow] {fpath.name}")

        try:
            self._builder.update_file(fpath)
            JsonWriter().write(
                self._builder.files,
                self._builder.symbols,
                self._out_dir / "graph.json",
            )
            MarkdownWriter().write_context(
                self._builder.files,
                self._builder.symbols,
                self._builder.graph,
                self._out_dir / "CONTEXT.md",
                summary=self._summary,
            )
            HtmlWriter().write(
                self._builder.files,
                self._builder.symbols,
                self._out_dir / "graph.html",
            )

            # Notify the server to trigger a browser reload
            from .server import notify_reload

            notify_reload()

            self._console.print("[green]Graph updated[/green]")
        except Exception as e:
            self._console.print(f"[red]Error:[/red] {e}")


def start_watch(
    project_root: Path,
    builder: GraphBuilder,
    out_dir: Path,
    console,
    open_browser: bool = False,
    *,
    summary: str | None = None,
) -> None:
    from .server import start_server, stop_server

    port = start_server(out_dir)
    console.print(
        f"[bold green]Live-Reload Server started at:[/bold green] http://localhost:{port}/graph.html"
    )

    if open_browser:
        import webbrowser

        try:
            webbrowser.open(f"http://localhost:{port}/graph.html")
        except Exception as e:
            console.print(f"[red]Không thể tự động mở trình duyệt: {e}[/red]")

    handler = _Handler(builder, out_dir, console, summary=summary)
    observer = Observer()
    observer.schedule(handler, str(project_root), recursive=True)
    observer.start()
    console.print(f"[bold cyan]Watching[/bold cyan] {project_root}  (Ctrl+C để dừng)")

    try:
        import time

        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        observer.stop()
        observer.join()
        stop_server()
