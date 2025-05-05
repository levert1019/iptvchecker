# styles.py

STYLE_SHEET = """
/* ────────── GLOBAL BACKGROUND & TEXT ────────── */
QMainWindow, QWidget, QDialog {
    background-color: #2d2d30;
    color: white;
}

/* ────────── NAV BAR ────────── */
QFrame#nav_bar {
    background-color: #5b2fc9;
}

/* ────────── ALL PUSH BUTTONS ────────── */
QPushButton {
    background-color: #5b2fc9;
    color: white;
    border: none;
    border-radius: 6px;
    padding: 6px 14px;
    font-weight: bold;
}
QPushButton:hover {
    background-color: #4a28a0;
}

/* ────────── GROUP BOXES ────────── */
QGroupBox {
    border: 2px solid #5b2fc9;
    border-radius: 6px;
    margin-top: 10px;
    background-color: #2d2d30;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
    background-color: #5b2fc9;
    color: white;
    font-weight: bold;
}

/* ────────── TABLES ────────── */
QTableWidget {
    background-color: #2d2d30;
    gridline-color: #3e3e42;
    color: white;
}
QHeaderView::section {
    background-color: #1e1e1e;
    color: white;
    border: none;
}

/* ────────── SCROLL AREAS ────────── */
QScrollArea {
    background-color: #2d2d30;
}

/* ────────── CHECKBOXES ────────── */
QCheckBox {
    spacing: 8px;
    color: white;
}
QCheckBox::indicator {
    width: 16px; height: 16px;
    border: 2px solid #5b2fc9;
    border-radius: 4px;
    background: transparent;
}
QCheckBox::indicator:checked {
    background: #5b2fc9;
}
"""
