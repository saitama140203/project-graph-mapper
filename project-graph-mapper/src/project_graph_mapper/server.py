from __future__ import annotations

import os
import queue
import threading
from http.server import SimpleHTTPRequestHandler
from pathlib import Path

try:
    from http.server import ThreadingHTTPServer
except ImportError:
    from http.server import HTTPServer
    from socketserver import ThreadingMixIn

    class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
        daemon_threads = True


_clients: set[queue.Queue] = set()
_clients_lock = threading.Lock()
_server_thread: threading.Thread | None = None
_server: ThreadingHTTPServer | None = None


class LiveReloadRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, directory=None, **kwargs):
        if directory is None:
            directory = os.getcwd()
        self.directory = directory
        super().__init__(*args, directory=directory, **kwargs)

    def do_GET(self) -> None:
        if self.path == "/events":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

            q: queue.Queue = queue.Queue()
            with _clients_lock:
                _clients.add(q)
            try:
                # Keep connection alive, send heartbeat and wait for reload events
                while True:
                    try:
                        event = q.get(timeout=10)
                        if event == "reload":
                            self.wfile.write(b"data: reload\n\n")
                            self.wfile.flush()
                    except queue.Empty:
                        # Send ping comment to keep connection alive
                        self.wfile.write(b": ping\n\n")
                        self.wfile.flush()
            except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
                pass
            finally:
                with _clients_lock:
                    if q in _clients:
                        _clients.remove(q)
        else:
            super().do_GET()

    def log_message(self, format: str, *args: any) -> None:
        # Suppress GET logs to keep the terminal output clean
        pass


def start_server(out_dir: Path, port: int = 0) -> int:
    global _server, _server_thread

    # We want to serve out_dir
    def handler_factory(*args, **kwargs):
        return LiveReloadRequestHandler(*args, directory=str(out_dir), **kwargs)

    _server = ThreadingHTTPServer(("127.0.0.1", port), handler_factory)
    actual_port = _server.server_address[1]

    _server_thread = threading.Thread(target=_server.serve_forever, daemon=True)
    _server_thread.start()

    return actual_port


def notify_reload() -> None:
    with _clients_lock:
        clients_copy = list(_clients)
    for q in clients_copy:
        q.put("reload")


def stop_server() -> None:
    global _server
    if _server:
        _server.shutdown()
        _server.server_close()
        _server = None
