"""Configuration tab: data directory, buckets, targets, allocations."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from investment_tracker.config import AccountAllocation, AppConfig, Bucket, copy_config
from investment_tracker.ui.styles import MUTED, NEGATIVE


def _spin(value: float | None, maximum: float = 100.0) -> QDoubleSpinBox:
    box = QDoubleSpinBox()
    box.setRange(0.0, maximum)
    box.setDecimals(1)
    box.setSingleStep(0.5)
    box.setSpecialValueText("—")
    # 0 is a legitimate target (e.g. 0% yield). Use -0.1 internally as empty? 
    # Instead: allow 0 and provide a clear checkbox. Simpler: -1 means unset via special value.
    box.setMinimum(-0.1)
    box.setValue(-0.1 if value is None else float(value))
    box.setSuffix(" %")
    box.setMaximumWidth(120)
    return box


def _spin_value(box: QDoubleSpinBox) -> float | None:
    value = box.value()
    if value < 0:
        return None
    return float(value)


class ConfigTab(QWidget):
    applied = Signal(object)  # AppConfig

    def __init__(self, parent=None):
        super().__init__(parent)
        self._config = AppConfig()
        self._account_names: list[str] = []

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        scroll.setWidget(inner)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        layout = QVBoxLayout(inner)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        files = QGroupBox("Data files")
        files_form = QFormLayout(files)
        path_row = QHBoxLayout()
        self.dir_edit = QLineEdit()
        browse = QPushButton("Browse…")
        browse.setProperty("secondary", True)
        browse.clicked.connect(self._browse)
        path_row.addWidget(self.dir_edit, stretch=1)
        path_row.addWidget(browse)
        files_form.addRow("CSV directory", path_row)
        hint = QLabel(
            "Each file must be named ACCOUNT CURRENCY.csv — for example "
            "'US Brokerage USD.csv'. Currency is the three-letter code."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {MUTED};")
        files_form.addRow(hint)
        self.base_currency = QLineEdit("USD")
        self.base_currency.setMaxLength(3)
        self.base_currency.setMaximumWidth(80)
        files_form.addRow("Reporting currency", self.base_currency)
        layout.addWidget(files)

        buckets_box = QGroupBox("Buckets and targets")
        buckets_layout = QHBoxLayout(buckets_box)

        left = QVBoxLayout()
        self.bucket_list = QListWidget()
        self.bucket_list.setMaximumWidth(220)
        self.bucket_list.currentRowChanged.connect(self._load_bucket_into_form)
        left.addWidget(self.bucket_list)
        list_buttons = QHBoxLayout()
        add_b = QPushButton("Add")
        add_b.clicked.connect(self._add_bucket)
        rename_b = QPushButton("Rename")
        rename_b.setProperty("secondary", True)
        rename_b.clicked.connect(self._rename_bucket)
        del_b = QPushButton("Remove")
        del_b.setProperty("danger", True)
        del_b.clicked.connect(self._remove_bucket)
        list_buttons.addWidget(add_b)
        list_buttons.addWidget(rename_b)
        list_buttons.addWidget(del_b)
        left.addLayout(list_buttons)
        buckets_layout.addLayout(left)

        right = QVBoxLayout()
        form = QFormLayout()
        self.target_alloc = _spin(None)
        self.target_return = _spin(None, maximum=100.0)
        self.target_yield = _spin(None, maximum=100.0)
        self.target_vol = _spin(None, maximum=100.0)
        self.target_dd = _spin(None, maximum=100.0)
        form.addRow("Target size of portfolio", self.target_alloc)
        form.addRow("Target return (ex-distributions)", self.target_return)
        form.addRow("Target income yield", self.target_yield)
        form.addRow("Target volatility", self.target_vol)
        form.addRow("Target maximum drawdown", self.target_dd)
        note = QLabel("Leave a target at — if you do not want to set one.")
        note.setStyleSheet(f"color: {MUTED};")
        form.addRow(note)
        right.addLayout(form)

        right.addWidget(QLabel("Accounts in this bucket (target % of the bucket)"))
        self.account_table = QTableWidget(0, 3)
        self.account_table.setHorizontalHeaderLabels(["Include", "Account", "Target % of bucket"])
        self.account_table.verticalHeader().setVisible(False)
        self.account_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.account_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.account_table.itemChanged.connect(self._on_account_item_changed)
        right.addWidget(self.account_table)
        self.alloc_warning = QLabel("")
        self.alloc_warning.setStyleSheet(f"color: {NEGATIVE};")
        right.addWidget(self.alloc_warning)
        buckets_layout.addLayout(right, stretch=1)
        layout.addWidget(buckets_box)

        actions = QHBoxLayout()
        actions.addStretch()
        save_btn = QPushButton("Save configuration")
        save_btn.clicked.connect(self._apply)
        actions.addWidget(save_btn)
        layout.addLayout(actions)
        layout.addStretch()

        for widget in (
            self.target_alloc,
            self.target_return,
            self.target_yield,
            self.target_vol,
            self.target_dd,
        ):
            widget.valueChanged.connect(self._write_form_to_bucket)

    def set_accounts(self, names: list[str]) -> None:
        self._account_names = sorted(names)
        self._rebuild_account_table()
        self._load_bucket_into_form(self.bucket_list.currentRow())

    def load_config(self, config: AppConfig) -> None:
        self._config = copy_config(config)
        self.dir_edit.setText(self._config.data_directory)
        self.base_currency.setText(self._config.base_currency)
        self._refresh_bucket_list()
        if self.bucket_list.count():
            self.bucket_list.setCurrentRow(0)
        else:
            self._rebuild_account_table()

    def _refresh_bucket_list(self) -> None:
        current = self.bucket_list.currentItem()
        current_name = current.text() if current else None
        self.bucket_list.blockSignals(True)
        self.bucket_list.clear()
        for bucket in self._config.buckets:
            self.bucket_list.addItem(QListWidgetItem(bucket.name))
        self.bucket_list.blockSignals(False)
        if current_name:
            matches = self.bucket_list.findItems(current_name, Qt.MatchFlag.MatchExactly)
            if matches:
                self.bucket_list.setCurrentItem(matches[0])

    def _current_bucket(self) -> Bucket | None:
        row = self.bucket_list.currentRow()
        if row < 0 or row >= len(self._config.buckets):
            return None
        return self._config.buckets[row]

    def _load_bucket_into_form(self, _row: int) -> None:
        bucket = self._current_bucket()
        widgets = (
            (self.target_alloc, bucket.target_allocation if bucket else None),
            (self.target_return, bucket.target_return if bucket else None),
            (self.target_yield, bucket.target_income_yield if bucket else None),
            (self.target_vol, bucket.target_volatility if bucket else None),
            (self.target_dd, bucket.target_max_drawdown if bucket else None),
        )
        for widget, value in widgets:
            widget.blockSignals(True)
            widget.setEnabled(bucket is not None)
            widget.setValue(-0.1 if value is None else float(value))
            widget.blockSignals(False)
        self._rebuild_account_table()
        self._update_alloc_warning()

    def _rebuild_account_table(self) -> None:
        bucket = self._current_bucket()
        included = {item.name: item.target_allocation for item in bucket.accounts} if bucket else {}
        self.account_table.blockSignals(True)
        self.account_table.setRowCount(len(self._account_names))
        for row, name in enumerate(self._account_names):
            check = QTableWidgetItem("")
            check.setFlags(
                Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsSelectable
            )
            check.setCheckState(Qt.CheckState.Checked if name in included else Qt.CheckState.Unchecked)
            self.account_table.setItem(row, 0, check)
            label = QTableWidgetItem(name)
            label.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.account_table.setItem(row, 1, label)
            spin = QDoubleSpinBox()
            spin.setRange(0.0, 100.0)
            spin.setDecimals(1)
            spin.setSuffix(" %")
            spin.setValue(float(included[name]) if name in included and included[name] is not None else 0.0)
            spin.setEnabled(name in included and bucket is not None)
            spin.valueChanged.connect(self._write_form_to_bucket)
            self.account_table.setCellWidget(row, 2, spin)
        self.account_table.blockSignals(False)

    def _on_account_item_changed(self, item: QTableWidgetItem) -> None:
        if item.column() != 0:
            return
        spin = self.account_table.cellWidget(item.row(), 2)
        if spin is not None:
            spin.setEnabled(item.checkState() == Qt.CheckState.Checked)
        self._write_form_to_bucket()

    def _write_form_to_bucket(self) -> None:
        bucket = self._current_bucket()
        if bucket is None:
            return
        bucket.target_allocation = _spin_value(self.target_alloc)
        bucket.target_return = _spin_value(self.target_return)
        bucket.target_income_yield = _spin_value(self.target_yield)
        bucket.target_volatility = _spin_value(self.target_vol)
        bucket.target_max_drawdown = _spin_value(self.target_dd)
        accounts: list[AccountAllocation] = []
        for row in range(self.account_table.rowCount()):
            check = self.account_table.item(row, 0)
            name_item = self.account_table.item(row, 1)
            spin = self.account_table.cellWidget(row, 2)
            if check is None or name_item is None:
                continue
            if check.checkState() != Qt.CheckState.Checked:
                continue
            target = float(spin.value()) if spin is not None else None
            accounts.append(AccountAllocation(name=name_item.text(), target_allocation=target))
        bucket.accounts = accounts
        self._update_alloc_warning()

    def _update_alloc_warning(self) -> None:
        messages = []
        bucket_total = sum(
            (bucket.target_allocation or 0.0) for bucket in self._config.buckets
        )
        if self._config.buckets and abs(bucket_total - 100.0) > 0.5:
            messages.append(f"Bucket targets sum to {bucket_total:.1f}% (expected 100%).")
        bucket = self._current_bucket()
        if bucket:
            account_total = sum((item.target_allocation or 0.0) for item in bucket.accounts)
            if bucket.accounts and abs(account_total - 100.0) > 0.5:
                messages.append(
                    f"Account targets in this bucket sum to {account_total:.1f}% (expected 100%)."
                )
        self.alloc_warning.setText(" ".join(messages))

    def _add_bucket(self) -> None:
        name, ok = QInputDialog.getText(self, "New bucket", "Bucket name:")
        name = name.strip()
        if not ok or not name:
            return
        if any(bucket.name == name for bucket in self._config.buckets):
            QMessageBox.warning(self, "Duplicate name", "A bucket with that name already exists.")
            return
        self._write_form_to_bucket()
        self._config.buckets.append(Bucket(name=name))
        self._refresh_bucket_list()
        self.bucket_list.setCurrentRow(self.bucket_list.count() - 1)

    def _rename_bucket(self) -> None:
        bucket = self._current_bucket()
        if bucket is None:
            return
        name, ok = QInputDialog.getText(self, "Rename bucket", "Bucket name:", text=bucket.name)
        name = name.strip()
        if not ok or not name:
            return
        bucket.name = name
        self._refresh_bucket_list()

    def _remove_bucket(self) -> None:
        row = self.bucket_list.currentRow()
        if row < 0:
            return
        name = self._config.buckets[row].name
        confirm = QMessageBox.question(self, "Remove bucket", f"Remove bucket '{name}'?")
        if confirm != QMessageBox.StandardButton.Yes:
            return
        del self._config.buckets[row]
        self._refresh_bucket_list()
        if self.bucket_list.count():
            self.bucket_list.setCurrentRow(min(row, self.bucket_list.count() - 1))
        else:
            self._load_bucket_into_form(-1)

    def _browse(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self, "Select folder of CSV files", self.dir_edit.text() or str(Path.home())
        )
        if directory:
            self.dir_edit.setText(directory)

    def _apply(self) -> None:
        self._write_form_to_bucket()
        self._config.data_directory = self.dir_edit.text().strip()
        self._config.base_currency = (self.base_currency.text().strip() or "USD").upper()
        self.applied.emit(copy_config(self._config))
