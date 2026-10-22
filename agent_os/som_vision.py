#!/usr/bin/env python3
"""
Set-of-Mark (SoM) Vision Renderer for JARVIS 2.0
Captures desktop screenshots and overlays numbered Arc Cyan (#00E5FF) bounding boxes
and telemetry tags on interactive regions for Vision LLM consumption.
"""

import base64
import io
from typing import Any, Dict, List, Optional, Tuple
from PIL import Image, ImageDraw, ImageFont


class SOMVision:
    """
    Renders Set-of-Mark visual annotations on desktop screenshots.
    """

    ARC_CYAN = (0, 229, 255)
    BACKGROUND_DARK = (6, 10, 18, 220)
    TEXT_WHITE = (230, 247, 255)

    def capture_screen(self) -> Image.Image:
        """Captures primary desktop display image."""
        try:
            import mss
            with mss.mss() as sct:
                monitor = sct.monitors[1]
                sct_img = sct.grab(monitor)
                return Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
        except Exception:
            pass

        try:
            from PIL import ImageGrab
            return ImageGrab.grab().convert("RGB")
        except Exception:
            # Fallback synthetic canvas for headless environments
            return Image.new("RGB", (1280, 720), color=(10, 16, 26))

    def render_som(
        self,
        image: Image.Image,
        elements: List[Dict[str, Any]],
        box_color: Tuple[int, int, int] = ARC_CYAN,
    ) -> Tuple[Image.Image, str]:
        """
        Draws numbered cyan bounding boxes with high-contrast label badges.
        Returns: (annotated_pil_image, base64_png_string)
        """
        annotated = image.copy()
        draw = ImageDraw.Draw(annotated, "RGBA")

        # Load default font
        try:
            font = ImageFont.load_default()
        except Exception:
            font = None

        for el in elements:
            idx = el.get("id", 0)
            bbox = el.get("bbox", [0, 0, 0, 0])
            x, y, w, h = bbox

            if w <= 0 or h <= 0:
                continue

            # Draw outer Arc Cyan bounding box
            draw.rectangle(
                [x, y, x + w, y + h],
                outline=box_color + (255,),
                width=2,
            )

            # Draw label badge at top-left of box
            label_text = f"[{idx}]"
            badge_w = 26 + (len(str(idx)) * 6)
            badge_h = 16

            badge_x = max(0, x)
            badge_y = max(0, y - badge_h)

            draw.rectangle(
                [badge_x, badge_y, badge_x + badge_w, badge_y + badge_h],
                fill=self.BACKGROUND_DARK,
                outline=box_color + (200,),
                width=1,
            )

            draw.text(
                (badge_x + 4, badge_y + 2),
                label_text,
                fill=self.TEXT_WHITE,
                font=font,
            )

        # Encode to Base64 PNG
        buffered = io.BytesIO()
        annotated.save(buffered, format="PNG")
        b64_str = base64.b64encode(buffered.getvalue()).decode("utf-8")

        return annotated, b64_str

    def capture_and_annotate(self, elements: List[Dict[str, Any]]) -> Tuple[Image.Image, str]:
        """Convenience method: capture screen and overlay SoM boxes in one call."""
        img = self.capture_screen()
        return self.render_som(img, elements)


# Global SoM vision instance
som_vision = SOMVision()
