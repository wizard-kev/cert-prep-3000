import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from certprep import launch


def test_app_url_is_localhost_only():
    assert launch.HOST == "127.0.0.1"
    assert launch.app_url(8123) == "http://127.0.0.1:8123/"


def _serve(handler) -> tuple[HTTPServer, int]:
    server = HTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, server.server_address[1]


class _OtherProgram(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"<html>not the study app</html>")

    def log_message(self, *args):
        pass


class _StudyApp(_OtherProgram):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'[{"chapter": 1}]')


def test_refuses_a_port_held_by_another_program(monkeypatch):
    server, port = _serve(_OtherProgram)
    try:
        monkeypatch.setattr(launch, "settings", type("S", (), {"port": port})())
        assert launch.port_in_use(port) and not launch.app_answers(launch.app_url(port))
        with pytest.raises(SystemExit, match=f"Port {port} is already used by another program"):
            launch.main(["--no-browser"])
    finally:
        server.shutdown()


def test_reuses_an_already_running_app(monkeypatch, capsys):
    server, port = _serve(_StudyApp)
    try:
        monkeypatch.setattr(launch, "settings", type("S", (), {"port": port})())
        monkeypatch.setattr(launch.uvicorn, "run", lambda *a, **k: pytest.fail("must not start a second server"))
        launch.main(["--no-browser"])
        assert "already running" in capsys.readouterr().out
    finally:
        server.shutdown()


def test_free_port_is_not_in_use():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    assert not launch.port_in_use(port)
