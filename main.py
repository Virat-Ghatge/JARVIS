#!/usr/bin/env python3
"""
J.A.R.V.I.S. - Just A Rather Very Intelligent System
Main Application Entry Point

Default: Launches the PySide6 Desktop GUI Assistant.
Fallback: 'python main.py --cli' runs in headless/terminal-only mode.
"""

import sys
import argparse
from pathlib import Path

# Ensure root directory is in sys.path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from core.engine import JARVISEngine
from core.tts_engine import TTSEngine


def run_gui():
    """Launch the modern PySide6 desktop HUD interface."""
    from PySide6.QtWidgets import QApplication
    from ui.app_window import MainWindow

    # High DPI scaling configuration
    app = QApplication(sys.argv)
    app.setApplicationName("JARVIS Assistant")
    app.setApplicationDisplayName("J.A.R.V.I.S.")

    # Create and display main HUD window
    window = MainWindow()
    window.show()

    sys.exit(app.exec())


def run_cli(silent: bool = False):
    """Run in headless/terminal-only CLI mode."""
    print("=" * 60)
    print("  J.A.R.V.I.S. - Command Line Interface (CLI Mode)")
    print("  Type 'exit' or press Ctrl+C to quit.")
    print("=" * 60)

    tts = TTSEngine(enabled=not silent)
    engine = JARVISEngine(tts_engine=tts)

    engine.speak("All systems online, sir. Standing by for command line input.")

    while engine.running:
        try:
            query = input("\nJARVIS > ").strip()
            if not query:
                continue

            result = engine.execute_command(query, source="cli")
            # In CLI mode, ensure response is printed
            print(f"\nResponse: {result['response']}")

            if result.get("action") == "exit":
                break

        except (KeyboardInterrupt, EOFError):
            print("\nShutting down J.A.R.V.I.S...")
            engine.speak("Goodbye, sir. Going offline.")
            break
        except Exception as e:
            print(f"[CLI Error] {e}")


def main():
    parser = argparse.ArgumentParser(description="JARVIS AI Assistant")
    parser.add_argument(
        "--cli", "-c",
        action="store_true",
        help="Launch in terminal-only CLI mode (headless/no GUI)"
    )
    parser.add_argument(
        "--silent", "-s",
        action="store_true",
        help="Disable voice synthesis (TTS) output"
    )

    args = parser.parse_args()

    if args.cli:
        run_cli(silent=args.silent)
    else:
        run_gui()


if __name__ == "__main__":
    main()
