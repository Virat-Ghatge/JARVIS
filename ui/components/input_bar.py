#!/usr/bin/env python3
"""
Input Bar Component for JARVIS GUI
Provides text input field with command history recall (Up/Down arrow keys) and submit button.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QFrame,
)


class CommandLineEdit(QLineEdit):
    """Custom QLineEdit implementing command history recall with Up/Down arrow keys."""

    up_pressed = Signal()
    down_pressed = Signal()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Up:
            self.up_pressed.emit()
            event.accept()
        elif event.key() == Qt.Key_Down:
            self.down_pressed.emit()
            event.accept()
        else:
            super().keyPressEvent(event)


class InputBar(QFrame):
    """Unified Input Bar widget."""

    command_submitted = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("InputContainer")

        self.history: list[str] = []
        self.history_index: int = -1

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(10)

        # Input field
        self.input_field = CommandLineEdit()
        self.input_field.setObjectName("CommandInput")
        self.input_field.setPlaceholderText("Type a command or ask a question (e.g., 'what time is it', 'schedule meeting', 'system status')...")
        self.input_field.returnPressed.connect(self._handle_submit)
        self.input_field.up_pressed.connect(self._recall_previous)
        self.input_field.down_pressed.connect(self._recall_next)
        layout.addWidget(self.input_field, 1)

        # Submit button
        self.btn_submit = QPushButton("Execute")
        self.btn_submit.setObjectName("SubmitBtn")
        self.btn_submit.clicked.connect(self._handle_submit)
        layout.addWidget(self.btn_submit)

    def _handle_submit(self):
        text = self.input_field.text().strip()
        if not text:
            return

        # Store in history
        if not self.history or self.history[-1] != text:
            self.history.append(text)
        self.history_index = len(self.history)

        # Clear field and emit signal
        self.input_field.clear()
        self.command_submitted.emit(text)

    def _recall_previous(self):
        if not self.history:
            return
        if self.history_index > 0:
            self.history_index -= 1
            self.input_field.setText(self.history[self.history_index])

    def _recall_next(self):
        if not self.history:
            return
        if self.history_index < len(self.history) - 1:
            self.history_index += 1
            self.input_field.setText(self.history[self.history_index])
        else:
            self.history_index = len(self.history)
            self.input_field.clear()
