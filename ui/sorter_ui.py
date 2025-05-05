# playlist_sorter_window.py

from PyQt5 import QtWidgets, QtCore

class SorterUI(QtWidgets.QMainWindow):
    """
    A simplified UI for the Playlist Sorter:
      - Big header
      - Styled console area (same look as IPTV Checker)
      - Checkboxes for Show Working / Show Info / Show Error
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Playlist Sorter")
        self.resize(800, 600)
        self._build_ui()

    def _build_ui(self):
        # Central widget & layout
        central = QtWidgets.QWidget(self)
        v = QtWidgets.QVBoxLayout(central)
        v.setContentsMargins(10, 10, 10, 10)
        v.setSpacing(10)

        # ── Header ───────────────────────────────────────────────
        header = QtWidgets.QLabel("Playlist Sorter")
        header.setAlignment(QtCore.Qt.AlignCenter)
        font = header.font()
        font.setPointSize(20)
        font.setBold(True)
        header.setFont(font)
        v.addWidget(header)

        # ── Console GroupBox ────────────────────────────────────
        gb = QtWidgets.QGroupBox("Console")
        gb.setStyleSheet("""
            QGroupBox { 
                border:2px solid #5b2fc9; 
                border-radius:5px; 
                margin-top:6px; 
            }
            QGroupBox::title { 
                background:#5b2fc9; 
                color:white; 
                subcontrol-origin:margin; 
                left:10px; 
                padding:0 3px; 
            }
        """)
        vb = QtWidgets.QVBoxLayout(gb)

        # The console itself
        self.console = QtWidgets.QPlainTextEdit()
        self.console.setReadOnly(True)
        self.console.setStyleSheet("""
            background-color: black;
            color: white;
            font-family: Consolas, 'Courier New', monospace;
        """)
        vb.addWidget(self.console)

        # ── Log-Level Checkboxes ────────────────────────────────
        hb = QtWidgets.QHBoxLayout()
        self.cb_show_working = QtWidgets.QCheckBox("Show Working")
        self.cb_show_info    = QtWidgets.QCheckBox("Show Info")
        self.cb_show_error   = QtWidgets.QCheckBox("Show Error")
        # default to showing errors
        self.cb_show_error.setChecked(True)

        hb.addWidget(self.cb_show_working)
        hb.addWidget(self.cb_show_info)
        hb.addWidget(self.cb_show_error)
        hb.addStretch()

        vb.addLayout(hb)
        v.addWidget(gb)

        # Set central widget
        self.setCentralWidget(central)


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    win = PlaylistSorterWindow()
    win.show()
    sys.exit(app.exec_())
