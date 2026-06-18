"""Launch the iceReach platform: start the FastAPI app and open the browser.

Serves the API and (if built) the React SPA from a single process. In dev you can
instead run the backend with `--reload` and the Vite dev server separately.
"""

import os
import socket
import subprocess
import sys
import time
import webbrowser

BACKEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend")


def find_free_port(start_port=8000, end_port=8100):
    for port in range(start_port, end_port + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError("No free ports available in range.")


def run_server():
    port = find_free_port()
    url = f"http://127.0.0.1:{port}/"
    print(f"✅ Starting iceReach at: {url}")
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "icereach.main:app", "--reload",
         "--port", str(port), "--app-dir", BACKEND_DIR]
    )
    time.sleep(2)
    webbrowser.open(url)
    try:
        process.wait()
    except KeyboardInterrupt:
        print("\n🛑 Shutting down server...")
        process.terminate()


if __name__ == "__main__":
    run_server()
