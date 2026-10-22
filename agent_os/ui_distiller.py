#!/usr/bin/env python3
"""
UI Distiller for JARVIS 2.0
Extracts active OS window accessibility trees and interactive control coordinates (x, y, w, h).
Uses Windows UIAutomation / pywinauto when available, with a resilient fallback grid.
"""

import platform
from typing import Any, Dict, List, Optional


class UIDistiller:
    """
    Inspects desktop windows and extracts bounding boxes for interactive UI controls.
    """

    def __init__(self):
        self.os_type = platform.system()

    def get_interactive_elements(self, max_elements: int = 50) -> List[Dict[str, Any]]:
        """
        Extract interactive elements from the currently focused or active application window.
        Returns: list of {"id": int, "name": str, "type": str, "bbox": [x, y, w, h], "center": [cx, cy]}
        """
        elements: List[Dict[str, Any]] = []

        if self.os_type == "Windows":
            try:
                elements = self._extract_windows_uia(max_elements)
            except Exception as e:
                print(f"[UIDistiller] Windows UIA extraction notice: {e}")

        # If OS inspection returns few elements or is running in headless/fallback mode:
        if not elements:
            elements = self._generate_fallback_grid()

        return elements[:max_elements]

    def _extract_windows_uia(self, max_elements: int) -> List[Dict[str, Any]]:
        """Extract controls using comtypes / uiautomation or pywinauto."""
        extracted: List[Dict[str, Any]] = []

        try:
            import pywinauto
            from pywinauto import Desktop

            desktop = Desktop(backend="uia")
            active_window = desktop.active()
            if not active_window:
                return []

            ctrls = active_window.descendants()
            idx = 1
            for c in ctrls:
                try:
                    rect = c.rectangle()
                    width = rect.width()
                    height = rect.height()

                    # Filter out invisible or microscopic elements
                    if width < 12 or height < 12 or width > 3000 or height > 3000:
                        continue

                    name = c.window_text() or c.element_info.name or ""
                    ctrl_type = c.element_info.control_type or "Control"

                    cx = rect.left + width // 2
                    cy = rect.top + height // 2

                    extracted.append({
                        "id": idx,
                        "name": str(name)[:40],
                        "type": str(ctrl_type),
                        "bbox": [rect.left, rect.top, width, height],
                        "center": [cx, cy],
                    })
                    idx += 1
                    if len(extracted) >= max_elements:
                        break
                except Exception:
                    continue

        except Exception:
            pass

        return extracted

    def _generate_fallback_grid(self) -> List[Dict[str, Any]]:
        """
        Creates a clean 4x3 screen coordinate reference grid if accessibility APIs are restricted.
        """
        try:
            from PIL import ImageGrab
            screen = ImageGrab.grab()
            screen_w, screen_h = screen.size
        except Exception:
            screen_w, screen_h = 1920, 1080

        grid = []
        cols = 4
        rows = 3
        cell_w = screen_w // cols
        cell_h = screen_h // rows

        idx = 1
        for r in range(rows):
            for c in range(cols):
                x = c * cell_w + 20
                y = r * cell_h + 20
                w = cell_w - 40
                h = cell_h - 40
                grid.append({
                    "id": idx,
                    "name": f"Sector R{r+1}C{c+1}",
                    "type": "Region",
                    "bbox": [x, y, w, h],
                    "center": [x + w // 2, y + h // 2],
                })
                idx += 1

        return grid


# Singleton instance
ui_distiller = UIDistiller()
