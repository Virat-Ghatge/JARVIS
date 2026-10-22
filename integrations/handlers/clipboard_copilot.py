#!/usr/bin/env python3
"""
Universal Clipboard & Selection Copilot for JARVIS 2.0
Enables instant "Act on This" voice and text interactions on clipboard contents:
- "Summarize clipboard / this"
- "Fix this code"
- "Explain this"
- "Translate selection"
"""

import re
from typing import Optional
from core.llm_router import router

try:
    import pyperclip
    PYPERCLIP_AVAILABLE = True
except ImportError:
    PYPERCLIP_AVAILABLE = False


class ClipboardCopilot:
    """
    Reads OS clipboard and executes AI-assisted transformations and analysis.
    """

    def get_clipboard_text(self) -> str:
        """Fetch plain text from OS clipboard."""
        if PYPERCLIP_AVAILABLE:
            try:
                return pyperclip.paste() or ""
            except Exception as e:
                print(f"[ClipboardCopilot] pyperclip paste error: {e}")

        # Fallback using tkinter
        try:
            import tkinter as tk
            root = tk.Tk()
            root.withdraw()
            text = root.clipboard_get()
            root.destroy()
            return text or ""
        except Exception:
            return ""

    def set_clipboard_text(self, text: str) -> bool:
        """Write plain text to OS clipboard."""
        if PYPERCLIP_AVAILABLE:
            try:
                pyperclip.copy(text)
                return True
            except Exception:
                pass
        return False

    def act_on_clipboard(self, user_command: str, custom_text: Optional[str] = None) -> str:
        """
        Executes action on current clipboard contents based on command query.
        """
        content = custom_text if custom_text is not None else self.get_clipboard_text()
        if not content or not content.strip():
            return "Your clipboard is currently empty, sir. Please copy some text or code first."

        cmd = user_command.lower()

        # 1. Summarization
        if any(k in cmd for k in ["summarize", "tldr", "brief", "summary"]):
            system_prompt = (
                "You are JARVIS. Summarize the following clipboard text concisely. "
                "Highlight key takeaways in crisp bullet points."
            )
            prompt = f"Text to summarize:\n\"\"\"\n{content[:4000]}\n\"\"\""
            return router.query_text("qa_chat", prompt, system_prompt=system_prompt)

        # 2. Fix Code
        elif any(k in cmd for k in ["fix code", "debug", "fix this", "correct this code", "find bug"]):
            system_prompt = (
                "You are JARVIS expert software engineer. Review the provided code snippet from the clipboard. "
                "1. Identify the bug or inefficiency.\n"
                "2. Provide the corrected, production-ready code.\n"
                "3. Explain what was fixed in 1-2 concise sentences."
            )
            prompt = f"Code to review and fix:\n```\n{content[:4000]}\n```"
            fixed = router.query_text("qa_chat", prompt, system_prompt=system_prompt)
            return fixed

        # 3. Explain Selection
        elif any(k in cmd for k in ["explain", "what does this mean", "break down"]):
            system_prompt = (
                "You are JARVIS. Explain the following text or code simply, clearly, and concisely. "
                "Break down complex terminology or algorithms."
            )
            prompt = f"Content to explain:\n\"\"\"\n{content[:4000]}\n\"\"\""
            return router.query_text("qa_chat", prompt, system_prompt=system_prompt)

        # 4. Translation
        elif "translate" in cmd:
            target_lang = "English"
            if "to " in cmd:
                target_lang = cmd.split("to ")[-1].strip().capitalize()
            system_prompt = f"Translate the following text faithfully and accurately into {target_lang}."
            prompt = f"Text to translate:\n\"\"\"\n{content[:4000]}\n\"\"\""
            return router.query_text("qa_chat", prompt, system_prompt=system_prompt)

        # Default action: general Q&A grounded on clipboard
        system_prompt = "You are JARVIS. Answer the user query using the following clipboard content as context."
        prompt = f"Context from clipboard:\n\"\"\"\n{content[:4000]}\n\"\"\"\n\nUser Question: {user_command}"
        return router.query_text("qa_chat", prompt, system_prompt=system_prompt)


# Global clipboard copilot singleton
clipboard_copilot = ClipboardCopilot()
