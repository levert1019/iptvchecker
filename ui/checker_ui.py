# ui/checker_ui.py

from PyQt5 import QtWidgets, QtCore

class CheckerUI(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("checker_page")
        self._create_controls()
        self._build_ui()

    def _create_controls(self):
        # control buttons
        self.btn_start = QtWidgets.QPushButton("Start")
        self.btn_start.setObjectName("controlButton")
        self.btn_pause = QtWidgets.QPushButton("Pause")
        self.btn_pause.setObjectName("controlButton")
        self.btn_stop  = QtWidgets.QPushButton("Stop")
        self.btn_stop .setObjectName("controlButton")

        # console filter checkboxes
        self.cb_show_working = QtWidgets.QCheckBox("Show Working")
        self.cb_show_info    = QtWidgets.QCheckBox("Show Info")
        self.cb_show_error   = QtWidgets.QCheckBox("Show Error")
        for cb in (self.cb_show_working, self.cb_show_info, self.cb_show_error):
            cb.setChecked(True)

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10,10,10,10)
        layout.setSpacing(12)

        # ─── Rich‐Text Header ──────────────────────────────────────────────
        hdr = QtWidgets.QLabel()
        hdr.setTextFormat(QtCore.Qt.RichText)
        hdr.setText(
            '<span style="font-size:24pt; color:#FFFFFF; font-weight:bold;">Don</span>'
            '<span style="font-size:24pt; color:#5b2fc9; font-weight:bold;">TV</span>'
            '<span style="font-size:18pt; color:#FFFFFF; font-weight:bold;"> IPTV Checker</span>'
        )
        hdr.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(hdr)

        # ─── Results Tables ────────────────────────────────────────────────
        pan_h = QtWidgets.QHBoxLayout()
        for status in ("working","black_screen","non_working"):
            title = status.replace("_"," ").title()
            box = QtWidgets.QGroupBox(title)
            v = QtWidgets.QVBoxLayout(box)
            cols = 3 if status=="working" else 1
            tbl = QtWidgets.QTableWidget(0, cols)
            headers = ["Channel","Res","FPS"] if status=="working" else ["Channel"]
            tbl.setHorizontalHeaderLabels(headers)
            tbl.horizontalHeader().setStretchLastSection(True)
            tbl.verticalHeader().setVisible(False)
            tbl.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
            tbl.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
            v.addWidget(tbl)
            setattr(self, f"tbl_{status}", tbl)
            pan_h.addWidget(box)
        layout.addLayout(pan_h)

        # ─── Console ────────────────────────────────────────────────────────
        console_box = QtWidgets.QGroupBox("Console")
        v2 = QtWidgets.QVBoxLayout(console_box)
        h2 = QtWidgets.QHBoxLayout()
        h2.addWidget(self.cb_show_working)
        h2.addWidget(self.cb_show_info)
        h2.addWidget(self.cb_show_error)
        h2.addStretch()
        v2.addLayout(h2)
        self.te_console = QtWidgets.QTextEdit()
        self.te_console.setReadOnly(True)
        v2.addWidget(self.te_console)
        layout.addWidget(console_box)
