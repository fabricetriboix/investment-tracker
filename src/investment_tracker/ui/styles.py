"""Qt styles tuned for a 14-inch laptop."""

APP_STYLESHEET = """
QMainWindow, QWidget {
    background: #f4f6f7;
    color: #1c2833;
    font-size: 14px;
}
QTabWidget::pane {
    border: 1px solid #d5dbdb;
    background: #ffffff;
    top: -1px;
}
QTabBar::tab {
    background: #e5e8e8;
    color: #1c2833;
    padding: 7px 12px;
    margin-right: 2px;
    border: 1px solid #d5dbdb;
    border-bottom: none;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    min-width: 7em;
}
QTabBar::tab:selected {
    background: #ffffff;
    font-weight: 600;
    color: #1b4f72;
}
QTabBar::tab:hover:!selected {
    background: #f8f9f9;
}
QGroupBox {
    font-weight: 600;
    border: 1px solid #d5dbdb;
    border-radius: 6px;
    margin-top: 12px;
    padding: 12px 8px 8px 8px;
    background: #ffffff;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: #1b4f72;
}
QTableView, QTableWidget {
    background: #ffffff;
    gridline-color: #eaecee;
    selection-background-color: #d4e6f1;
    selection-color: #1c2833;
    alternate-background-color: #f8f9f9;
    font-size: 14px;
}
QHeaderView::section {
    background: #1b4f72;
    color: #ffffff;
    padding: 10px 18px;
    border: none;
    font-weight: 600;
}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background: #ffffff;
    border: 1px solid #cacfd2;
    border-radius: 3px;
    padding: 3px 6px;
    min-height: 22px;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border: 1px solid #1b4f72;
}
QPushButton {
    background: #1b4f72;
    color: #ffffff;
    border: none;
    border-radius: 4px;
    padding: 6px 12px;
    font-weight: 600;
}
QPushButton:hover {
    background: #154360;
}
QPushButton:pressed {
    background: #1a5276;
}
QPushButton:disabled {
    background: #aab7b8;
}
QPushButton[secondary="true"] {
    background: #ffffff;
    color: #1b4f72;
    border: 1px solid #1b4f72;
}
QPushButton[danger="true"] {
    background: #922b21;
}
QCheckBox {
    spacing: 6px;
}
QScrollArea {
    border: none;
    background: transparent;
}
QSplitter::handle {
    background: #d5dbdb;
}
QStatusBar {
    background: #eaecee;
    color: #34495e;
}
QToolBar {
    background: #ffffff;
    border-bottom: 1px solid #d5dbdb;
    spacing: 8px;
    padding: 4px 8px;
}
"""

POSITIVE = "#196f3d"
NEGATIVE = "#922b21"
NAVY = "#1b4f72"
TEAL = "#0e6655"
AMBER = "#b9770e"
MUTED = "#7f8c8d"
