"""Main window: dashboard, configuration, one tab per account."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QMainWindow, QTabWidget

from investment_tracker.config import AppConfig, save as save_config
from investment_tracker.csv_loader import Account, load_directory
from investment_tracker.currency import FxConverter
from investment_tracker.portfolio import DashboardData, build_dashboard
from investment_tracker.ui.account_tab import AccountTab
from investment_tracker.ui.config_tab import ConfigTab
from investment_tracker.ui.dashboard import DashboardTab


class _DashboardWorker(QThread):
    finished_ok = Signal(object)
    failed = Signal(str)

    def __init__(self, accounts: list[Account], config: AppConfig, parent=None):
        super().__init__(parent)
        self._accounts = accounts
        self._config = config

    def run(self) -> None:
        try:
            fx = FxConverter()
            data = build_dashboard(self._accounts, self._config, fx)
            self.finished_ok.emit(data)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(self, config: AppConfig):
        super().__init__()
        self.setWindowTitle("Investment Tracker")
        self.resize(1280, 800)
        self.setMinimumSize(1100, 680)

        self.config = config
        self.accounts: list[Account] = []
        self._worker: _DashboardWorker | None = None
        self._account_tabs: dict[str, AccountTab] = {}
        self._dash_generation = 0

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setUsesScrollButtons(True)
        self.tabs.setElideMode(Qt.TextElideMode.ElideNone)
        self.setCentralWidget(self.tabs)

        self.dashboard = DashboardTab()
        self.config_tab = ConfigTab()
        self.config_tab.applied.connect(self._on_config_applied)

        refresh = QAction("Reload CSVs", self)
        refresh.setShortcut(QKeySequence.StandardKey.Refresh)
        refresh.triggered.connect(self.reload)
        self.addAction(refresh)

        self.statusBar().showMessage("Loading…")
        self.reload()

    def _rebuild_tabs(self) -> None:
        current = self.tabs.tabText(self.tabs.currentIndex()) if self.tabs.count() else "Dashboard"
        self.tabs.blockSignals(True)
        while self.tabs.count():
            widget = self.tabs.widget(0)
            self.tabs.removeTab(0)
            if widget not in (self.dashboard, self.config_tab):
                widget.deleteLater()

        self.tabs.addTab(self.dashboard, "Dashboard")
        self.tabs.addTab(self.config_tab, "Configuration")
        self._account_tabs = {}
        for account in self.accounts:
            bucket = self.config.bucket_for_account(account.name)
            bucket_name = bucket.name if bucket is not None else None
            tab = AccountTab(account, bucket_name=bucket_name)
            index = self.tabs.addTab(tab, account.name)
            type_bit = f"{account.type_label} · {account.currency}"
            self.tabs.setTabToolTip(
                index,
                f"{type_bit} · {bucket_name}" if bucket_name else f"{type_bit} · Unassigned",
            )
            self._account_tabs[account.name] = tab
        self.tabs.blockSignals(False)

        for index in range(self.tabs.count()):
            if self.tabs.tabText(index) == current:
                self.tabs.setCurrentIndex(index)
                break

    def reload(self) -> None:
        directory = Path(self.config.data_directory).expanduser() if self.config.data_directory else None
        errors: list[str] = []
        if directory is None or not str(directory):
            self.accounts = []
            errors = ["Choose a CSV directory in the Configuration tab."]
        else:
            self.accounts, errors = load_directory(directory)

        self.config_tab.set_accounts([account.name for account in self.accounts])
        self.config_tab.load_config(self.config)
        self._rebuild_tabs()
        self._refresh_dashboard(errors)

    def _refresh_dashboard(self, extra_errors: list[str] | None = None) -> None:
        if self._worker is not None and self._worker.isRunning():
            try:
                self._worker.finished_ok.disconnect()
                self._worker.failed.disconnect()
            except TypeError:
                pass

        self._dash_generation += 1
        generation = self._dash_generation
        self.statusBar().showMessage("Updating dashboard (including FX rates)…")
        extra = list(extra_errors or [])

        def on_ok(data: DashboardData) -> None:
            if generation != self._dash_generation:
                return
            data.load_errors = extra + data.load_errors
            self.dashboard.render(data, self.config)
            as_of = data.as_of or "—"
            n = len(self.accounts)
            self.statusBar().showMessage(
                f"{n} account{'s' if n != 1 else ''} · as of {as_of} · "
                f"Frankfurter FX · {self.config.base_currency}"
            )

        def on_fail(message: str) -> None:
            if generation != self._dash_generation:
                return
            self.statusBar().showMessage(f"Dashboard error: {message}", 10000)

        self._worker = _DashboardWorker(self.accounts, self.config, self)
        self._worker.finished_ok.connect(on_ok)
        self._worker.failed.connect(on_fail)
        self._worker.start()

    def _on_config_applied(self, config: AppConfig) -> None:
        self.config = config
        path = save_config(self.config)
        self.reload()
        self.statusBar().showMessage(f"Configuration saved to {path}", 6000)
