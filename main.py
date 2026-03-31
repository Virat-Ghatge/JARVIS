#!/usr/bin/env python3
"""
J.A.R.V.I.S. - Just A Rather Very Intelligent System
A voice assistant inspired by Tony Stark's JARVIS

Main entry point - Run this file to start JARVIS
"""

from core import JARVIS


def main():
    """Entry point"""
    print("=" * 50)
    print("J.A.R.V.I.S. - Just A Rather Very Intelligent System")
    print("=" * 50)
    print("\nInitializing...")

    try:
        jarvis = JARVIS()
        jarvis.run()
    except KeyboardInterrupt:
        print("\nShutting down...")
    except Exception as e:
        print(f"Error: {e}")
        print("\nMake sure you have installed the required packages:")
        print("pip install SpeechRecognition pyttsx3 pyaudio")


if __name__ == "__main__":
    main()
