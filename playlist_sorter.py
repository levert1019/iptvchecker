import sys
import os
from PyQt5 import QtWidgets, QtCore

from styles import STYLE_SHEET

class PlaylistSorter(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DonTV Playlist Sorter")
        self.resize(1000, 700)

        # Build UI
        self._build_ui()
        self.setStyleSheet(STYLE_SHEET)

    def _build_ui(self):
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)

        main_v = QtWidgets.QVBoxLayout(central)
        main_v.setContentsMargins(10, 10, 10, 10)
        main_v.setSpacing(20)

        # Header
        hdr = QtWidgets.QLabel(
            '<span style="font-weight:bold; font-size:28pt;">Don</span>'
            '<span style="font-weight:bold; font-size:28pt; color:#5b2fc9;">TV</span>'
            '<span style="font-weight:bold; font-size:16pt;"> Playlist Sorter</span>'
        )
        hdr.setAlignment(QtCore.Qt.AlignCenter)
        main_v.addWidget(hdr)

        # Placeholder content
        placeholder = QtWidgets.QLabel("Playlist Sorter coming soon.")
        placeholder.setAlignment(QtCore.Qt.AlignCenter)
        main_v.addWidget(placeholder)

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    win = PlaylistSorter()
    win.show()
    sys.exit(app.exec_())
