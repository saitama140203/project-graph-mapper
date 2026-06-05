from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from project_graph_mapper.cli import cli
from project_graph_mapper.graph.builder import GraphBuilder
from project_graph_mapper.output.html_writer import HtmlWriter


@pytest.fixture
def sample_project(tmp_path: Path) -> Path:
    """Tạo dự án mẫu đơn giản cho việc test viz."""
    # File python
    (tmp_path / "app.py").write_text(
        """\
def main():
    return greet("World")

def greet(name: str):
    return f"Hello {name}"
""",
        encoding="utf-8",
    )

    # File javascript
    (tmp_path / "index.js").write_text(
        """\
function init() {
    console.log("init");
}
""",
        encoding="utf-8",
    )

    return tmp_path


def test_html_writer_generates_file_with_valid_json(sample_project):
    builder = GraphBuilder().build(sample_project)
    output_html = sample_project / ".pgm" / "graph.html"

    writer = HtmlWriter()
    writer.write(builder.files, builder.symbols, output_html)

    assert output_html.exists()
    content = output_html.read_text(encoding="utf-8")

    # Verify HTML template key components
    assert "PGM Interactive Graph Viewer" in content
    assert '<script id="pgm-raw-data" type="application/json">' in content
    assert "</script>" in content

    # Extract JSON data payload and verify structure
    start_tag = '<script id="pgm-raw-data" type="application/json">'
    end_tag = "</script>"
    start_idx = content.find(start_tag) + len(start_tag)
    end_idx = content.find(end_tag, start_idx)

    json_str = content[start_idx:end_idx].strip()
    data = json.loads(json_str)

    assert "project_name" in data
    assert "generated_at" in data
    assert "symbol_graph" in data
    assert "file_graph" in data

    # Check nodes in symbol graph
    sym_nodes = data["symbol_graph"]["nodes"]
    sym_names = [n["name"] for n in sym_nodes]
    assert "main" in sym_names
    assert "greet" in sym_names
    assert "init" in sym_names

    # Check nodes in file graph
    file_nodes = data["file_graph"]["nodes"]
    file_ids = [n["id"] for n in file_nodes]
    assert any("app.py" in f for f in file_ids)
    assert any("index.js" in f for f in file_ids)


def test_cli_viz_command_generates_files(sample_project, monkeypatch):
    # Mock start_watch to prevent blocking in watch mode during tests
    watch_calls = []

    def mock_start_watch(project_root, builder, out_dir, console, open_browser=False, **kwargs):
        watch_calls.append((project_root, builder, out_dir, console, open_browser))

    import project_graph_mapper.watcher

    monkeypatch.setattr(project_graph_mapper.watcher, "start_watch", mock_start_watch)

    runner = CliRunner()
    result = runner.invoke(cli, ["viz", str(sample_project), "--output", ".custom_pgm"])

    assert result.exit_code == 0
    assert "Đã sinh đồ thị thành công" in result.output

    html_path = sample_project / ".custom_pgm" / "graph.html"
    json_path = sample_project / ".custom_pgm" / "graph.json"

    assert html_path.exists()
    assert json_path.exists()

    # Verify start_watch was called instead of direct webbrowser.open
    assert len(watch_calls) == 1
    assert watch_calls[0][4] is True  # open_browser should be True


def test_cli_viz_command_no_open_flag(sample_project, monkeypatch):
    opened_urls = []

    def mock_open(url):
        opened_urls.append(url)
        return True

    import webbrowser

    monkeypatch.setattr(webbrowser, "open", mock_open)

    runner = CliRunner()
    result = runner.invoke(cli, ["viz", str(sample_project), "--no-open"])

    assert result.exit_code == 0
    assert "Đã sinh đồ thị thành công" in result.output
    assert "Đang mở đồ thị" not in result.output

    assert (sample_project / ".pgm" / "graph.html").exists()
    # verify browser wasn't opened
    assert len(opened_urls) == 0


def test_live_reload_server_lifecycle(tmp_path):
    import time
    import urllib.error
    import urllib.request

    from project_graph_mapper.server import start_server, stop_server

    # Start the server on a random port
    port = start_server(tmp_path)
    assert port > 0

    # Try fetching a non-existent file, should return 404
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/non_existent.html")
        assert False, "Should have raised HTTPError"
    except urllib.error.HTTPError as e:
        assert e.code == 404

    # Write a mock file and fetch it
    (tmp_path / "index.html").write_text("Hello Live Server", encoding="utf-8")
    response = urllib.request.urlopen(f"http://127.0.0.1:{port}/index.html")
    assert response.status == 200
    assert response.read().decode("utf-8") == "Hello Live Server"

    # Stop the server
    stop_server()

    # Verify server is stopped
    time.sleep(0.5)
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/index.html")
        assert False, "Should have raised URLError after stop"
    except urllib.error.URLError:
        pass  # Success, connection refused
