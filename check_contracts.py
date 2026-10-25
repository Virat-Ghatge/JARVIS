import ast
import sys
import importlib
import traceback
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SCAN_DIRS = ["config", "core", "audio", "agent_os", "integrations", "automation", "tests"]

print("=== Phase 1: AST Symbol Verification Across All Project Files ===")
missing_symbols = []

for folder in SCAN_DIRS:
    folder_path = BASE_DIR / folder
    if not folder_path.exists():
        continue
    for py_file in folder_path.rglob("*.py"):
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8", errors="ignore"), filename=str(py_file))
        except Exception as e:
            print(f"[SYNTAX ERROR] {py_file}: {e}")
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                top_pkg = node.module.split(".")[0]
                if top_pkg in SCAN_DIRS:
                    try:
                        mod = importlib.import_module(node.module)
                        for alias in node.names:
                            if alias.name != "*" and not hasattr(mod, alias.name):
                                missing_symbols.append((str(py_file.relative_to(BASE_DIR)), node.module, alias.name))
                    except Exception as e:
                        missing_symbols.append((str(py_file.relative_to(BASE_DIR)), node.module, f"<ModuleImportError: {e}>"))

if missing_symbols:
    for src, mod_name, sym in missing_symbols:
        print(f"[MISSING SYMBOL] in {src}: from {mod_name} import {sym}")
else:
    print("[OK] All internal 'from X import Y' symbols verified across the entire repository!")

print("\n=== Phase 2: Subsystem Runtime Import Check ===")
MODULES = [
    "config.settings",
    "core.adapters.base",
    "core.llm_router",
    "core.context_manager",
    "core.engine",
    "audio.tts_engine",
    "audio.voice_listener",
    "agent_os.safety_interceptor",
    "agent_os.code_executor",
    "agent_os.ui_distiller",
    "agent_os.som_vision",
    "agent_os.os_actuator",
    "agent_os.state_machine",
    "integrations.mcp_client",
    "integrations.skill_store",
    "integrations.workspace_rag",
    "automation.meeting_bot",
    "automation.meeting_scheduler",
    "automation.meeting_handler",
    "automation.web_agent",
    "automation.server",
]

failed = 0
for mod in MODULES:
    try:
        importlib.import_module(mod)
        print(f"[OK] {mod}")
    except Exception as exc:
        failed += 1
        print(f"[FAIL] {mod}: {exc}")
        traceback.print_exc()

sys.exit(1 if (failed or missing_symbols) else 0)
