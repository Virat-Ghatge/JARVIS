#!/usr/bin/env python3
"""
Chat Feed Component for JARVIS Desktop GUI
Renders conversation bubbles for user queries and assistant responses.
"""

from datetime import datetime
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QFrame,
    QScrollArea,
    QSizePolicy,
)


class ChatMessage(QFrame):
    """Individual conversation bubble."""

    def __init__(self, text: str, sender: str = "jarvis", source: str = "text", timestamp: str = None, parent=None):
        super().__init__(parent)
        self.sender = sender.lower()
        self.timestamp = timestamp or datetime.now().strftime("%I:%M %p")

        # Object name for styling
        if self.sender == "user":
            self.setObjectName("UserBubble")
        else:
            self.setObjectName("JarvisBubble")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        # Meta header
        meta_layout = QHBoxLayout()
        meta_layout.setContentsMargins(0, 0, 0, 0)

        sender_label = QLabel("YOU" if self.sender == "user" else "J.A.R.V.I.S.")
        sender_label.setObjectName("UserMeta" if self.sender == "user" else "JarvisMeta")
        meta_layout.addWidget(sender_label)

        if source:
            source_tag = QLabel(f"[{source.upper()}]")
            source_tag.setObjectName("UserMeta" if self.sender == "user" else "JarvisMeta")
            meta_layout.addWidget(source_tag)

        meta_layout.addStretch()

        time_label = QLabel(self.timestamp)
        time_label.setObjectName("UserMeta" if self.sender == "user" else "JarvisMeta")
        meta_layout.addWidget(time_label)

        layout.addLayout(meta_layout)

        # Content text
        text_label = QLabel(text)
        text_label.setObjectName("UserText" if self.sender == "user" else "JarvisText")
        text_label.setWordWrap(True)
        text_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(text_label)


class ChatFeed(QScrollArea):
    """Scrollable feed of chat messages with auto-scroll."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ChatScrollArea")
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        # Container widget inside scroll area
        self.container = QWidget()
        self.container.setObjectName("ChatContent")
        self.layout = QVBoxLayout(self.container)
        self.layout.setContentsMargins(16, 16, 16, 16)
        self.layout.setSpacing(12)
        self.layout.addStretch()

        self.setWidget(self.container)

    def add_message(self, text: str, sender: str = "jarvis", source: str = "text"):
        """Add a new message bubble and scroll down."""
        msg_widget = ChatMessage(text=text, sender=sender, source=source)

        # Wrap in alignment row
        row_layout = QHBoxLayout()
        row_layout.setContentsMargins(0, 0, 0, 0)

        if sender.lower() == "user":
            row_layout.addStretch(1)
            row_layout.addWidget(msg_widget, 4)
        else:
            row_layout.addWidget(msg_widget, 4)
            row_layout.addStretch(1)

        # Insert before stretch item at the end
        self.layout.insertLayout(self.layout.count() - 1, row_layout)

        # Auto-scroll to bottom
        QTimer.singleShot(50, self.scroll_to_bottom)

    def scroll_to_bottom(self):
        scrollbar = self.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def clear_feed(self):
        """Remove all messages."""
        while self.layout.count() > 1:
            item = self.layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                while item.layout().count():
                    child = item.layout().takeAt(0)
                    if child.widget():
                        child.widget().deleteLater()
