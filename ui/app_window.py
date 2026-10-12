#!/usr/bin/env python3
"""
MainWindow layout & event routing for JARVIS Desktop App (PySide6)
Implements dark HUD theme, unified text/voice dispatch, dual audio controls,
and asynchronous task execution via QThreadPool.
"""

import os
import webbrowser
from datetime import datetime
from typing import Optional

from PySide6.QtCore import Qt, QObject, Signal, QRunnable, QThreadPool, QTimer
from PySide6.QtGui import QIcon, QFont
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QSplitter,
    QMessageBox,
)

from config.settings import (
    STYLES_FILE,
    MEETING_DASHBOARD_PORT,
    MEETING_DASHBOARD_HOST,
    ASSETS_DIR,
)
from core.engine import JARVISEngine
from core.voice_listener import VoiceListener
from core.tts_engine import TTSEngine
from ui.components.chat_feed import ChatFeed
from ui.components.stat_cards import StatCardsDock
from ui.components.input_bar import InputBar


class CommandWorkerSignals(QObject):
    """Signals for background command worker."""
    finished = Signal(dict)


class CommandTask(QRunnable):
    """Executes InputGateway commands in QThreadPool to keep GUI fluid."""

    def __init__(self, engine: JARVISEngine, query: str, source: str = "text"):
        super().__init__()
        self.engine = engine
        self.query = query
        self.source = source
        self.signals = CommandWorkerSignals()

    def run(self):
        try:
            result = self.engine.execute_command(self.query, source=self.source)
        except Exception as e:
            result = {
                "status": "error",
                "query": self.query,
                "response": f"Execution error: {e}",
                "source": self.source,
                "action": "error",
            }
        self.signals.finished.emit(result)


class BridgeSignals(QObject):
    """Cross-thread signal bridge for voice listener and meeting automation."""
    voice_command_received = Signal(str)
    mic_state_changed = Signal(bool, str)
    meeting_state_changed = Signal(str, str)


class MainWindow(QMainWindow):
    """
    Main PySide6 Window for JARVIS.
    """

    def __init__(self, engine: Optional[JARVISEngine] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("J.A.R.V.I.S. — Desktop AI Assistant")
        self.resize(1100, 720)
        self.setMinimumSize(850, 550)

        icon_path = ASSETS_DIR / "jarvis.png"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        # Initialize or link core engine and components
        self.tts_engine = TTSEngine(enabled=True)
        self.engine = engine or JARVISEngine(tts_engine=self.tts_engine)

        # Thread pool for non-blocking asynchronous execution
        self.thread_pool = QThreadPool.globalInstance()

        # Cross-thread Qt signal bridge
        self.bridge = BridgeSignals()
        self.bridge.voice_command_received.connect(self._on_voice_command)
        self.bridge.mic_state_changed.connect(self._on_mic_state_changed)
        self.bridge.meeting_state_changed.connect(self._on_meeting_event)

        # Initialize voice listener worker
        self.voice_listener = VoiceListener(
            on_command=lambda cmd: self.bridge.voice_command_received.emit(cmd),
            on_status_change=lambda active, msg: self.bridge.mic_state_changed.emit(active, msg),
            on_meeting_alert=lambda ev, title: self.bridge.meeting_state_changed.emit(ev, title),
        )

        # Hook meeting automation callbacks for meeting-aware audio interlocking
        if hasattr(self.engine, 'meeting_handler') and self.engine.meeting_handler:
            bot = self.engine.meeting_handler.bot
            if bot:
                bot.on_meeting_joined = lambda url: self.voice_listener.handle_meeting_joined("Google Meet / Teams")
                bot.on_meeting_left = lambda url: self.voice_listener.handle_meeting_left("Google Meet / Teams")

        # Apply QSS Styling
        self._load_stylesheet()

        # Build UI layout
        self._init_ui()

        # Welcome message in conversation feed
        self.chat_feed.add_message(
            "Good day, sir. Systems are online and standing by for your command.",
            sender="jarvis",
            source="system"
        )

    def _load_stylesheet(self):
        if STYLES_FILE.exists():
            try:
                with open(STYLES_FILE, "r", encoding="utf-8") as f:
                    self.setStyleSheet(f.read())
            except Exception as e:
                print(f"[UI] Error loading stylesheet: {e}")

    # ── UI Construction ───────────────────────────────────────────────
    def _init_ui(self):
        central_widget = QWidget()
        central_widget.setObjectName("CentralWidget")
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Initialize core components
        self.chat_feed = ChatFeed()
        self.input_bar = InputBar()
        self.input_bar.command_submitted.connect(self._on_text_command)

        # 1. Header Bar
        header = self._build_header_bar()
        main_layout.addWidget(header)

        # 2. Audio & Quick Control Toolbar
        toolbar = self._build_toolbar()
        main_layout.addWidget(toolbar)

        # 3. Middle Body Splitter (Chat Feed + Telemetry Dock)
        body_splitter = QSplitter(Qt.Horizontal)
        body_splitter.setHandleWidth(1)

        # Left Column: Chat Feed + Unified Input Bar
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        left_layout.addWidget(self.chat_feed, 1)
        left_layout.addWidget(self.input_bar)
        body_splitter.addWidget(left_panel)

        # Right Column: System Telemetry & Meeting Dock
        scheduler = self.engine.meeting_handler.scheduler if hasattr(self.engine, 'meeting_handler') else None
        self.telemetry_dock = StatCardsDock(scheduler=scheduler)
        self.telemetry_dock.open_meeting_requested.connect(self._join_meeting_url)
        body_splitter.addWidget(self.telemetry_dock)

        # Set splitter proportions (e.g., 75% left, 25% right)
        body_splitter.setStretchFactor(0, 4)
        body_splitter.setStretchFactor(1, 1)

        main_layout.addWidget(body_splitter, 1)

    def _build_header_bar(self) -> QFrame:
        header = QFrame()
        header.setObjectName("HeaderBar")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(20, 10, 20, 10)
        layout.setSpacing(16)

        # Title block
        title_block = QVBoxLayout()
        title_block.setSpacing(2)
        lbl_title = QLabel("J.A.R.V.I.S.")
        lbl_title.setObjectName("JarvisTitle")
        lbl_sub = QLabel("INTELLIGENT SYSTEM ARCHITECTURE")
        lbl_sub.setObjectName("JarvisSubtitle")
        title_block.addWidget(lbl_title)
        title_block.addWidget(lbl_sub)
        layout.addLayout(title_block)

        layout.addStretch()

        # Meeting Live Indicator Badge (hidden by default)
        self.badge_meeting = QLabel("IN MEETING: ACTIVE")
        self.badge_meeting.setObjectName("MeetingBadge")
        self.badge_meeting.setVisible(False)
        layout.addWidget(self.badge_meeting)

        # Online/Offline Badge
        is_online = self.engine.is_online()
        self.badge_status = QLabel("ONLINE" if is_online else "OFFLINE")
        self.badge_status.setObjectName("StatusBadgeOnline" if is_online else "StatusBadgeOffline")
        layout.addWidget(self.badge_status)

        # Meeting Dashboard Button
        btn_dashboard = QPushButton("Meeting Dashboard")
        btn_dashboard.setObjectName("DashboardBtn")
        btn_dashboard.setToolTip("Open local web schedule dashboard at :5050")
        btn_dashboard.clicked.connect(self._open_meeting_dashboard)
        layout.addWidget(btn_dashboard)

        return header

    def _build_toolbar(self) -> QFrame:
        bar = QFrame()
        bar.setStyleSheet("background-color: #0d1322; border-bottom: 1px solid #1e293b; padding: 6px 16px;")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 6, 16, 6)
        layout.setSpacing(12)

        # Mic Toggle Button (defaults to off/muted for user comfort, click to listen)
        self.btn_mic = QPushButton("MIC: MUTED")
        self.btn_mic.setObjectName("MicBtnMuted")
        self.btn_mic.setToolTip("Toggle microphone voice recognition stream on/off")
        self.btn_mic.clicked.connect(self._toggle_mic)
        layout.addWidget(self.btn_mic)

        # TTS Output Toggle Button (defaults to active)
        self.btn_tts = QPushButton("VOICE: ACTIVE")
        self.btn_tts.setObjectName("TTSBtnActive")
        self.btn_tts.setToolTip("Toggle JARVIS spoken voice responses on/off")
        self.btn_tts.clicked.connect(self._toggle_tts)
        layout.addWidget(self.btn_tts)

        # Active state hint
        self.lbl_mic_status = QLabel("Microphone muted. Click MIC or speak when active.")
        self.lbl_mic_status.setStyleSheet("color: #64748b; font-size: 11px;")
        layout.addWidget(self.lbl_mic_status)

        layout.addStretch()

        # Clear Chat Button
        btn_clear = QPushButton("Clear Chat")
        btn_clear.setStyleSheet("background-color: transparent; border: 1px solid #334155; color: #94a3b8; padding: 4px 10px; font-size: 11px;")
        btn_clear.clicked.connect(self.chat_feed.clear_feed)
        layout.addWidget(btn_clear)

        return bar

    # ── Audio Toggle Controls ─────────────────────────────────────────
    def _toggle_mic(self):
        new_state = self.voice_listener.toggle()
        self._update_mic_ui(new_state)

    def _update_mic_ui(self, is_active: bool, custom_msg: str = ""):
        if is_active:
            self.btn_mic.setText("MIC: LISTENING")
            self.btn_mic.setObjectName("MicBtnActive")
            self.lbl_mic_status.setText(custom_msg or "Microphone is listening for commands...")
            self.lbl_mic_status.setStyleSheet("color: #38bdf8; font-size: 11px;")
        else:
            self.btn_mic.setText("MIC: MUTED")
            self.btn_mic.setObjectName("MicBtnMuted")
            self.lbl_mic_status.setText(custom_msg or "Microphone muted. Voice recognition paused.")
            self.lbl_mic_status.setStyleSheet("color: #64748b; font-size: 11px;")

        # Re-apply stylesheet state to refresh button colors dynamically
        self.btn_mic.style().unpolish(self.btn_mic)
        self.btn_mic.style().polish(self.btn_mic)

    def _toggle_tts(self):
        new_state = self.tts_engine.toggle()
        if new_state:
            self.btn_tts.setText("VOICE: ACTIVE")
            self.btn_tts.setObjectName("TTSBtnActive")
        else:
            self.btn_tts.setText("VOICE: MUTED")
            self.btn_tts.setObjectName("TTSBtnMuted")

        self.btn_tts.style().unpolish(self.btn_tts)
        self.btn_tts.style().polish(self.btn_tts)

    # ── Command Ingestion & Execution Routing ─────────────────────────
    def _on_text_command(self, query: str):
        """Handle command submitted via GUI text input."""
        if not query.strip():
            return

        # Show user message bubble immediately
        self.chat_feed.add_message(query, sender="user", source="text")

        # Execute asynchronously in thread pool
        task = CommandTask(self.engine, query, source="text")
        task.signals.finished.connect(self._on_command_finished)
        self.thread_pool.start(task)

    def _on_voice_command(self, query: str):
        """Handle command received from VoiceListener thread."""
        if not query.strip():
            return

        # Show user message bubble from voice
        self.chat_feed.add_message(query, sender="user", source="voice")

        # Execute asynchronously in thread pool
        task = CommandTask(self.engine, query, source="voice")
        task.signals.finished.connect(self._on_command_finished)
        self.thread_pool.start(task)

    def _on_command_finished(self, result: dict):
        """Main thread callback when command completes."""
        response = result.get("response", "Command executed, sir.")
        source = result.get("source", "text")
        action = result.get("action", "")

        # Append assistant response bubble
        self.chat_feed.add_message(response, sender="jarvis", source=source)

        # Refresh telemetry dock
        self.telemetry_dock.refresh_stats()

        # Handle app shutdown command if requested
        if action == "exit":
            QTimer.singleShot(1500, self.close)

    # ── Meeting Interlock & Event Handling ────────────────────────────
    def _on_mic_state_changed(self, active: bool, msg: str):
        self._update_mic_ui(active, custom_msg=msg)

    def _on_meeting_event(self, event: str, title: str):
        if event == "joined":
            self.badge_meeting.setText(f"IN MEETING: {title[:20]}")
            self.badge_meeting.setVisible(True)
            self.telemetry_dock.refresh_meeting_banner()
        elif event == "left":
            self.badge_meeting.setVisible(False)
            self.telemetry_dock.refresh_meeting_banner()

    def _open_meeting_dashboard(self):
        url = f"http://{MEETING_DASHBOARD_HOST}:{MEETING_DASHBOARD_PORT}"
        webbrowser.open(url)

    def _join_meeting_url(self, url: str):
        """Triggered from telemetry dock join button."""
        self._on_text_command(f"join meeting {url}")

    def closeEvent(self, event):
        """Clean shutdown of background services."""
        if hasattr(self, 'voice_listener'):
            self.voice_listener.stop()
        if hasattr(self, 'tts_engine'):
            self.tts_engine.stop()
        event.accept()
