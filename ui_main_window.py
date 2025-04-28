import os
import re
import queue
import threading
from PyQt5 import QtWidgets, QtCore
from parser import parse_groups
from workers import WorkerThread
from dialogs import GroupSelectionDialog
from styles import STYLE_SHEET
from utils import QUALITY_LABELS, sup_digits, format_fps, resolution_to_label, clean_name


def build_ui(self):
    # Main window setup
    self.setWindowTitle("DonTV IPTV Checker")
    self.resize(1000, 700)

    # Central widget and layout
    central = QtWidgets.QWidget()
    v = QtWidgets.QVBoxLayout(central)
    v.setContentsMargins(10, 10, 10, 10)
    v.setSpacing(10)

    # Header label
    hdr = QtWidgets.QLabel(
        '<span style="font-weight:bold; font-size:32pt;">Don</span>'
        '<span style="font-weight:bold; font-size:32pt; color:#5b2fc9;">TV</span>'
        '<span style="font-weight:bold; font-size:18pt;"> IPTV Checker</span>'
    )
    hdr.setAlignment(QtCore.Qt.AlignCenter)
    v.addWidget(hdr)

    # M3U & group selection
    h0 = QtWidgets.QHBoxLayout()
    self.le_m3u = QtWidgets.QLineEdit(); h0.addWidget(self.le_m3u)
    btn_browse = QtWidgets.QPushButton("Browse M3U"); btn_browse.clicked.connect(self._on_browse_m3u); h0.addWidget(btn_browse)
    self.btn_select = QtWidgets.QPushButton("Select Groups"); self.btn_select.setEnabled(False); self.btn_select.clicked.connect(self._on_select_groups); h0.addWidget(self.btn_select)
    v.addLayout(h0)

    # Workers, Retries, Timeout
    h1 = QtWidgets.QHBoxLayout()
    h1.addWidget(QtWidgets.QLabel("Workers:"))
    self.sp_workers = QtWidgets.QSpinBox(); self.sp_workers.setRange(1, 50); self.sp_workers.setValue(5); h1.addWidget(self.sp_workers)
    h1.addWidget(QtWidgets.QLabel("Retries:"))
    self.sp_retries = QtWidgets.QSpinBox(); self.sp_retries.setRange(1, 10); self.sp_retries.setValue(2); h1.addWidget(self.sp_retries)
    h1.addWidget(QtWidgets.QLabel("Timeout (s):"))
    self.sp_timeout = QtWidgets.QSpinBox(); self.sp_timeout.setRange(1, 60); self.sp_timeout.setValue(10); h1.addWidget(self.sp_timeout)
    v.addLayout(h1)

    # Options
    h2 = QtWidgets.QHBoxLayout()
    self.cb_split = QtWidgets.QCheckBox("Split into Files"); h2.addWidget(self.cb_split)
    self.cb_update_quality = QtWidgets.QCheckBox("Update Quality in Name"); h2.addWidget(self.cb_update_quality)
    self.cb_update_fps = QtWidgets.QCheckBox("Update FPS in Name"); h2.addWidget(self.cb_update_fps)
    self.cb_include_untested = QtWidgets.QCheckBox("Include Untested Channels"); h2.addWidget(self.cb_include_untested)
    v.addLayout(h2)

    # Output folder
    h3 = QtWidgets.QHBoxLayout()
    h3.addWidget(QtWidgets.QLabel("Out Folder:"))
    self.le_out = QtWidgets.QLineEdit(); self.le_out.setPlaceholderText("Select output folder…"); h3.addWidget(self.le_out)
    btn_out = QtWidgets.QPushButton("Browse"); btn_out.clicked.connect(self._on_browse_out); h3.addWidget(btn_out)
    v.addLayout(h3)

    # Control buttons
    h4 = QtWidgets.QHBoxLayout()
    self.btn_start = QtWidgets.QPushButton("Start"); h4.addWidget(self.btn_start)
    self.btn_pause = QtWidgets.QPushButton("Pause"); self.btn_pause.setEnabled(False); h4.addWidget(self.btn_pause)
    self.btn_stop = QtWidgets.QPushButton("Stop"); self.btn_stop.setEnabled(False); h4.addWidget(self.btn_stop)
    v.addLayout(h4)

    # Result tables
    panes = QtWidgets.QHBoxLayout()
    for title in ["Working", "Black Screen", "Non Working"]:
        box = QtWidgets.QGroupBox(title)
        tbl = QtWidgets.QTableWidget(0, 3)
        tbl.setHorizontalHeaderLabels(["Channel", "Res", "FPS"])
        tbl.horizontalHeader().setStretchLastSection(True)
        tbl.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        tbl.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        tbl.setStyleSheet(
            "QHeaderView::section { background-color: #2b2b2b; color: #e0e0e0; }"
            "QTableWidget { background-color: #3c3f41; color: #e0e0e0; }"
            "QTableWidget::item:selected { background-color: #5b2fc9; color: white; }"
        )
        QtWidgets.QVBoxLayout(box).addWidget(tbl)
        panes.addWidget(box)
        setattr(self, f"tbl_{title.lower().replace(' ', '_')}", tbl)
    v.addLayout(panes)

    # Console + filters
    grpC = QtWidgets.QGroupBox("Console")
    vg = QtWidgets.QVBoxLayout(grpC)
    hf5 = QtWidgets.QHBoxLayout()
    self.cb_show_working = QtWidgets.QCheckBox("Show Working"); self.cb_show_working.setChecked(True); hf5.addWidget(self.cb_show_working)
    self.cb_show_info = QtWidgets.QCheckBox("Show Info"); self.cb_show_info.setChecked(True); hf5.addWidget(self.cb_show_info)
    self.cb_show_error = QtWidgets.QCheckBox("Show Error"); self.cb_show_error.setChecked(True); hf5.addWidget(self.cb_show_error)
    for cb in (self.cb_show_working, self.cb_show_info, self.cb_show_error):
        cb.stateChanged.connect(self._refresh_console)
    vg.addLayout(hf5)
    self.te_console = QtWidgets.QTextEdit(); self.te_console.setReadOnly(True); vg.addWidget(self.te_console)
    v.addWidget(grpC)

    # Status bar & finalize
    self.status = QtWidgets.QStatusBar()
    self.setStatusBar(self.status)
    self.setCentralWidget(central)
    self.setStyleSheet(STYLE_SHEET)
