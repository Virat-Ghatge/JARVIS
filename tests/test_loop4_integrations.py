#!/usr/bin/env python3
"""
Test Suite for Loop 4: MCP Client, Skills/Teach Mode, Clipboard Copilot, Workspace RAG & Smart Meetings
"""

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from automation.meeting_bot import MeetingBot
from integrations.handlers.clipboard_copilot import ClipboardCopilot
from integrations.mcp_client import MCPClientHub
from integrations.skill_store import SkillStore
from integrations.workspace_rag import WorkspaceRAG


class TestLoop4Integrations(unittest.TestCase):
    def setUp(self):
        self.skills = SkillStore()
        self.copilot = ClipboardCopilot()
        self.rag = WorkspaceRAG()
        self.mcp = MCPClientHub()
        self.bot = MeetingBot()

    def test_skill_store_add_delete_and_teach_mode(self):
        # 1. Start Teach Mode
        init_res = self.skills.start_teach_mode("Night Routine", ["night routine", "good night"])
        self.assertTrue(self.skills.is_teaching())
        self.assertEqual(init_res["name"], "Night Routine")

        # 2. Record Steps
        self.skills.record_step("mute volume")
        self.skills.record_step("tell me the time")

        # 3. Stop Teach Mode and Save
        saved_skill = self.skills.stop_teach_mode(save=True)
        self.assertFalse(self.skills.is_teaching())
        self.assertIsNotNone(saved_skill)
        self.assertEqual(len(saved_skill["steps"]), 2)

        # 4. Verify skill is present in list
        all_skills = self.skills.get_skills()
        matching = [s for s in all_skills if s.get("id") == saved_skill["id"]]
        self.assertEqual(len(matching), 1)

        # 5. Clean up
        deleted = self.skills.delete_skill(saved_skill["id"])
        self.assertTrue(deleted)

    def test_clipboard_copilot(self):
        sample_text = "JARVIS is an autonomous artificial intelligence operating system."
        with patch("core.llm_router.router.query_text", return_value="Summary: JARVIS is an AI OS."):
            res = self.copilot.act_on_clipboard("summarize this text", custom_text=sample_text)
            self.assertIn("Summary:", res)

        sample_code = "def add(a, b) return a + b"
        with patch("core.llm_router.router.query_text", return_value="Fix: added colon after add(a, b):"):
            res_fix = self.copilot.act_on_clipboard("fix this code", custom_text=sample_code)
            self.assertIn("Fix:", res_fix)

    def test_workspace_rag_indexing_and_search(self):
        temp_dir = Path(tempfile.mkdtemp(prefix="jarvis_rag_test_"))
        try:
            # Create sample files
            doc1 = temp_dir / "quantum_computing.md"
            doc1.write_text(
                "# Quantum Teleportation Protocol\n"
                "Quantum state transfer relies on entangled Bell pairs and classical communication channels.\n"
                "Qubits are manipulated using Hadamard and CNOT gates.\n",
                encoding="utf-8",
            )

            doc2 = temp_dir / "calculator.py"
            doc2.write_text(
                "def calculate_trajectory(velocity, angle):\n"
                "    import math\n"
                "    return (velocity ** 2) * math.sin(2 * angle) / 9.8\n",
                encoding="utf-8",
            )

            # Index temporary directory
            index_result = self.rag.index_workspace(temp_dir)
            self.assertTrue(index_result["ok"])
            self.assertEqual(index_result["files_indexed"], 2)
            self.assertGreaterEqual(index_result["chunks_count"], 2)

            # Search keyword
            results = self.rag.search("entangled Bell pairs", top_k=2)
            self.assertGreaterEqual(len(results), 1)
            first_match = results[0]
            self.assertEqual(first_match["filename"], "quantum_computing.md")
            self.assertIn("Bell pairs", first_match["text"])

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_meeting_caption_summarization(self):
        self.bot.live_captions = [
            {"text": "Alice: Welcome everyone to the quarterly roadmap review.", "timestamp": "14:00:10", "platform": "teams"},
            {"text": "Bob: We need to finalize the API vault before Friday.", "timestamp": "14:02:40", "platform": "teams"},
            {"text": "Alice: Agreed. Bob will own the release pipeline.", "timestamp": "14:05:00", "platform": "teams"},
        ]

        with patch("core.llm_router.router.query_text", return_value="Executive Summary: Roadmaps reviewed. Bob owns release pipeline."):
            summary = self.bot._generate_post_call_summary("Quarterly Roadmap Review")
            self.assertIsNotNone(summary)
            self.assertEqual(summary["title"], "Quarterly Roadmap Review")
            self.assertEqual(summary["captions_count"], 3)
            self.assertIn("Executive Summary", summary["summary"])

    def test_mcp_client_hub_list(self):
        tools = self.mcp.list_tools()
        self.assertIsInstance(tools, list)
        self.assertGreaterEqual(len(tools), 1)
        self.assertEqual(tools[0]["server"], "filesystem")


if __name__ == "__main__":
    unittest.main()
