from PyQt5 import QtWidgets, QtCore

class CheckerUI(QtWidgets.QWidget):
    """
    UI definition for the IPTV Checker page.
    Exposes:
      - btn_start, btn_pause, btn_stop
      - tbl_working, tbl_black_screen, tbl_non_working
      - te_console, cb_show_working, cb_show_info, cb_show_error
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        # Main vertical layout
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(20)

        # Header (rich text)
        hdr = QtWidgets.QLabel()
        hdr.setTextFormat(QtCore.Qt.RichText)
        hdr.setText(
            '<span style="font-size:24pt; color:#FFFFFF; font-weight:bold;">Don</span>'
            '<span style="font-size:24pt; color:#5b2fc9; font-weight:bold;">TV</span>'
            '<span style="font-size:18pt; color:#FFFFFF; font-weight:bold;"> IPTV Checker</span>'
        )
        hdr.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(hdr)

        # Control buttons row
        btns = QtWidgets.QHBoxLayout()
        self.btn_start = QtWidgets.QPushButton("Start")
        self.btn_start.setFixedSize(130, 45)
        btns.addWidget(self.btn_start)
        btns.addSpacing(10)

        self.btn_pause = QtWidgets.QPushButton("Pause")
        self.btn_pause.setFixedSize(130, 45)
        btns.addWidget(self.btn_pause)
        btns.addSpacing(10)

        self.btn_stop = QtWidgets.QPushButton("Stop")
        self.btn_stop.setFixedSize(130, 45)
        btns.addWidget(self.btn_stop)
        btns.addStretch()

        layout.addLayout(btns)

        # Result tables: Working / Black Screen / Non-working
        panes = QtWidgets.QHBoxLayout()
        for status, cols, headers in [
            ("working",     3, ["Channel", "Res", "FPS"]),
            ("black_screen",1, ["Channel"]),
            ("non_working", 1, ["Channel"])
        ]:
            grp = QtWidgets.QGroupBox(status.replace("_", " ").title())
            tbl = QtWidgets.QTableWidget(0, cols)
            tbl.setHorizontalHeaderLabels(headers)
            tbl.horizontalHeader().setStretchLastSection(True)
            tbl.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
            tbl.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)

            # Give each table a member name
            setattr(self, f"tbl_{status}", tbl)

            container = QtWidgets.QVBoxLayout(grp)
            container.addWidget(tbl)
            panes.addWidget(grp)

        layout.addLayout(panes)

        # Console + filter checkboxes
        console_grp = QtWidgets.QGroupBox("Console")
        console_v   = QtWidgets.QVBoxLayout(console_grp)

        flt_h = QtWidgets.QHBoxLayout()
        self.cb_show_working = QtWidgets.QCheckBox("Show Working")
        self.cb_show_info    = QtWidgets.QCheckBox("Show Info")
        self.cb_show_error   = QtWidgets.QCheckBox("Show Error")
        for cb in (self.cb_show_working, self.cb_show_info, self.cb_show_error):
            cb.setChecked(True)
            flt_h.addWidget(cb)
        console_v.addLayout(flt_h)

        self.te_console = QtWidgets.QTextEdit()
        self.te_console.setReadOnly(True)
        console_v.addWidget(self.te_console)

        layout.addWidget(console_grp)
