"""
Server Launcher for CNC Pattern Symmetry Repair Web Application.

Usage:
    .venv\\Scripts\\python server.py
    .venv\\Scripts\\python server.py --port 8080
"""

import os
import argparse
import webbrowser
from src.web.app import start_server


def main():
    default_port = int(os.environ.get("PORT", 5000))
    default_host = os.environ.get("HOST", "0.0.0.0")

    parser = argparse.ArgumentParser(description="Lax's CNC Symmetry Engine Web Server")
    parser.add_argument("--port", type=int, default=default_port, help=f"Port to run server on (default: {default_port})")
    parser.add_argument("--host", type=str, default=default_host, help=f"Host address (default: {default_host})")
    parser.add_argument("--open-browser", action="store_true", help="Automatically open default browser")

    args = parser.parse_args()

    url = f"http://{args.host}:{args.port}"
    print(f"\n==================================================================")
    print(f"  LAX'S CNC SYMMETRY ENGINE - WEB APPLICATION")
    print(f"  Address: {url}")
    print(f"==================================================================\n")

    if args.open_browser and args.host in ("127.0.0.1", "localhost"):
        webbrowser.open(url)

    start_server(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
