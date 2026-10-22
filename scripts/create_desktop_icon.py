#!/usr/bin/env python3
"""
Desktop Shortcut & Geometric Arc-Cyan HUD Icon Generator for JARVIS 2.0
Programmatically generates the Marvel HUD icon (jarvis.png and jarvis.ico)
using Pillow supersampling, and creates native clickable desktop launchers.
"""

import math
import os
import sys
import platform
import subprocess
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
MAIN_PY = BASE_DIR / "main.py"
ASSETS_DIR = BASE_DIR / "ui" / "assets"
ICON_ICO = ASSETS_DIR / "jarvis.ico"
ICON_PNG = ASSETS_DIR / "jarvis.png"


def generate_geometric_hud_icon(ico_path: Path, png_path: Path) -> None:
    """
    Programmatically creates an Arc-Cyan Holographic Reactor HUD icon
    with concentric segmented arcs, tick-marks, and central energy core.
    Draws on a 1024x1024 supersampled canvas and downsamples for crisp edges.
    """
    from PIL import Image, ImageDraw

    os.makedirs(ico_path.parent, exist_ok=True)
    canvas_size = 1024
    center = canvas_size // 2
    img = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 1. Dark Chamfered Background Hexagon / Circle Badge
    badge_radius = 490
    bg_color = (6, 10, 18, 250)  # #060A12 deep space dark
    draw.ellipse(
        [center - badge_radius, center - badge_radius, center + badge_radius, center + badge_radius],
        fill=bg_color,
        outline=(0, 229, 255, 120),  # Subtle outer cyan border
        width=4,
    )

    # 2. Outer Segmented Arc Ring (Cyan #00E5FF)
    arc_radius = 430
    arc_width = 16
    cyan = (0, 229, 255, 255)
    cyan_dim = (0, 229, 255, 100)
    gold = (255, 179, 0, 255)  # Reactor Gold #FFB300

    # Draw 4 segmented arcs
    for start_deg, end_deg in [(15, 75), (105, 165), (195, 255), (285, 345)]:
        draw.arc(
            [center - arc_radius, center - arc_radius, center + arc_radius, center + arc_radius],
            start=start_deg,
            end=end_deg,
            fill=cyan,
            width=arc_width,
        )

    # 3. Intermediate Dashed Sensor Ring
    mid_radius = 360
    draw.ellipse(
        [center - mid_radius, center - mid_radius, center + mid_radius, center + mid_radius],
        outline=cyan_dim,
        width=3,
    )

    # 12 Radial telemetry tick marks
    for i in range(12):
        angle = math.radians(i * 30)
        r_inner = mid_radius - (22 if i % 3 == 0 else 12)
        r_outer = mid_radius + (22 if i % 3 == 0 else 12)
        x1 = center + r_inner * math.cos(angle)
        y1 = center + r_inner * math.sin(angle)
        x2 = center + r_outer * math.cos(angle)
        y2 = center + r_outer * math.sin(angle)
        tick_color = gold if i % 3 == 0 else cyan
        draw.line([(x1, y1), (x2, y2)], fill=tick_color, width=5 if i % 3 == 0 else 3)

    # 4. Concentric Inner HUD Ring
    inner_radius = 270
    draw.ellipse(
        [center - inner_radius, center - inner_radius, center + inner_radius, center + inner_radius],
        outline=cyan,
        width=8,
    )

    # 5. Hexagonal Reactor Frame
    hex_radius = 210
    hex_points = []
    for i in range(6):
        angle = math.radians(i * 60 - 30)
        hx = center + hex_radius * math.cos(angle)
        hy = center + hex_radius * math.sin(angle)
        hex_points.append((hx, hy))
    draw.polygon(hex_points, outline=cyan, fill=(0, 229, 255, 30))

    # 6. Central Arc Reactor Core (Glowing Central Node)
    core_radius = 110
    draw.ellipse(
        [center - core_radius, center - core_radius, center + core_radius, center + core_radius],
        fill=(0, 229, 255, 180),
        outline=gold,
        width=6,
    )

    # Inner bright hot-spot
    hot_radius = 55
    draw.ellipse(
        [center - hot_radius, center - hot_radius, center + hot_radius, center + hot_radius],
        fill=(255, 255, 255, 240),
        outline=cyan,
        width=4,
    )

    # 3 Inverted Reactor Blades inside core
    for i in range(3):
        angle = math.radians(i * 120 - 90)
        bx = center + (core_radius - 10) * math.cos(angle)
        by = center + (core_radius - 10) * math.sin(angle)
        draw.line([(center, center), (bx, by)], fill=gold, width=5)

    # 7. Supersampled High-Quality Export
    png_256 = img.resize((256, 256), Image.Resampling.LANCZOS)
    png_256.save(png_path, format="PNG")
    print(f"[OK] Generated Arc-Cyan PNG Icon: {png_path}")

    # Generate Multi-Resolution ICO
    ico_sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    img.save(ico_path, format="ICO", sizes=ico_sizes)
    print(f"[OK] Generated Arc-Cyan Windows ICO: {ico_path}")


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
    pythonw_exe = Path(python_exe).parent / "pythonw.exe"
    target_exe = str(pythonw_exe if pythonw_exe.exists() else python_exe)

    icon_path = str(ICON_ICO if ICON_ICO.exists() else ICON_PNG)

    # 1. Native Windows .lnk shortcut via PowerShell WScript.Shell
    ps_command = f"""
$ws = New-Object -ComObject WScript.Shell
$s = $ws.CreateShortcut('{str(shortcut_path)}')
$s.TargetPath = '{target_exe}'
$s.Arguments = '"{str(MAIN_PY)}"'
$s.WorkingDirectory = '{str(BASE_DIR)}'
$s.IconLocation = '{icon_path}'
$s.Description = 'J.A.R.V.I.S. 2.0 Autonomous OS Agent & Holographic HUD'
$s.Save()
"""
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_command],
            check=True,
            capture_output=True,
            text=True,
        )
        print(f"[OK] Created Windows Shortcut: {shortcut_path}")
    except Exception as e:
        print(f"[!] PowerShell shortcut creation notice: {e}")

    # 2. Reliable .bat launcher in case LNK creation is restricted
    bat_content = f"""@echo off
title JARVIS 2.0 Assistant
cd /d "{str(BASE_DIR)}"
start "" "{target_exe}" "{str(MAIN_PY)}"
"""
    try:
        with open(bat_path, "w", encoding="utf-8") as f:
            f.write(bat_content)
        print(f"[OK] Created Batch Launcher: {bat_path}")
    except Exception as e:
        print(f"[!] Batch launcher creation notice: {e}")

    return shortcut_path


def create_linux_desktop_file(desktop_dir: Path) -> Path:
    """Create Linux .desktop application launcher."""
    desktop_file = desktop_dir / "jarvis.desktop"
    icon_path = str(ICON_PNG if ICON_PNG.exists() else ICON_ICO)

    content = f"""[Desktop Entry]
Version=2.0
Type=Application
Name=J.A.R.V.I.S. 2.0
Comment=Autonomous OS Agent & Holographic HUD
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
    print(f"JARVIS 2.0 Desktop Launcher Generator (OS: {os_name})")
    print("=" * 60)
    print(f"Target Project: {BASE_DIR}")
    print(f"Main Script:    {MAIN_PY}")
    print(f"Python Binary:  {sys.executable}")
    print(f"Desktop Folder: {desktop}\n")

    if not MAIN_PY.exists():
        print(f"[Error] main.py not found at {MAIN_PY}")
        sys.exit(1)

    # 1. Programmatically Generate Arc-Cyan HUD Icon
    print("[1/2] Generating Geometric Arc-Cyan HUD Icons...")
    try:
        generate_geometric_hud_icon(ICON_ICO, ICON_PNG)
    except Exception as e:
        print(f"[!] Icon generation fallback notice: {e}")

    # 2. Generate OS-Specific Desktop Launcher
    print("\n[2/2] Generating Desktop Shortcuts...")
    if os_name == "Windows":
        shortcut = create_windows_shortcut(desktop)
    elif os_name == "Linux":
        shortcut = create_linux_desktop_file(desktop)
    elif os_name == "Darwin":
        shortcut = create_macos_command_file(desktop)
    else:
        shortcut = create_macos_command_file(desktop)

    print("\n[SUCCESS] Desktop application launcher and HUD icons complete!")


if __name__ == "__main__":
    main()
