#!/usr/bin/env python3
"""
Skills Store & Teach Mode Recorder for JARVIS 2.0
Manages custom voice macros, multi-step routines, and allows users to record new
automation workflows on the fly via Teach Mode.
"""

import json
import threading
import uuid
from typing import Any, Dict, List, Optional
from config.settings import SKILLS_FILE


class SkillStore:
    """
    Manages custom skills, macros, and Teach Mode recording.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._is_teaching: bool = False
        self._current_recording: Optional[Dict[str, Any]] = None

    def get_skills(self) -> List[Dict[str, Any]]:
        """Retrieve all skills from config/skills.json."""
        with self._lock:
            if not SKILLS_FILE.exists():
                return []
            try:
                return json.loads(SKILLS_FILE.read_text(encoding="utf-8"))
            except Exception as e:
                print(f"[SkillStore] Error reading {SKILLS_FILE}: {e}")
                return []

    def save_skills(self, skills: List[Dict[str, Any]]) -> bool:
        """Persist skills list to config/skills.json."""
        with self._lock:
            try:
                SKILLS_FILE.write_text(json.dumps(skills, indent=2), encoding="utf-8")
                return True
            except Exception as e:
                print(f"[SkillStore] Error saving {SKILLS_FILE}: {e}")
                return False

    def add_skill(self, skill: Dict[str, Any]) -> bool:
        """Add or update a skill."""
        if not skill.get("id"):
            skill["id"] = f"skill-{uuid.uuid4().hex[:6]}"

        skills = self.get_skills()
        # Check if skill exists to update
        existing = next((i for i, s in enumerate(skills) if s["id"] == skill["id"]), None)
        if existing is not None:
            skills[existing] = skill
        else:
            skills.append(skill)

        return self.save_skills(skills)

    def delete_skill(self, skill_id: str) -> bool:
        """Delete a skill by ID."""
        skills = self.get_skills()
        updated = [s for s in skills if s.get("id") != skill_id]
        if len(updated) != len(skills):
            return self.save_skills(updated)
        return False

    def run_skill(self, skill_id: str, engine) -> Dict[str, Any]:
        """Execute all steps of a skill sequentially using JARVISEngine."""
        skills = self.get_skills()
        skill = next((s for s in skills if s.get("id") == skill_id), None)
        if not skill:
            return {"ok": False, "error": f"Skill '{skill_id}' not found", "results": []}

        steps = skill.get("steps", [])
        results = []
        for step in steps:
            res = engine.process_command(step, source="macro")
            results.append({"step": step, "response": res.get("text", "")})

        summary = f"Routine '{skill.get('name')}' completed ({len(steps)} steps)."
        return {"ok": True, "name": skill.get("name"), "summary": summary, "results": results}

    # ── Teach Mode ────────────────────────────────────────────────────
    def is_teaching(self) -> bool:
        """Check if Teach Mode is currently active."""
        with self._lock:
            return self._is_teaching

    def start_teach_mode(self, name: str, trigger_phrases: List[str]) -> Dict[str, Any]:
        """Initiate a new Teach Mode recording session."""
        with self._lock:
            self._is_teaching = True
            self._current_recording = {
                "id": f"skill-{uuid.uuid4().hex[:6]}",
                "name": name.strip(),
                "trigger_phrases": [t.strip().lower() for t in trigger_phrases if t.strip()],
                "steps": [],
            }
            return dict(self._current_recording)

    def record_step(self, command: str) -> bool:
        """Append a command step to the active Teach Mode session."""
        with self._lock:
            if not self._is_teaching or not self._current_recording:
                return False
            self._current_recording["steps"].append(command.strip())
            return True

    def stop_teach_mode(self, save: bool = True) -> Optional[Dict[str, Any]]:
        """End Teach Mode session and optionally save to config/skills.json."""
        with self._lock:
            if not self._is_teaching or not self._current_recording:
                self._is_teaching = False
                self._current_recording = None
                return None

            recorded = self._current_recording
            self._is_teaching = False
            self._current_recording = None

        if save and recorded.get("steps"):
            self.add_skill(recorded)
            print(f"[SkillStore] Saved new skill via Teach Mode: '{recorded['name']}' ({len(recorded['steps'])} steps)")

        return recorded


# Global skill store singleton
skill_store = SkillStore()
