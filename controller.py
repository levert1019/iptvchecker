import sys
import os
import re
import queue
import threading
from PyQt5 import QtWidgets, QtCore
from parser import parse_groups
from workers import WorkerThread
from dialogs import GroupSelectionDialog
from styles import STYLE_SHEET

# Superscript quality labels
QUALITY_LABELS = {
    'sd': 'ˢᴰ',
    'hd': 'ᴴᴰ',
    'fhd': 'ᶠᴴᴰ',
    'uhd': 'ᵁᴴᴰ'
}

def sup_digits(text: str) -> str:
    tbl = str.maketrans({
        '0': '⁰', '1': '¹', '2': '²', '3': '³', '4': '⁴',
        '5': '⁵', '6': '⁶', '7': '⁷', '8': '⁸', '9': '⁹'
    })
    return text.translate(tbl)

def format_fps(text: str) -> str:
    m = re.search(r"(\d+(?:\.\d+)?)", text or "")
    if not m:
        return '–'
    num = m.group(1)
    if num.endswith('.0'):
        num = num[:-2]
    return f"{sup_digits(num)}ᶠᵖˢ"

def resolution_to_label(res: str) -> str:
    parts = res.split('×')
    if len(parts) != 2:
        return ''
    try:
        w, h = map(int, parts)
    except ValueError:
        return ''
    if w >= 3840 or h >= 2160:
        key = 'uhd'
    elif w >= 1920 or h >= 1080:
        key = 'fhd'
    elif w >= 1280 or h >= 720:
        key = 'hd'
    else:
        key = 'sd'
    return QUALITY_LABELS[key]

def clean_name(name: str) -> str:
    name = re.sub(r"\d+ᶠᵖˢ", '', name)
    for v in QUALITY_LABELS.values():
        name = name.replace(v, '')
    name = re.sub(r"\b(sd|hd|fhd|uhd)\b", '', name, flags=re.IGNORECASE)
    name = re.sub(r"\b\d+(?:\.\d+)?fps\b", '', name, flags=re.IGNORECASE)
    return name.strip()

class IPTVChecker(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DonTV IPTV Checker")
        self.resize(1000, 700)
        # Data state
        self.group_urls = {}
        self.categories = {}
        self.selected_groups = []
        self.tasks_q = None
        self.threads = []
        self.results = {}
        self.url_map = {}
        self.extinf_map = {}
        self.status_map = {}
        self.log_records = []
        self.remaining = 0
        self._is_paused = False
        # Build UI
        self._build_ui()
        self.setStyleSheet(STYLE_SHEET)

    def _build_ui(self):
        central = QtWidgets.QWidget()
        main_layout = QtWidgets.QVBoxLayout(central)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # Header
        hdr = QtWidgets.QLabel(
            '<span style="font-weight:bold; font-size:32pt;">Don</span>'
            '<span style="font-weight:bold; font-size:32pt; color:#5b2fc9;">TV</span>'
            '<span style="font-weight:bold; font-size:18pt;"> IPTV Checker</span>'
        )
        hdr.setAlignment(QtCore.Qt.AlignCenter)
        main_layout.addWidget(hdr)

        # Top option panels
        top_layout = QtWidgets.QHBoxLayout()

        # Testing Options group
        grp_test = QtWidgets.QGroupBox("Testing Options")
        grp_test.setStyleSheet(
            "QGroupBox { border:2px solid #5b2fc9; border-radius:5px; margin-top:10px; }"
            "QGroupBox:title { subcontrol-origin: margin; subcontrol-position: top center; padding: 0 3px; }"
        )
        form = QtWidgets.QFormLayout(grp_test)
        self.sp_workers = QtWidgets.QSpinBox(); self.sp_workers.setRange(1, 50); self.sp_workers.setValue(5)
        form.addRow("Workers:", self.sp_workers)
        self.sp_timeout = QtWidgets.QSpinBox(); self.sp_timeout.setRange(1, 60); self.sp_timeout.setValue(10)
        form.addRow("Max Timeout (s):", self.sp_timeout)
        self.sp_retries = QtWidgets.QSpinBox(); self.sp_retries.setRange(1, 10); self.sp_retries.setValue(2)
        form.addRow("Max Retries:", self.sp_retries)
        top_layout.addWidget(grp_test)

        # Output Options group
        grp_out = QtWidgets.QGroupBox("Output Options")
        grp_out.setStyleSheet(
            "QGroupBox { border:2px solid #5b2fc9; border-radius:5px; margin-top:10px; }"
            "QGroupBox:title { subcontrol-origin: margin; subcontrol-position: top center; padding: 0 3px; }"
        )
        v2 = QtWidgets.QVBoxLayout(grp_out)
        self.cb_update_quality = QtWidgets.QCheckBox("Update Quality in Names")
        v2.addWidget(self.cb_update_quality)
        self.cb_update_fps = QtWidgets.QCheckBox("Add FPS to Names")
        v2.addWidget(self.cb_update_fps)
        self.cb_split = QtWidgets.QCheckBox("Split into Files")
        v2.addWidget(self.cb_split)
        self.cb_include_untested = QtWidgets.QCheckBox("Include Untested Channels")
        v2.addWidget(self.cb_include_untested)
        v2.addSpacing(10)
        self.btn_out = QtWidgets.QPushButton("Select Output Directory")
        self.btn_out.setStyleSheet("background-color:#5b2fc9; color:white; padding:8px; font-weight:bold;")
        v2.addWidget(self.btn_out)
        self.lbl_out_dir = QtWidgets.QLabel("Output Directory: ")
        v2.addWidget(self.lbl_out_dir)
        top_layout.addWidget(grp_out)

        main_layout.addLayout(top_layout)

        # Bottom control buttons
        btn_layout = QtWidgets.QHBoxLayout()
        self.btn_load = QtWidgets.QPushButton("Load M3U File")
        self.btn_load.setStyleSheet("background-color:#5b2fc9; color:white; padding:10px; font-weight:bold;")
        btn_layout.addWidget(self.btn_load)
        self.btn_select_groups = QtWidgets.QPushButton("Select Groups")
        self.btn_select_groups.setEnabled(False)
        btn_layout.addWidget(self.btn_select_groups)
        self.btn_start = QtWidgets.QPushButton("Start Testing")
        btn_layout.addWidget(self.btn_start)
        self.btn_pause = QtWidgets.QPushButton("Pause")
        self.btn_pause.setEnabled(False)
        btn_layout.addWidget(self.btn_pause)
        self.btn_stop = QtWidgets.QPushButton("Stop")
        self.btn_stop.setEnabled(False)
        btn_layout.addWidget(self.btn_stop)
        main_layout.addLayout(btn_layout)

        # Connect signals
        self.btn_load.clicked.connect(self._on_browse_m3u)
        self.btn_select_groups.clicked.connect(self._on_select_groups)
        self.btn_out.clicked.connect(self._on_browse_out)
        self.btn_start.clicked.connect(self.start_check)
        self.btn_pause.clicked.connect(self._toggle_pause)
        self.btn_stop.clicked.connect(self.stop_check)

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
                "QTableWidget::item:selected { background-color: #5b2fc9; color:white; }"
            )
            QtWidgets.QVBoxLayout(box).addWidget(tbl)
            panes.addWidget(box)
            setattr(self, f"tbl_{title.lower().replace(' ', '_')}", tbl)
        main_layout.addLayout(panes)

        # Console + filters
        grpC = QtWidgets.QGroupBox("Console")
        vg = QtWidgets.QVBoxLayout(grpC)
        hf = QtWidgets.QHBoxLayout()
        self.cb_show_working = QtWidgets.QCheckBox("Show Working"); self.cb_show_working.setChecked(True); hf.addWidget(self.cb_show_working)
        self.cb_show_info = QtWidgets.QCheckBox("Show Info"); self.cb_show_info.setChecked(True); hf.addWidget(self.cb_show_info)
        self.cb_show_error = QtWidgets.QCheckBox("Show Error"); self.cb_show_error.setChecked(True); hf.addWidget(self.cb_show_error)
        for cb in (self.cb_show_working, self.cb_show_info, self.cb_show_error): cb.stateChanged.connect(self._refresh_console)
        vg.addLayout(hf)
        self.te_console = QtWidgets.QTextEdit(); self.te_console.setReadOnly(True); vg.addWidget(self.te_console)
        main_layout.addWidget(grpC)

        # Status
        self.status = QtWidgets.QStatusBar()
        self.setStatusBar(self.status)
        self.setCentralWidget(central)

    # ... rest of methods (start_check, _on_result, etc.) remain unchanged ...

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    win = IPTVChecker()
    win.show()
    sys.exit(app.exec_())
