"""Starts the app on 127.0.0.1 and opens it in the browser once it answers.

Run with:  python -m ccst.launch [--no-browser]   (run.ps1 and the desktop shortcut do this)
Close the window, or press Ctrl+C, to stop the app."""

import argparse
import json
import socket
import threading
import time
import urllib.request
import webbrowser

import uvicorn

from .config import settings

HOST = "127.0.0.1"  # never listen on other interfaces
# Talk to the local app directly, even if the system has a proxy configured.
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def app_url(port: int | None = None) -> str:
    return f"http://{HOST}:{port or settings.port}/"


def app_answers(url: str, timeout: float = 1.0) -> bool:
    """True if this app (not some other program) answers at `url`."""
    try:
        with _opener.open(url + "api/chapters", timeout=timeout) as r:
            return r.status == 200 and isinstance(json.load(r), list)
    except (OSError, ValueError):
        return False


def port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1.0)
        return s.connect_ex((HOST, port)) == 0


def _open_when_ready(url: str, timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if app_answers(url):
            webbrowser.open(url)
            return
        time.sleep(0.5)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="ccst.launch", description="Start the study app and open it in the browser.")
    parser.add_argument("--no-browser", action="store_true", help="start the app without opening the browser")
    args = parser.parse_args(argv)

    port = settings.port
    url = app_url(port)
    if port_in_use(port):
        if app_answers(url):
            print(f"The app is already running at {url}", flush=True)
            if not args.no_browser:
                webbrowser.open(url)
            return
        raise SystemExit(f"Port {port} is already used by another program. Close that program, or set "
                         f"CCST_PORT in the .env file to a free port from 1024 to 65535.")

    print(f"Starting the app at {url}")
    print("Keep this window open while you study. Close it, or press Ctrl+C, to stop the app.", flush=True)
    if not args.no_browser:
        threading.Thread(target=_open_when_ready, args=(url,), daemon=True).start()
    uvicorn.run("ccst.main:app", host=HOST, port=port, log_level="warning")


if __name__ == "__main__":
    main()
