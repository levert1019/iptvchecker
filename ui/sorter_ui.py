# ui/sorter_ui.py

from PyQt5 import QtWidgets, QtCore

class SorterUI(QtWidgets.QWidget):
    """
    UI for the Playlist Sorter with in-line console and filters.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sorter_page")
        self._create_controls()
        self._build_ui()

    def _create_controls(self):
        # Console filter checkboxes
        self.cb_show_working = QtWidgets.QCheckBox("Show Working")
        self.cb_show_info    = QtWidgets.QCheckBox("Show Info")
        self.cb_show_error   = QtWidgets.QCheckBox("Show Error")
        for cb in (self.cb_show_working, self.cb_show_info, self.cb_show_error):
            cb.setChecked(True)

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(12)

        # Header
        hdr = QtWidgets.QLabel()
        hdr.setTextFormat(QtCore.Qt.RichText)
        hdr.setText(
            '<span style="font-size:24pt; color:#FFFFFF; font-weight:bold;">Don</span>'
            '<span style="font-size:24pt; color:#5b2fc9; font-weight:bold;">TV</span>'
            '<span style="font-size:18pt; color:#FFFFFF; font-weight:bold;"> Playlist Sorter</span>'
        )
        hdr.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(hdr)

        # Console Group
        console_box = QtWidgets.QGroupBox("Console")
        v2 = QtWidgets.QVBoxLayout(console_box)
        # Filters (directly under the label)
        h2 = QtWidgets.QHBoxLayout()
        h2.addWidget(self.cb_show_working)
        h2.addWidget(self.cb_show_info)
        h2.addWidget(self.cb_show_error)
        h2.addStretch()
        v2.addLayout(h2)
        # Text area
        self.te_console = QtWidgets.QTextEdit()
        self.te_console.setReadOnly(True)
        v2.addWidget(self.te_console)
        layout.addWidget(console_box)

        # (Additional UI elements like start/pause/stop buttons are managed by MainWindow)
