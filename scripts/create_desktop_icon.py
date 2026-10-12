#!/usr/bin/env python3
"""
Desktop Shortcut & Application Launcher Generator for JARVIS
Cross-platform support for Windows, Linux, and macOS.
Generates clickable desktop entry pointing to python main.py with the JARVIS icon.
"""

import os
import sys
import platform
import subprocess
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
MAIN_PY = BASE_DIR / "main.py"
ICON_ICO = BASE_DIR / "ui" / "assets" / "jarvis.ico"
ICON_PNG = BASE_DIR / "ui" / "assets" / "jarvis.png"


def get_desktop_dir() -> Path:
    """Resolve the user's Desktop directory cross-platform."""
    home = Path(os.path.expanduser("~"))
    desktop = home / "Desktop"

    # Handle OneDrive redirected desktop on Windows if present
    onedrive_desktop = home / "OneDrive" / "Desktop"
    if onedrive_desktop.exists():
        return onedrive_desktop

    if desktop.exists():
        return desktop

    return home


def create_windows_shortcut(desktop_dir: Path) -> Path:
    """Create Windows .lnk shortcut and fallback .bat launcher."""
    shortcut_path = desktop_dir / "JARVIS Assistant.lnk"
    bat_path = desktop_dir / "Launch JARVIS.bat"

    python_exe = sys.executable
    # Prefer pythonw.exe if available in same directory to avoid persistent console window
    pythonw_exe = Path(python_exe).parent / "pythonw.exe"
    target_exe = str(pythonw_exe if pythonw_exe.exists() else python_exe)

    icon_path = str(ICON_ICO if ICON_ICO.exists() else ICON_PNG)

    # 1. Create native Windows .lnk shortcut via PowerShell WScript.Shell
    ps_command = f"""
$ws = New-Object -ComObject WScript.Shell
$s = $ws.CreateShortcut('{str(shortcut_path)}')
$s.TargetPath = '{target_exe}'
$s.Arguments = '"{str(MAIN_PY)}"'
$s.WorkingDirectory = '{str(BASE_DIR)}'
$s.IconLocation = '{icon_path}'
$s.Description = 'J.A.R.V.I.S. Desktop Assistant'
$s.Save()
"""
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_command],
            check=True,
            capture_output=True,
            text=True
        )
        print(f"[OK] Created Windows Shortcut: {shortcut_path}")
    except Exception as e:
        print(f"[!] PowerShell shortcut creation warning: {e}")

    # 2. Also create reliable .bat launcher in case LNK creation is restricted
    bat_content = f"""@echo off
title JARVIS Assistant
cd /d "{str(BASE_DIR)}"
start "" "{target_exe}" "{str(MAIN_PY)}"
"""
    try:
        with open(bat_path, "w", encoding="utf-8") as f:
            f.write(bat_content)
        print(f"[OK] Created Batch Launcher: {bat_path}")
    except Exception as e:
        print(f"[!] Batch launcher creation warning: {e}")

    return shortcut_path


def create_linux_desktop_file(desktop_dir: Path) -> Path:
    """Create Linux .desktop application launcher."""
    desktop_file = desktop_dir / "jarvis.desktop"
    icon_path = str(ICON_PNG if ICON_PNG.exists() else ICON_ICO)

    content = f"""[Desktop Entry]
Version=1.0
Type=Application
Name=J.A.R.V.I.S.
Comment=Desktop AI Voice & Text Assistant
Exec={sys.executable} "{str(MAIN_PY)}"
Path={str(BASE_DIR)}
Icon={icon_path}
Terminal=false
Categories=Utility;Development;
"""
    with open(desktop_file, "w", encoding="utf-8") as f:
        f.write(content)

    os.chmod(desktop_file, 0o755)
    print(f"[OK] Created Linux Desktop Entry: {desktop_file}")

    # Also install to local applications menu if directory exists
    apps_dir = Path(os.path.expanduser("~")) / ".local" / "share" / "applications"
    if apps_dir.exists():
        app_file = apps_dir / "jarvis.desktop"
        with open(app_file, "w", encoding="utf-8") as f:
            f.write(content)
        os.chmod(app_file, 0o755)
        print(f"[OK] Added to Applications menu: {app_file}")

    return desktop_file


def create_macos_command_file(desktop_dir: Path) -> Path:
    """Create macOS clickable .command launcher."""
    cmd_file = desktop_dir / "JARVIS.command"
    content = f"""#!/bin/bash
cd "{str(BASE_DIR)}"
"{sys.executable}" "{str(MAIN_PY)}"
"""
    with open(cmd_file, "w", encoding="utf-8") as f:
        f.write(content)

    os.chmod(cmd_file, 0o755)
    print(f"[OK] Created macOS Command Launcher: {cmd_file}")
    return cmd_file


def main():
    os_name = platform.system()
    desktop = get_desktop_dir()

    print("=" * 60)
    print(f"JARVIS Desktop Launcher Generator (OS: {os_name})")
    print("=" * 60)
    print(f"Target Project: {BASE_DIR}")
    print(f"Main Script:    {MAIN_PY}")
    print(f"Python Binary:  {sys.executable}")
    print(f"Desktop Folder: {desktop}\n")

    if not MAIN_PY.exists():
        print(f"[Error] main.py not found at {MAIN_PY}")
        sys.exit(1)

    if os_name == "Windows":
        shortcut = create_windows_shortcut(desktop)
    elif os_name == "Linux":
        shortcut = create_linux_desktop_file(desktop)
    elif os_name == "Darwin":
        shortcut = create_macos_command_file(desktop)
    else:
        print(f"[!] Unsupported OS '{os_name}', creating fallback batch/shell file.")
        shortcut = create_macos_command_file(desktop)

    print("\n[SUCCESS] Desktop application launcher generation complete!")


if __name__ == "__main__":
    main()
