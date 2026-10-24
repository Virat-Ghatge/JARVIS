import os
import sys
import time
import socket
import signal
import shutil
import subprocess
import webbrowser
from pathlib import Path
from typing import Optional, List

import uvicorn

from config.settings import init_config_files

HOST = "127.0.0.1"
PORT = 5050
APP_URL = f"http://{HOST}:{PORT}"
BASE_DIR = Path(__file__).resolve().parent
UI_DIST_INDEX = BASE_DIR / "ui" / "dist" / "index.html"


def is_port_listening(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def wait_for_server_ready(host: str, port: int, max_wait_sec: float = 15.0) -> bool:
    deadline = time.time() + max_wait_sec
    while time.time() < deadline:
        if is_port_listening(host, port):
            return True
        time.sleep(0.15)
    return False


def find_chromium_binary() -> Optional[str]:
    """Locates Chrome or Edge executable to run JARVIS HUD in isolated `--app` mode."""
    candidates: List[str] = []
    if sys.platform.startswith("win"):
        prog_files = [
            os.environ.get("PROGRAMFILES", r"C:\Program Files"),
            os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
            os.environ.get("LOCALAPPDATA", ""),
        ]
        rel_paths = [
            r"Google\Chrome\Application\chrome.exe",
            r"Microsoft\Edge\Application\msedge.exe",
            r"BraveSoftware\Brave-Browser\Application\brave.exe",
        ]
        for root in prog_files:
            if not root:
                continue
            for rel in rel_paths:
                full = os.path.join(root, rel)
                if os.path.isfile(full):
                    candidates.append(full)

    for binary_name in ("chrome", "google-chrome", "msedge", "chromium", "chromium-browser"):
        resolved = shutil.which(binary_name)
        if resolved:
            candidates.append(resolved)

    return candidates[0] if candidates else None


def launch_hud_app_window(url: str) -> Optional[subprocess.Popen]:
    """
    Launches the JARVIS HUD in Chromium's multi-process `--app` mode so UI rendering
    never shares a process or GIL with Python/FastAPI.
    """
    browser_bin = find_chromium_binary()
    hud_profile_dir = BASE_DIR / ".hud_app_profile"
    hud_profile_dir.mkdir(parents=True, exist_ok=True)

    if browser_bin:
        args = [
            browser_bin,
            f"--app={url}",
            f"--user-data-dir={hud_profile_dir}",
            "--window-size=1440,900",
            "--disable-features=Translate",
            "--no-first-run",
            "--no-default-browser-check",
        ]
        try:
            return subprocess.Popen(
                args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as exc:
            print(f"[JARVIS Supervisor] Chromium --app launch failed ({exc}); falling back to default browser.")

    webbrowser.open(url)
    return None


def ensure_frontend_built() -> None:
    if UI_DIST_INDEX.exists():
        return
    ui_dir = BASE_DIR / "ui"
    if (ui_dir / "package.json").exists():
        npm_cmd = "npm.cmd" if sys.platform.startswith("win") else "npm"
        if shutil.which(npm_cmd):
            print("[JARVIS Supervisor] ui/dist missing; building React HUD via npm run build...")
            subprocess.run([npm_cmd, "run", "build"], cwd=str(ui_dir), check=False)


def run_backend_server() -> subprocess.Popen:
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "automation.server:app",
        "--host",
        HOST,
        "--port",
        str(PORT),
        "--log-level",
        "info",
    ]
    return subprocess.Popen(cmd, cwd=str(BASE_DIR))


def main() -> None:
    init_config_files()
    ensure_frontend_built()

    if "--server-only" in sys.argv:
        uvicorn.run("automation.server:app", host=HOST, port=PORT, log_level="info")
        return

    print(f"[JARVIS 2.0 Supervisor] Starting FastAPI + WebSocket backend on {APP_URL} ...")
    backend_proc = run_backend_server()
    hud_proc: Optional[subprocess.Popen] = None

    def _graceful_shutdown(*_args):
        print("\n[JARVIS 2.0 Supervisor] Shutting down HUD and backend processes...")
        if hud_proc and hud_proc.poll() is None:
            try:
                hud_proc.terminate()
            except Exception:
                pass
        if backend_proc.poll() is None:
            try:
                backend_proc.terminate()
                backend_proc.wait(timeout=4.0)
            except Exception:
                try:
                    backend_proc.kill()
                except Exception:
                    pass
        sys.exit(0)

    signal.signal(signal.SIGINT, _graceful_shutdown)
    signal.signal(signal.SIGTERM, _graceful_shutdown)

    if not wait_for_server_ready(HOST, PORT, max_wait_sec=20.0):
        print("[JARVIS 2.0 Supervisor] ERROR: Backend failed to bind to 127.0.0.1:5050.")
        _graceful_shutdown()

    print("[JARVIS 2.0 Supervisor] Backend online. Launching Chromium --app Holographic HUD...")
    hud_proc = launch_hud_app_window(APP_URL)

    try:
        while True:
            if backend_proc.poll() is not None:
                print("[JARVIS 2.0 Supervisor] Backend process exited. Closing supervisor.")
                break
            if hud_proc is not None and hud_proc.poll() is not None:
                print("[JARVIS 2.0 Supervisor] HUD window closed by user. Stopping backend...")
                break
            time.sleep(0.5)
    finally:
        _graceful_shutdown()


if __name__ == "__main__":
    main()
