#!/usr/bin/env python3
"""
System Telemetry Dock & Stat Cards Component for JARVIS GUI
Displays live CPU, battery, RAM, and upcoming meeting notifications.
"""

from datetime import datetime
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QFrame,
    QPushButton,
)

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False


class StatCard(QFrame):
    """Reusable mini telemetry card."""

    def __init__(self, label: str, initial_value: str = "--", sub_text: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("StatCard")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        self.lbl_title = QLabel(label)
        self.lbl_title.setObjectName("StatLabel")
        layout.addWidget(self.lbl_title)

        self.lbl_value = QLabel(initial_value)
        self.lbl_value.setObjectName("StatValue")
        layout.addWidget(self.lbl_value)

        self.lbl_sub = QLabel(sub_text)
        self.lbl_sub.setObjectName("StatSub")
        layout.addWidget(self.lbl_sub)

    def set_data(self, value: str, sub_text: str = ""):
        self.lbl_value.setText(value)
        if sub_text:
            self.lbl_sub.setText(sub_text)


class StatCardsDock(QFrame):
    """Right-side dock displaying live telemetry and meeting schedule."""

    open_meeting_requested = Signal(str)

    def __init__(self, scheduler=None, parent=None):
        super().__init__(parent)
        self.setObjectName("TelemetryDock")
        self.setFixedWidth(260)
        self.scheduler = scheduler

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 16, 12, 16)
        layout.setSpacing(12)

        header = QLabel("SYSTEM TELEMETRY")
        header.setObjectName("StatLabel")
        header.setAlignment(Qt.AlignCenter)
        layout.addWidget(header)

        # CPU Card
        self.cpu_card = StatCard("CPU Load", "0%", "Monitoring active")
        layout.addWidget(self.cpu_card)

        # Memory Card
        self.ram_card = StatCard("Memory (RAM)", "0%", "Physical memory")
        layout.addWidget(self.ram_card)

        # Battery Card
        self.battery_card = StatCard("Battery", "--", "Checking status...")
        layout.addWidget(self.battery_card)

        # Meeting Card
        self.meeting_card = QFrame()
        self.meeting_card.setObjectName("MeetingCard")
        m_layout = QVBoxLayout(self.meeting_card)
        m_layout.setContentsMargins(12, 10, 12, 10)
        m_layout.setSpacing(6)

        m_header = QLabel("NEXT SCHEDULED MEETING")
        m_header.setObjectName("StatLabel")
        m_layout.addWidget(m_header)

        self.meeting_title = QLabel("No meetings scheduled")
        self.meeting_title.setObjectName("MeetingCardTitle")
        self.meeting_title.setWordWrap(True)
        m_layout.addWidget(self.meeting_title)

        self.meeting_time = QLabel("Agenda clear")
        self.meeting_time.setObjectName("MeetingCardTime")
        m_layout.addWidget(self.meeting_time)

        self.btn_join_meeting = QPushButton("Join Now")
        self.btn_join_meeting.setObjectName("DashboardBtn")
        self.btn_join_meeting.setVisible(False)
        self.btn_join_meeting.clicked.connect(self._on_join_clicked)
        m_layout.addWidget(self.btn_join_meeting)

        layout.addWidget(self.meeting_card)
        layout.addStretch()

        # Telemetry update timer
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_stats)
        self.timer.start(3000)

        # First refresh
        self.refresh_stats()

    def refresh_stats(self):
        """Update hardware stats and meeting banner."""
        if PSUTIL_AVAILABLE:
            try:
                cpu = psutil.cpu_percent()
                self.cpu_card.set_data(f"{cpu:.1f}%", "Load normal" if cpu < 75 else "High usage")

                ram = psutil.virtual_memory().percent
                self.ram_card.set_data(f"{ram:.1f}%", f"{psutil.virtual_memory().used // (1024**3)} GB in use")

                if hasattr(psutil, 'sensors_battery'):
                    bat = psutil.sensors_battery()
                    if bat:
                        plugged = "Plugged In" if bat.power_plugged else "On Battery"
                        self.battery_card.set_data(f"{bat.percent}%", plugged)
                    else:
                        self.battery_card.set_data("AC Power", "Desktop mode")
            except Exception:
                pass

        # Update meeting banner
        self.refresh_meeting_banner()

    def refresh_meeting_banner(self):
        if not self.scheduler:
            return
        try:
            today_meetings = self.scheduler.get_today()
            pending = [m for m in today_meetings if m.get("status") == "pending"]
            active = [m for m in today_meetings if m.get("status") == "active"]

            if active:
                m = active[0]
                self.meeting_title.setText(f"[LIVE] {m.get('title')}")
                self.meeting_time.setText("Call in progress")
                self.btn_join_meeting.setVisible(False)
            elif pending:
                m = sorted(pending, key=lambda x: x.get("start_time", ""))[0]
                self.meeting_title.setText(m.get("title", "Meeting"))
                try:
                    t_str = datetime.fromisoformat(m["start_time"]).strftime("%I:%M %p")
                except Exception:
                    t_str = m.get("start_time", "")
                self.meeting_time.setText(f"Scheduled for {t_str}")
                self._current_url = m.get("meeting_url", "")
                self.btn_join_meeting.setVisible(bool(self._current_url))
            else:
                self.meeting_title.setText("No pending meetings")
                self.meeting_time.setText("All set for today")
                self.btn_join_meeting.setVisible(False)
        except Exception:
            pass

    def _on_join_clicked(self):
        if hasattr(self, '_current_url') and self._current_url:
            self.open_meeting_requested.emit(self._current_url)
