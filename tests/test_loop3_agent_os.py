#!/usr/bin/env python3
"""
Test Suite for Loop 3: 3-Tier Dynamic OS Agent & Safety Interceptor
"""

import base64
import threading
import time
import unittest
from unittest.mock import MagicMock, patch
from PIL import Image

from agent_os.code_executor import CodeExecutor
from agent_os.os_actuator import OSActuator
from agent_os.safety_interceptor import SafetyInterceptor
from agent_os.som_vision import SOMVision
from agent_os.ui_distiller import UIDistiller


class TestLoop3AgentOS(unittest.TestCase):
    def setUp(self):
        self.safety = SafetyInterceptor()
        self.som = SOMVision()
        self.actuator = OSActuator()
        self.executor = CodeExecutor()
        self.distiller = UIDistiller()

    def test_som_vision_rendering(self):
        # Create a synthetic canvas
        test_img = Image.new("RGB", (640, 480), color=(15, 25, 40))
        elements = [
            {"id": 1, "name": "Submit Button", "type": "Button", "bbox": [50, 50, 120, 40], "center": [110, 70]},
            {"id": 2, "name": "Search Box", "type": "Edit", "bbox": [200, 100, 300, 35], "center": [350, 117]},
        ]

        annotated_img, b64_png = self.som.render_som(test_img, elements)
        self.assertIsNotNone(annotated_img)
        self.assertIsInstance(b64_png, str)
        self.assertGreater(len(b64_png), 100)

        # Verify decoded bytes are valid PNG
        decoded = base64.b64decode(b64_png)
        self.assertTrue(decoded.startswith(b"\x89PNG\r\n\x1a\n"))

    def test_safety_interceptor_detection(self):
        risky_code = """
import os
import shutil
os.remove('C:\\important_file.dat')
"""
        is_safe, reason = self.safety.inspect_code(risky_code)
        self.assertFalse(is_safe)
        self.assertIn("os.remove", reason)

        rmtree_code = "shutil.rmtree('/var/data')"
        is_safe_rm, reason_rm = self.safety.inspect_code(rmtree_code)
        self.assertFalse(is_safe_rm)
        self.assertIn("shutil.rmtree", reason_rm)

        safe_code = """
import math
print("The square root of 144 is", math.sqrt(144))
"""
        is_safe_good, _ = self.safety.inspect_code(safe_code)
        self.assertTrue(is_safe_good)

    def test_safety_interceptor_approval_flow(self):
        # Test approval grant
        approval_result = None

        def requester():
            nonlocal approval_result
            approval_result = self.safety.request_approval(
                action_type="file_delete",
                description="Testing deletion approval",
                preview="os.remove('test.tmp')",
                timeout_sec=5,
            )

        t = threading.Thread(target=requester)
        t.start()

        # Wait for request to register
        time.sleep(0.05)
        self.assertEqual(len(self.safety._pending_requests), 1)
        req_id = list(self.safety._pending_requests.keys())[0]

        # User approves
        success = self.safety.approve(req_id)
        self.assertTrue(success)
        t.join(timeout=2.0)
        self.assertTrue(approval_result)

        # Test denial
        denial_result = None

        def requester_deny():
            nonlocal denial_result
            denial_result = self.safety.request_approval(
                action_type="file_delete",
                description="Testing denial flow",
                preview="del *.*",
                timeout_sec=5,
            )

        t2 = threading.Thread(target=requester_deny)
        t2.start()

        time.sleep(0.05)
        self.assertEqual(len(self.safety._pending_requests), 1)
        req_id2 = list(self.safety._pending_requests.keys())[0]

        # User denies
        success = self.safety.deny(req_id2)
        self.assertTrue(success)
        t2.join(timeout=2.0)
        self.assertFalse(denial_result)

    def test_code_executor_safe_script(self):
        with patch.object(
            self.executor,
            "synthesize_script",
            return_value="print('CALCULATION_RESULT:', sum(range(10)))",
        ):
            res = self.executor.execute_task("compute sum of 0 to 9")
            self.assertTrue(res["ok"])
            self.assertIn("CALCULATION_RESULT: 45", res["output"])
            self.assertIn("duration_ms", res)
            self.assertGreaterEqual(res["duration_ms"], 0)

    def test_os_actuator_abort_kill_switch(self):
        self.actuator.reset_abort()
        self.assertFalse(self.actuator.is_aborted())

        self.actuator.abort()
        self.assertTrue(self.actuator.is_aborted())

        # When aborted, all actuator commands must abort immediately
        res_click = self.actuator.click(100, 200)
        self.assertFalse(res_click)

        res_type = self.actuator.type_text("test")
        self.assertFalse(res_type)

        res_hotkey = self.actuator.press_hotkey("ctrl+c")
        self.assertFalse(res_hotkey)

    def test_ui_distiller_fallback_grid(self):
        elements = self.distiller.get_interactive_elements(max_elements=12)
        self.assertGreaterEqual(len(elements), 1)
        first = elements[0]
        self.assertIn("id", first)
        self.assertIn("bbox", first)
        self.assertIn("center", first)


if __name__ == "__main__":
    unittest.main()
