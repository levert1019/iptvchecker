# styles.py

DEEP_PURPLE = "#5b2fc9"
DARK_BG     = "#2b2b2b"
MID_BG      = "#3c3f41"
TEXT_LIGHT  = "#e0e0e0"
HEADER_FONT = "Arial"

STYLE_SHEET = f"""
QWidget {{ background: {DARK_BG}; color: {TEXT_LIGHT}; }}
QLabel, QGroupBox::title {{ color: {TEXT_LIGHT}; }}
QLineEdit {{ background: {MID_BG}; color: {TEXT_LIGHT}; border: none; padding: 2px; }}
QSpinBox, QComboBox {{ background: {MID_BG}; color: {TEXT_LIGHT}; border: none; padding: 2px; }}
QCheckBox {{ color: {TEXT_LIGHT}; }}
QPushButton {{ background: {DEEP_PURPLE}; color: white; border-radius: 4px; padding: 6px; }}
QPushButton:hover {{ background: #7e52e0; }}
QGroupBox {{ background: {MID_BG}; border: 2px solid {DEEP_PURPLE}; margin-top: 1em; }}
QGroupBox::title {{ background-color: {DARK_BG}; subcontrol-origin: margin; subcontrol-position: top left; padding: 4px; }}
QTableWidget, QListWidget {{ background: {MID_BG}; color: {TEXT_LIGHT}; border: none; }}
QScrollArea {{ background: {DARK_BG}; border: none; }}
QScrollBar:vertical, QScrollBar:horizontal {{ background: {MID_BG}; width: 12px; height: 12px; }}
QScrollBar::handle {{ background: {DEEP_PURPLE}; min-height: 20px; border-radius: 6px; }}
QTextEdit {{ background: {MID_BG}; color: {TEXT_LIGHT}; border: none; }}
"""
