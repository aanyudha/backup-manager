"""Shared schedule form controls for backup profile pages."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QSpinBox,
    QWidget,
)

from app.models.profile import Profile

WEEKDAY_OPTIONS = [
    ("Mon", 0),
    ("Tue", 1),
    ("Wed", 2),
    ("Thu", 3),
    ("Fri", 4),
    ("Sat", 5),
    ("Sun", 6),
]


class ScheduleFieldsSection:
    """Bundle schedule controls so multiple pages stay consistent."""

    def __init__(self) -> None:
        self.schedule_enabled_checkbox = QCheckBox("Enable Schedule")
        self.schedule_type_combo = QComboBox()
        self.schedule_type_combo.addItems(["manual", "daily", "weekly", "monthly"])
        self.schedule_time_edit = QLineEdit()
        self.schedule_time_edit.setPlaceholderText("HH:MM")
        self.run_if_missed_checkbox = QCheckBox("Run if missed")
        self.run_if_missed_checkbox.setChecked(True)
        self.day_of_month_spin = QSpinBox()
        self.day_of_month_spin.setRange(1, 31)
        self.day_of_month_spin.setValue(1)

        self.days_widget = QWidget()
        self.days_layout = QHBoxLayout(self.days_widget)
        self.days_layout.setContentsMargins(0, 0, 0, 0)
        self.days_layout.setSpacing(6)
        self.day_checkboxes: dict[int, QCheckBox] = {}
        for label, value in WEEKDAY_OPTIONS:
            checkbox = QCheckBox(label)
            self.day_checkboxes[value] = checkbox
            self.days_layout.addWidget(checkbox)
        self.days_layout.addStretch(1)

        self.schedule_type_combo.currentTextChanged.connect(self._refresh_state)
        self._refresh_state()

    def add_to_form(self, form: QFormLayout) -> None:
        """Append the scheduler rows to an existing form layout."""
        form.addRow("", self.schedule_enabled_checkbox)
        form.addRow("Schedule Type", self.schedule_type_combo)
        form.addRow("Time", self.schedule_time_edit)
        form.addRow("Days of Week", self.days_widget)
        form.addRow("Day of Month", self.day_of_month_spin)
        form.addRow("", self.run_if_missed_checkbox)

    def clear(self) -> None:
        """Reset the controls to defaults for a new profile."""
        self.schedule_enabled_checkbox.setChecked(False)
        self.schedule_type_combo.setCurrentText("manual")
        self.schedule_time_edit.clear()
        for checkbox in self.day_checkboxes.values():
            checkbox.setChecked(False)
        self.day_of_month_spin.setValue(1)
        self.run_if_missed_checkbox.setChecked(True)
        self._refresh_state()

    def load_profile(self, profile: Profile) -> None:
        """Populate the controls from a persisted profile."""
        self.schedule_enabled_checkbox.setChecked(profile.schedule_enabled)
        self.schedule_type_combo.setCurrentText(profile.schedule_type)
        self.schedule_time_edit.setText(profile.schedule_time or "")
        for day, checkbox in self.day_checkboxes.items():
            checkbox.setChecked(day in profile.schedule_days_of_week)
        self.day_of_month_spin.setValue(profile.schedule_day_of_month or 1)
        self.run_if_missed_checkbox.setChecked(profile.run_if_missed)
        self._refresh_state()

    def apply_to_payload(self, payload: dict[str, object]) -> None:
        """Copy the current UI values into a profile payload."""
        schedule_type = self.schedule_type_combo.currentText()
        payload.update(
            schedule_enabled=self.schedule_enabled_checkbox.isChecked(),
            schedule_type=schedule_type,
            schedule_time=self.schedule_time_edit.text() or None,
            schedule_days_of_week=[
                day
                for day, checkbox in self.day_checkboxes.items()
                if checkbox.isChecked()
            ]
            if schedule_type == "weekly"
            else [],
            schedule_day_of_month=self.day_of_month_spin.value() if schedule_type == "monthly" else None,
            run_if_missed=self.run_if_missed_checkbox.isChecked(),
        )

    def _refresh_state(self) -> None:
        schedule_type = self.schedule_type_combo.currentText()
        supports_time = schedule_type in {"daily", "weekly", "monthly"}
        is_weekly = schedule_type == "weekly"
        is_monthly = schedule_type == "monthly"

        self.schedule_time_edit.setEnabled(supports_time)
        self.days_widget.setEnabled(is_weekly)
        self.day_of_month_spin.setEnabled(is_monthly)
        self.run_if_missed_checkbox.setEnabled(schedule_type != "manual")
