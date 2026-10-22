#!/usr/bin/env python3
"""
Safety Interceptor & Risk Gatekeeper for JARVIS 2.0
Inspects synthesized code and operating system actions before execution.
Triggers HUD Approval Modal events for destructive operations when Autonomous Trust Mode is OFF.
"""

import re
import threading
import time
import uuid
from typing import Any, Callable, Dict, List, Optional, Tuple

from config.settings import get_vault


class SafetyInterceptor:
    """
    Evaluates risks in scripts and actions. Intercepts dangerous operations
    and prompts for approval via the Holographic HUD Approval Modal.
    """

    DESTRUCTIVE_PATTERNS = [
        r"\brm\s+-rf\b",
        r"\brmdir\s+/[sS]\b",
        r"\bdel\s+/[fFqQsS]\b",
        r"\bdel\s+[*]\b",
        r"\bformat\s+[a-zA-Z]:",
        r"\bshutil\.rmtree\b",
        r"\bos\.remove\b",
        r"\bos\.unlink\b",
        r"\bos\.rmdir\b",
        r"\bshutdown\s+",
        r"\btaskkill\s+/[fF]\b",
        r"\bdrop\s+table\b",
        r"\bdrop\s+database\b",
        r"\bdd\s+if=",
        r"\bmkfs\b",
    ]

    def __init__(self):
        self._lock = threading.Lock()
        self._pending_requests: Dict[str, Dict[str, Any]] = {}
        self._listeners: List[Callable[[Dict[str, Any]], None]] = []

    def register_approval_listener(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Register a callback for APPROVAL_REQUIRED events."""
        with self._lock:
            if callback not in self._listeners:
                self._listeners.append(callback)

    def is_trust_mode_active(self) -> bool:
        """Check if Autonomous Trust Mode is enabled in settings."""
        try:
            vault = get_vault()
            return bool(vault.get("autonomous_trust_mode", False))
        except Exception:
            return False

    def inspect_code(self, code: str) -> Tuple[bool, str]:
        """
        Inspect code for risky or destructive patterns.
        Returns: (is_safe: bool, risk_description: str)
        """
        if not code:
            return True, ""

        for pattern in self.DESTRUCTIVE_PATTERNS:
            match = re.search(pattern, code, re.IGNORECASE)
            if match:
                return False, f"Potentially destructive operation detected: '{match.group(0)}'"

        return True, ""

    def request_approval(
        self,
        action_type: str,
        description: str,
        preview: str,
        timeout_sec: int = 15,
    ) -> bool:
        """
        Pauses and requests user approval via HUD ApprovalModal.
        If Autonomous Trust Mode is active, bypasses modal and auto-approves.
        """
        if self.is_trust_mode_active():
            print(f"[SafetyInterceptor] Autonomous Trust Mode active: Auto-approved '{action_type}'")
            return True

        req_id = f"req-{uuid.uuid4().hex[:8]}"
        event_obj = threading.Event()

        payload = {
            "request_id": req_id,
            "action_type": action_type,
            "description": description,
            "preview": preview,
            "timeout_sec": timeout_sec,
        }

        with self._lock:
            self._pending_requests[req_id] = {
                "event": event_obj,
                "approved": False,
                "timestamp": time.time(),
            }
            listeners = list(self._listeners)

        # Notify UI listeners
        for cb in listeners:
            try:
                cb(payload)
            except Exception as e:
                print(f"[SafetyInterceptor] Listener error: {e}")

        print(f"[SafetyInterceptor] Approval required ({req_id}): {description}. Waiting up to {timeout_sec}s...")

        # Wait for user input or timeout
        signaled = event_obj.wait(timeout=float(timeout_sec))

        with self._lock:
            req_data = self._pending_requests.pop(req_id, None)

        if not signaled:
            print(f"[SafetyInterceptor] Request {req_id} timed out. Defaulting to DENIED.")
            return False

        if req_data and req_data.get("approved"):
            print(f"[SafetyInterceptor] Request {req_id} was APPROVED by user.")
            return True
        else:
            print(f"[SafetyInterceptor] Request {req_id} was DENIED by user.")
            return False

    def approve(self, request_id: str) -> bool:
        """Approve a pending request."""
        with self._lock:
            req = self._pending_requests.get(request_id)
            if req:
                req["approved"] = True
                req["event"].set()
                return True
        return False

    def deny(self, request_id: str) -> bool:
        """Deny a pending request."""
        with self._lock:
            req = self._pending_requests.get(request_id)
            if req:
                req["approved"] = False
                req["event"].set()
                return True
        return False


# Global safety interceptor singleton
safety_interceptor = SafetyInterceptor()
