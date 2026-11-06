"""Single-command local dashboard launcher.

Builds the frontend on first run, then serves static assets and API from one
loopback-only uvicorn process. Requires the optional 'web' Python extra.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path


def launch_web(*, rebuild: bool = False) -> int:
    root = Path(__file__).resolve().parents[2]
    frontend = root / "web"
    index = frontend / "dist" / "index.html"
    if not frontend.is_dir():
        print("Web UI source directory not found. Run from a source checkout.", file=sys.stderr)
        return 2
    if rebuild or not index.is_file():
        if shutil.which("npm") is None:
            print("Node.js/npm is required for the initial frontend build.", file=sys.stderr)
            return 2
        for command in (["npm", "install", "--no-audit", "--no-fund"], ["npm", "run", "build"]):
            result = subprocess.run(command, cwd=frontend, check=False)
            if result.returncode != 0:
                print("Frontend build failed; see output above.", file=sys.stderr)
                return result.returncode
    try:
        import uvicorn

        from sf_factory.web_api import create_app
    except ImportError:
        print("Web dependencies missing. Run: uv sync --extra web", file=sys.stderr)
        return 2
    from sf_factory.factory_selection import data_directory, open_factory
    from sf_factory.file_dashboard import FileDashboardFactory
    from sf_factory.state_store import StateConflict, StateUnavailable

    try:
        factory = open_factory(data_directory())
    except (OSError, ValueError, StateConflict, StateUnavailable) as exc:
        print(f"Could not open dashboard storage: {exc}", file=sys.stderr)
        return 2
    backend = ("File (no DB)" if isinstance(factory, FileDashboardFactory)
               else "SQLite (existing/configured)")
    print(f"Storage: {backend}; {factory.root}")
    app = create_app(static_dir=frontend / "dist", data_dir=factory.root)
    url = "http://127.0.0.1:8000"
    print(f"Software Factory dashboard: {url}")
    try:
        webbrowser.open(url)
        uvicorn.run(app, host="127.0.0.1", port=8000)
    except OSError as exc:
        print(f"Could not start dashboard: {exc}", file=sys.stderr)
        return 1
    return 0
